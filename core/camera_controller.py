"""
PTZ Camera Controller
Sends NMEA-style bearing commands to a Pan/Tilt/Zoom camera via UDP and
receives the camera's current azimuth via a separate UDP listen port.

Command flow:
  1. Operator clicks "Slew Camera" on an AIS or ARPA target.
  2. This module builds a configurable NMEA-style string that embeds the
     target's true bearing and sends it to the camera controller over UDP.
  3. The camera responds with its own NMEA-style sentence containing its
     current azimuth, which is parsed here and forwarded to the PPI display.

NMEA checksum (standard XOR):
  All bytes between '$' and '*' exclusive are XOR'd.
  Result is encoded as two uppercase hex digits.
"""

import json
import logging
import math
import os
import socket
import threading

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

_CONFIG_FILE = 'nmea_config.json'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def nmea_checksum(body: str) -> str:
    """Return two-character hex XOR checksum of *body* (between $ and *)."""
    csum = 0
    for ch in body:
        csum ^= ord(ch)
    return f"{csum:02X}"


def bearing_between(own_lat, own_lon, tgt_lat, tgt_lon) -> float:
    """Calculate true bearing (0-360°) from own ship to target."""
    dlat = tgt_lat - own_lat
    dlon = (tgt_lon - own_lon) * math.cos(math.radians(own_lat))
    return math.degrees(math.atan2(dlon, dlat)) % 360.0


# ---------------------------------------------------------------------------
# CameraController
# ---------------------------------------------------------------------------

class CameraController(QObject):
    """
    Manages a PTZ camera via configurable NMEA-style UDP messages.

    Outgoing command template variables
    ------------------------------------
    [HDR]  — the configured command header   (e.g. PCAM)
    [BRG]  — target bearing, 6 chars         (e.g. 045.30)
    [CHK]  — NMEA XOR checksum, 2 hex chars  (e.g. 4A)

    Example template : ``$[HDR],[BRG]*[CHK]``
    Rendered         : ``$PCAM,045.30*4A``

    Incoming response
    -----------------
    The camera sends a NMEA-style sentence such as ``$PCAMR,045.30*XX``.
    The response header and 1-based field index of the azimuth value are
    both configurable.
    """

    # Signals
    azimuth_updated    = pyqtSignal(float)   # camera's current azimuth (degrees true)
    status_updated     = pyqtSignal(str)     # human-readable status / log message
    connection_changed = pyqtSignal(bool)    # True = listener running

    # Default configuration
    _DEFAULTS = {
        'enabled':                 False,
        'host':                    '192.168.1.100',
        'send_port':               10120,
        'listen_port':             10121,
        'cmd_header':              'PCAM',
        'cmd_template':            '$[HDR],[BRG]*[CHK]',
        'response_header':         'PCAMR',
        'response_bearing_field':  1,       # 1-based field after the header
        'bearing_mode':            'relative',  # 'true' = geographic north, 'relative' = relative to ship heading
    }

    def __init__(self):
        super().__init__()
        self.config = dict(self._DEFAULTS)
        self.load_config()

        self.current_azimuth = None

        self._running = False
        self._listen_thread = None
        self._sock_recv = None

    # ------------------------------------------------------------------
    # Configuration persistence
    # ------------------------------------------------------------------

    def load_config(self):
        """Load camera section from nmea_config.json."""
        if not os.path.exists(_CONFIG_FILE):
            return
        try:
            with open(_CONFIG_FILE, 'r') as fh:
                data = json.load(fh)
            self.config.update(data.get('camera', {}))
        except Exception as exc:
            logger.error("Camera config load error: %s", exc)

    def save_config(self):
        """Persist camera section into nmea_config.json (preserves other keys)."""
        data = {}
        if os.path.exists(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE, 'r') as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                # Do NOT continue: writing now would replace the whole file
                # with only the camera section and wipe the NMEA source config.
                logger.error("Camera config not saved — cannot read %s: %s",
                             _CONFIG_FILE, exc)
                return
        data['camera'] = self.config
        try:
            with open(_CONFIG_FILE, 'w') as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:
            logger.error("Camera config save error: %s", exc)

    # ------------------------------------------------------------------
    # Message building
    # ------------------------------------------------------------------

    def build_command(self, bearing_deg: float) -> str:
        """
        Render the NMEA-style slew command for *bearing_deg*.

        Template variables are substituted in order:
          [HDR] → cmd_header
          [BRG] → bearing formatted as ``ddd.dd`` (e.g. ``045.30``)
          [CHK] → NMEA XOR checksum of body between $ and *
        """
        template = self.config.get('cmd_template', '$[HDR],[BRG]*[CHK]')
        header   = self.config.get('cmd_header', 'PCAM')
        brg_str  = f"{bearing_deg:06.2f}"

        msg = template.replace('[HDR]', header).replace('[BRG]', brg_str)

        # Calculate checksum for the body between $ and *
        if '$' in msg and '*' in msg:
            body = msg[msg.index('$') + 1: msg.index('*')]
            msg  = msg.replace('[CHK]', nmea_checksum(body))
        else:
            msg = msg.replace('[CHK]', '')

        # Ensure CRLF termination
        msg = msg.rstrip('\r\n') + '\r\n'
        return msg

    def parse_response(self, sentence: str):
        """
        Extract camera azimuth from an incoming NMEA-style sentence.

        Returns float azimuth or None if the sentence does not match the
        configured response header or cannot be parsed.
        """
        sentence = sentence.strip()
        resp_hdr  = self.config.get('response_header', 'PCAMR')
        field_idx = int(self.config.get('response_bearing_field', 1))

        # Strip leading $
        if sentence.startswith('$'):
            sentence = sentence[1:]
        # Verify and strip trailing *CHECKSUM
        if '*' in sentence:
            star = sentence.index('*')
            body, given = sentence[:star], sentence[star + 1:star + 3]
            if given and nmea_checksum(body).upper() != given.upper():
                return None
            sentence = body

        parts = sentence.split(',')
        if not parts or parts[0] != resp_hdr:
            return None

        try:
            azimuth = float(parts[field_idx])
        except (IndexError, ValueError):
            return None
        if not math.isfinite(azimuth):
            return None
        return azimuth % 360.0

    # ------------------------------------------------------------------
    # Send command
    # ------------------------------------------------------------------

    def send_slew_command(self, bearing_deg: float):
        """Send a NMEA slew command to the camera via UDP."""
        if not self.config.get('enabled', False):
            self.status_updated.emit("Camera control is disabled.")
            return

        msg  = self.build_command(bearing_deg)
        host = self.config.get('host', '127.0.0.1')
        port = int(self.config.get('send_port', 10120))

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            sock.sendto(msg.encode('ascii', errors='replace'), (host, port))
            sock.close()
            self.status_updated.emit(
                f"CAM SLEW {bearing_deg:06.2f}° → {host}:{port}  [{msg.strip()}]"
            )
            logger.debug("Camera command sent: %r", msg.strip())
        except Exception as exc:
            self.status_updated.emit(f"CAM SEND ERROR: {exc}")
            logger.error("Camera send error: %s", exc)

    # ------------------------------------------------------------------
    # Listen thread — receives camera azimuth responses
    # ------------------------------------------------------------------

    def start_listening(self):
        """Start background UDP listener for camera responses."""
        if self._running or not self.config.get('enabled', False):
            return
        self._running = True
        self._listen_thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="camera-listen"
        )
        self._listen_thread.start()

    def stop_listening(self):
        """Stop the UDP listener."""
        self._running = False
        if self._sock_recv:
            try:
                self._sock_recv.close()
            except OSError:
                pass

    def _listen_loop(self):
        listen_port = int(self.config.get('listen_port', 10121))
        try:
            self._sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock_recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock_recv.bind(('0.0.0.0', listen_port))
            self._sock_recv.settimeout(1.0)
            logger.info("Camera listener bound to port %d", listen_port)
            self.connection_changed.emit(True)
            self.status_updated.emit(f"Camera listener started on port {listen_port}")
        except Exception as exc:
            logger.error("Camera listener bind error: %s", exc)
            self.status_updated.emit(f"CAM LISTEN ERROR: {exc}")
            self._running = False
            self.connection_changed.emit(False)
            return

        while self._running:
            try:
                data, _addr = self._sock_recv.recvfrom(256)
                sentence = data.decode('ascii', errors='replace').strip()
                azimuth = self.parse_response(sentence)
                if azimuth is not None:
                    self.current_azimuth = azimuth
                    self.azimuth_updated.emit(azimuth)
                    logger.debug("Camera azimuth received: %.1f°", azimuth)
            except socket.timeout:
                continue
            except Exception as exc:
                if self._running:
                    logger.error("Camera receive error: %s", exc)

        self.connection_changed.emit(False)
        logger.info("Camera listener stopped")
