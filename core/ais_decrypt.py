"""
Encrypted AIS Decryption Engine.

Decrypts AIS payloads encrypted with AES-128-CBC or AES-256-CBC using
pre-shared keys.  Uses the ``cryptography`` library backed by OpenSSL 3.x
so that a FIPS-validated OpenSSL provider can be used at deployment time
without any application code changes.

Key management (add / remove / persist) is handled by the companion
dialog ``gui/ais_encrypt_dialog.py``.  Keys are stored in
``ais_encrypt_config.json`` in the working directory.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_padding
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    logger.warning("cryptography library not installed — encrypted AIS disabled")

CONFIG_FILE = 'ais_encrypt_config.json'


# ------------------------------------------------------------------
# Key configuration
# ------------------------------------------------------------------

def load_encrypt_config() -> list[dict]:
    """Load encryption keys from config file.

    Returns a list of key dicts::

        [{'name': str, 'key_id': str, 'key_hex': str,
          'cipher': str, 'enabled': bool}, ...]
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            return data.get('keys', [])
        except Exception as exc:
            logger.error("Error loading AIS encrypt config: %s", exc)
    return []


def save_encrypt_config(keys: list[dict]):
    """Persist encryption keys to config file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'keys': keys}, f, indent=2)


# ------------------------------------------------------------------
# AIS Decryptor
# ------------------------------------------------------------------

class AISDecryptor:
    """Attempts AES decryption of 6-bit-armored AIS payloads.

    The encrypted AIS scheme used here works as follows:

    1.  The **sender** takes the raw binary AIS payload (the bit-vector
        that would normally be 6-bit-ASCII-armored directly), pads it to
        an AES block boundary using PKCS7, encrypts with AES-CBC, then
        6-bit-ASCII-armors the ciphertext into the AIVDM sentence.

    2.  The **receiver** (this class) reverses that process: de-armors the
        payload from the AIVDM sentence to raw bytes, tries AES-CBC
        decryption with each enabled key, strips PKCS7 padding, and
        re-armors the cleartext back into a 6-bit payload string that the
        standard ITU-R M.1371 decoder can process.

    A 16-byte IV is prepended to the ciphertext (standard practice), so
    the first 16 bytes of the de-armored data are the IV.
    """

    def __init__(self):
        self._keys: list[dict] = []

    # ---- key management ----

    def load_keys(self):
        """Reload keys from the config file."""
        self._keys = load_encrypt_config()
        enabled = sum(1 for k in self._keys if k.get('enabled'))
        logger.info("AIS decrypt: loaded %d keys (%d enabled)",
                    len(self._keys), enabled)

    @property
    def has_keys(self) -> bool:
        return any(k.get('enabled') for k in self._keys)

    @property
    def key_count(self) -> int:
        return sum(1 for k in self._keys if k.get('enabled'))

    # ---- decryption ----

    def try_decrypt(self, payload_str: str, pad_bits: int
                    ) -> tuple[str, int, bool, str]:
        """Attempt to decrypt an AIS payload.

        Parameters
        ----------
        payload_str : str
            The 6-bit-ASCII-armored payload from the AIVDM sentence.
        pad_bits : int
            Number of padding bits in the last 6-bit character.

        Returns
        -------
        (payload, pad, was_encrypted, key_name)
            If decryption succeeds, *payload* and *pad* are the cleartext
            values ready for normal ITU decode.  *was_encrypted* is True
            and *key_name* identifies which key succeeded.
            If no key matches, the original values are returned with
            *was_encrypted* = False and *key_name* = ''.
        """
        if not _HAS_CRYPTO or not self._keys:
            return payload_str, pad_bits, False, ''

        raw = _payload_to_bytes(payload_str, pad_bits)
        if len(raw) < 17:
            # Too short to contain IV + at least one AES block
            return payload_str, pad_bits, False, ''

        iv = raw[:16]
        ciphertext = raw[16:]

        for key_cfg in self._keys:
            if not key_cfg.get('enabled'):
                continue
            try:
                key_bytes = bytes.fromhex(key_cfg['key_hex'])
            except (ValueError, KeyError):
                continue

            cipher_name = key_cfg.get('cipher', 'AES-128-CBC')
            expected_len = 16 if '128' in cipher_name else 32
            if len(key_bytes) != expected_len:
                continue

            try:
                cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
                decryptor = cipher.decryptor()
                plaintext_padded = decryptor.update(ciphertext) + decryptor.finalize()

                # Strip PKCS7 padding
                unpadder = sym_padding.PKCS7(128).unpadder()
                plaintext = unpadder.update(plaintext_padded) + unpadder.finalize()

                # Re-armor into 6-bit payload
                dec_payload, dec_pad = _bytes_to_payload(plaintext)

                # Validate: first 6 bits should be a valid AIS message type (1–27)
                if not _looks_like_valid_ais(dec_payload):
                    continue

                logger.debug("AIS decrypt OK with key '%s'",
                             key_cfg.get('name', '?'))
                return dec_payload, dec_pad, True, key_cfg.get('name', '')

            except Exception:
                # Wrong key or corrupted — try next
                continue

        return payload_str, pad_bits, False, ''


# ------------------------------------------------------------------
# AIS encryption (for test sender / key verification)
# ------------------------------------------------------------------

def encrypt_ais_payload(payload_str: str, pad_bits: int,
                        key_hex: str, cipher_name: str = 'AES-128-CBC'
                        ) -> tuple[str, int]:
    """Encrypt an AIS payload for testing / sender use.

    Returns (encrypted_payload_str, pad_bits).
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography library not installed")

    key_bytes = bytes.fromhex(key_hex)
    raw = _payload_to_bytes(payload_str, pad_bits)

    # PKCS7 pad to AES block size
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()

    # Generate random IV
    iv = os.urandom(16)

    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    # Prepend IV to ciphertext, then re-armor
    encrypted_raw = iv + ciphertext
    return _bytes_to_payload(encrypted_raw)


# ------------------------------------------------------------------
# Payload <-> bytes conversion helpers
# ------------------------------------------------------------------

def _payload_to_bytes(payload: str, pad_bits: int) -> bytes:
    """Convert 6-bit-ASCII-armored AIVDM payload to raw bytes."""
    bits: list[int] = []
    for ch in payload:
        val = ord(ch) - 48
        if val > 40:
            val -= 8
        for shift in (5, 4, 3, 2, 1, 0):
            bits.append((val >> shift) & 1)
    if pad_bits:
        bits = bits[:-pad_bits]
    # Pad to byte boundary
    remainder = len(bits) % 8
    if remainder:
        bits += [0] * (8 - remainder)
    raw = bytearray()
    for i in range(0, len(bits), 8):
        byte_val = 0
        for b in bits[i:i+8]:
            byte_val = (byte_val << 1) | b
        raw.append(byte_val)
    return bytes(raw)


def _bytes_to_payload(data: bytes) -> tuple[str, int]:
    """Convert raw bytes back to 6-bit-ASCII-armored payload + pad count."""
    bits: list[int] = []
    for byte_val in data:
        for shift in (7, 6, 5, 4, 3, 2, 1, 0):
            bits.append((byte_val >> shift) & 1)
    # Pad to multiple of 6
    pad = (6 - len(bits) % 6) % 6
    bits += [0] * pad
    chars = []
    for i in range(0, len(bits), 6):
        val = 0
        for b in bits[i:i+6]:
            val = (val << 1) | b
        val += 48
        if val > 87:
            val += 8
        chars.append(chr(val))
    return ''.join(chars), pad


def _looks_like_valid_ais(payload: str) -> bool:
    """Quick sanity check: first 6 bits should be msg type 1-27."""
    if not payload:
        return False
    val = ord(payload[0]) - 48
    if val > 40:
        val -= 8
    msg_type = val  # top 6 bits of first char = msg type
    return 1 <= msg_type <= 27
