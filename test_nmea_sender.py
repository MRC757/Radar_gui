#!/usr/bin/env python3
"""
Test NMEA Data Generator — Multi-Rate
Simulates Perle IOLAN terminal server output by sending NMEA-0183
sentences via UDP to the radar application.

Message rates (typical of real installations):
  GGA, VTG, HDT      -> 10 Hz  (high-rate navigation)
  RMC                 -> 1 Hz   (recommended minimum)
  ZDA                 -> 1 Hz   (UTC time/date)
  DBT / DPT           -> 2 Hz   (depth sounder)
  ROT                 -> 2 Hz   (rate of turn)
  MWV                 -> 1 Hz   (wind)
  MTW                 -> 0.2 Hz (water temperature, every 5 s)

Default ports match the application defaults:
  GPS  (GGA, VTG, RMC, ZDA)  -> UDP 10110
  Gyro (HDT, ROT)            -> UDP 10111
  Depth (DBT)                -> UDP 10112
  AIS  (AIVDM)               -> UDP 10113
"""

import logging
import socket
import time
import math
from datetime import datetime, timezone

from core.ais_decrypt import encrypt_ais_payload

logger = logging.getLogger(__name__)


def generate_nmea_checksum(sentence):
    """Calculate NMEA checksum"""
    checksum = 0
    for char in sentence[1:]:  # Skip the $
        checksum ^= ord(char)
    return f"{checksum:02X}"


def make_sentence(body):
    """Build a complete NMEA sentence with checksum and CRLF."""
    cs = generate_nmea_checksum(body)
    return f"{body}*{cs}\r\n"


# ------------------------------------------------------------------
# AIS AIVDM encoder  (ITU-R M.1371 6-bit payload encoding)
# ------------------------------------------------------------------

def _ais_encode_payload(bits: list[int]) -> tuple[str, int]:
    """Encode a bit-vector into 6-bit ASCII-armored AIVDM payload.

    Returns (payload_string, pad_bit_count).
    """
    # Pad to multiple of 6
    pad = (6 - len(bits) % 6) % 6
    bits = bits + [0] * pad
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


def _int_to_bits(value: int, length: int) -> list[int]:
    """Convert integer to bit list (MSB first, two's complement for negatives)."""
    if value < 0:
        value = (1 << length) + value
    return [(value >> (length - 1 - i)) & 1 for i in range(length)]


def encode_ais_msg1(mmsi: int, nav_status: int, sog: float,
                    lon: float, lat: float, cog: float,
                    heading: float, timestamp_sec: int = 0) -> str:
    """Build an AIVDM sentence for a Type 1 (Class A position report)."""
    bits = []
    bits += _int_to_bits(1, 6)            # msg type
    bits += _int_to_bits(0, 2)            # repeat indicator
    bits += _int_to_bits(mmsi, 30)        # MMSI
    bits += _int_to_bits(nav_status, 4)   # nav status
    bits += _int_to_bits(0, 8)            # rate of turn (not available)
    bits += _int_to_bits(int(sog * 10), 10)  # SOG in 1/10 knot
    bits += _int_to_bits(0, 1)            # position accuracy
    bits += _int_to_bits(int(lon * 600000), 28)  # longitude
    bits += _int_to_bits(int(lat * 600000), 27)  # latitude
    bits += _int_to_bits(int(cog * 10), 12)      # COG in 1/10 deg
    bits += _int_to_bits(int(heading) % 360, 9)  # true heading
    bits += _int_to_bits(timestamp_sec, 6)        # UTC second
    bits += _int_to_bits(0, 2)            # manoeuvre indicator
    bits += _int_to_bits(0, 3)            # spare
    bits += _int_to_bits(0, 1)            # RAIM flag
    bits += _int_to_bits(0, 19)           # radio status

    payload, pad = _ais_encode_payload(bits)
    body = f"!AIVDM,1,1,,A,{payload},{pad}"
    cs = generate_nmea_checksum(body)
    return f"{body}*{cs}\r\n"


def encode_ais_msg5(mmsi: int, name: str, ship_type: int = 70,
                    call_sign: str = '', destination: str = '') -> list[str]:
    """Build a 2-sentence AIVDM for Type 5 (Class A static/voyage).

    Returns a list of 2 sentence strings.
    """
    def _text_to_bits(text: str, n_chars: int) -> list[int]:
        ais_chars = "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_ !\"#$%&'()*+,-./0123456789:;<=>?"
        bits = []
        padded = text.upper().ljust(n_chars, '@')[:n_chars]
        for ch in padded:
            idx = ais_chars.find(ch)
            if idx < 0:
                idx = 0
            bits += _int_to_bits(idx, 6)
        return bits

    bits = []
    bits += _int_to_bits(5, 6)             # msg type
    bits += _int_to_bits(0, 2)             # repeat
    bits += _int_to_bits(mmsi, 30)         # MMSI
    bits += _int_to_bits(0, 2)             # AIS version
    bits += _int_to_bits(mmsi % 10000000, 30)  # IMO number (fake)
    bits += _text_to_bits(call_sign, 7)    # call sign
    bits += _text_to_bits(name, 20)        # ship name
    bits += _int_to_bits(ship_type, 8)     # ship type
    bits += _int_to_bits(10, 9)            # dim A (bow)
    bits += _int_to_bits(10, 9)            # dim B (stern)
    bits += _int_to_bits(5, 6)             # dim C (port)
    bits += _int_to_bits(5, 6)             # dim D (starboard)
    bits += _int_to_bits(1, 4)             # fix type (GPS)
    bits += _int_to_bits(0, 4)             # ETA month
    bits += _int_to_bits(0, 5)             # ETA day
    bits += _int_to_bits(0, 5)             # ETA hour
    bits += _int_to_bits(0, 6)             # ETA minute
    bits += _int_to_bits(80, 8)            # draught (8.0m)
    bits += _text_to_bits(destination, 20) # destination
    bits += _int_to_bits(0, 1)             # DTE
    bits += _int_to_bits(0, 1)             # spare

    # Total should be 424 bits — split into two sentences
    payload, pad = _ais_encode_payload(bits)

    # Split roughly at character boundary: first ~38 chars, rest
    split = len(payload) // 2
    p1, p2 = payload[:split], payload[split:]

    body1 = f"!AIVDM,2,1,1,A,{p1},0"
    cs1 = generate_nmea_checksum(body1)
    body2 = f"!AIVDM,2,2,1,A,{p2},{pad}"
    cs2 = generate_nmea_checksum(body2)
    return [f"{body1}*{cs1}\r\n", f"{body2}*{cs2}\r\n"]


# Simulated AIS targets (relative to Chesapeake Bay own-ship position)
AIS_TARGETS = [
    {
        'mmsi': 211235000, 'name': 'EVER GIVEN',    'call_sign': 'VRCH4',
        'ship_type': 70,   'base_lat': 37.02, 'base_lon': -76.28,
        'course': 225.0,   'speed': 14.0,  'nav_status': 0,
    },
    {
        'mmsi': 366999001, 'name': 'TUG RESOLUTE',  'call_sign': 'WDB9876',
        'ship_type': 52,   'base_lat': 36.99, 'base_lon': -76.31,
        'course': 60.0,    'speed': 8.0,   'nav_status': 0,
    },
    {
        'mmsi': 338123456, 'name': 'FISHING EAGLE',  'call_sign': 'WDE4321',
        'ship_type': 30,   'base_lat': 37.005, 'base_lon': -76.295,
        'course': 180.0,   'speed': 5.5,   'nav_status': 0,
    },
    {
        'mmsi': 477000111, 'name': 'HONG KONG STAR', 'call_sign': 'VRAA1',
        'ship_type': 71,   'base_lat': 37.03, 'base_lon': -76.32,
        'course': 45.0,    'speed': 18.0,  'nav_status': 0,
    },
    {
        'mmsi': 244123000, 'name': 'DUTCH PRIDE',    'call_sign': 'PBAA',
        'ship_type': 80,   'base_lat': 36.985, 'base_lon': -76.285,
        'course': 350.0,   'speed': 11.0,  'nav_status': 0,
    },
]

# Test AES-128 key for encrypted AIS (must match key in ais_encrypt_config.json)
SA_AIS_TEST_KEY = '0123456789ABCDEF0123456789ABCDEF'  # 32 hex = AES-128

# Encrypted AIS targets (SA-AIS) — same format but sent through AES-CBC
ENCRYPTED_AIS_TARGETS = [
    {
        'mmsi': 555000001, 'name': 'GHOST RIDER',  'call_sign': 'SECR1',
        'ship_type': 35,   'base_lat': 37.015, 'base_lon': -76.305,
        'course': 135.0,   'speed': 16.0,  'nav_status': 0,
    },
    {
        'mmsi': 555000002, 'name': 'SHADOW OPS',   'call_sign': 'SECR2',
        'ship_type': 90,   'base_lat': 36.995, 'base_lon': -76.275,
        'course': 310.0,   'speed': 22.0,  'nav_status': 0,
    },
]


# Default ports (match application defaults for Perle IOLAN setup)
GPS_PORT = 10110
HDG_PORT = 10111
DEPTH_PORT = 10112
AIS_PORT = 10113
TARGET_IP = '127.0.0.1'


def send_nmea_data():
    """Send test NMEA data on separate ports with realistic multi-rate timing.

    High-rate sentences (GGA, VTG, HDT) send every 100 ms (10 Hz).
    Medium-rate sentences (DBT, ROT) send every 500 ms (2 Hz).
    Low-rate sentences (RMC, ZDA, MWV) send every 1000 ms (1 Hz).
    Slow sentences (MTW) send every 5000 ms (0.2 Hz).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Simulated position (Chesapeake Bay area)
    base_lat = 37.0
    base_lon = -76.3
    heading = 45.0
    speed = 12.0
    depth = 15.0
    rate_of_turn = 2.5       # deg/min
    wind_angle = 135.0       # degrees relative
    wind_speed_kts = 18.0    # knots
    water_temp = 22.4        # Celsius

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s: %(message)s",
                        datefmt="%H:%M:%S")
    logger.info("Sending multi-rate NMEA data to %s", TARGET_IP)
    logger.info("  GPS  (GGA/VTG/RMC/ZDA) -> port %d  (10/10/1/1 Hz)", GPS_PORT)
    logger.info("  Gyro (HDT/ROT)         -> port %d  (10/2 Hz)", HDG_PORT)
    logger.info("  Depth (DBT)            -> port %d  (2 Hz)", DEPTH_PORT)
    logger.info("  Wind/Temp (MWV/MTW)    -> port %d  (1/0.2 Hz)", GPS_PORT)
    logger.info("  AIS  (AIVDM x%d + %d SA-AIS) -> port %d  (0.33 Hz position)",
                len(AIS_TARGETS), len(ENCRYPTED_AIS_TARGETS), AIS_PORT)
    logger.info("Press Ctrl+C to stop")

    # Timing counters (in 100 ms ticks)
    tick = 0

    try:
        while True:
            timestamp = time.time()
            tick += 1

            # Update simulated position (slow circular drift)
            lat = base_lat + 0.001 * math.sin(timestamp / 10.0)
            lon = base_lon + 0.001 * math.cos(timestamp / 10.0)

            # Slowly vary heading
            heading = 45.0 + 10.0 * math.sin(timestamp / 30.0)

            # Format coordinates
            lat_deg = int(abs(lat))
            lat_min = (abs(lat) - lat_deg) * 60
            lat_dir = 'N' if lat >= 0 else 'S'
            lat_str = f"{lat_deg:02d}{lat_min:07.4f}"

            lon_deg = int(abs(lon))
            lon_min = (abs(lon) - lon_deg) * 60
            lon_dir = 'E' if lon >= 0 else 'W'
            lon_str = f"{lon_deg:03d}{lon_min:07.4f}"

            # UTC time string for sentences
            utc = datetime.now(timezone.utc)
            utc_str = utc.strftime("%H%M%S.%f")[:9]  # HHMMSS.ss

            # ============================================================
            # 10 Hz sentences — every tick
            # ============================================================

            # GGA — Position
            gga = (f"$GPGGA,{utc_str},{lat_str},{lat_dir},"
                   f"{lon_str},{lon_dir},1,08,0.9,545.4,M,46.9,M,,")
            sock.sendto(make_sentence(gga).encode(), (TARGET_IP, GPS_PORT))

            # VTG — Speed/Course
            vtg = (f"$GPVTG,{heading:.1f},T,{heading:.1f},M,"
                   f"{speed:.1f},N,{speed * 1.852:.1f},K")
            sock.sendto(make_sentence(vtg).encode(), (TARGET_IP, GPS_PORT))

            # HDT — True Heading
            hdt = f"$HEHDT,{heading:.1f},T"
            sock.sendto(make_sentence(hdt).encode(), (TARGET_IP, HDG_PORT))

            # ============================================================
            # 2 Hz sentences — every 5th tick (500 ms)
            # ============================================================
            if tick % 5 == 0:
                # DBT — Depth Below Transducer
                depth_feet = depth * 3.28084
                dbt = (f"$SDDBT,{depth_feet:.1f},f,{depth:.1f},M,"
                       f"{depth * 0.546807:.1f},F")
                sock.sendto(make_sentence(dbt).encode(),
                            (TARGET_IP, DEPTH_PORT))

                # ROT — Rate of Turn
                rot = f"$HEROT,{rate_of_turn:.1f},A"
                sock.sendto(make_sentence(rot).encode(),
                            (TARGET_IP, HDG_PORT))

                # VHW — Water Speed and Heading
                # STW is typically ~1-2 kts less than SOG due to current
                stw = max(0.0, speed - 1.5 + 0.3 * math.sin(timestamp / 20.0))
                vhw = (f"$VWVHW,{heading:.1f},T,{heading:.1f},M,"
                       f"{stw:.1f},N,{stw * 1.852:.1f},K")
                sock.sendto(make_sentence(vhw).encode(),
                            (TARGET_IP, HDG_PORT))

            # ============================================================
            # 1 Hz sentences — every 10th tick (1000 ms)
            # ============================================================
            if tick % 10 == 0:
                # RMC — Recommended Minimum
                date_str = utc.strftime("%d%m%y")
                rmc = (f"$GPRMC,{utc_str},A,{lat_str},{lat_dir},"
                       f"{lon_str},{lon_dir},{speed:.1f},{heading:.1f},"
                       f"{date_str},3.1,W")
                sock.sendto(make_sentence(rmc).encode(),
                            (TARGET_IP, GPS_PORT))

                # ZDA — Time & Date
                zda = (f"$GPZDA,{utc_str},{utc.day:02d},{utc.month:02d},"
                       f"{utc.year},00,00")
                sock.sendto(make_sentence(zda).encode(),
                            (TARGET_IP, GPS_PORT))

                # MWV — Wind Speed and Angle (relative)
                mwv = (f"$WIMWV,{wind_angle:.1f},R,"
                       f"{wind_speed_kts:.1f},N,A")
                sock.sendto(make_sentence(mwv).encode(),
                            (TARGET_IP, GPS_PORT))

                # GLL — Geographic Position
                gll = (f"$GPGLL,{lat_str},{lat_dir},{lon_str},{lon_dir},"
                       f"{utc_str},A")
                sock.sendto(make_sentence(gll).encode(),
                            (TARGET_IP, GPS_PORT))

            # ============================================================
            # 0.2 Hz sentences — every 50th tick (5000 ms)
            # ============================================================
            if tick % 50 == 0:
                # MTW — Water Temperature
                mtw = f"$YXMTW,{water_temp:.1f},C"
                sock.sendto(make_sentence(mtw).encode(),
                            (TARGET_IP, GPS_PORT))

                logger.info(
                    "Lat=%.6f Lon=%.6f Hdg=%.1f° Spd=%.1fkts "
                    "Depth=%.1fm ROT=%.1f°/min Wind=%.0f°/%.0fkts "
                    "WaterT=%.1f°C  [tick %d]",
                    lat, lon, heading, speed, depth,
                    rate_of_turn, wind_angle, wind_speed_kts,
                    water_temp, tick)

            # ============================================================
            # AIS — position reports every 30th tick (3 s) + static at start
            # ============================================================
            if tick % 30 == 0:
                for tgt in AIS_TARGETS:
                    # Move targets slowly along their course
                    elapsed_nm = tgt['speed'] * (timestamp / 3600.0)
                    crs_rad = math.radians(tgt['course'])
                    dlat = (elapsed_nm * math.cos(crs_rad)) / 60.0
                    dlon = (elapsed_nm * math.sin(crs_rad)) / (
                        60.0 * math.cos(math.radians(tgt['base_lat'])))
                    # Wrap position to stay near base (modular drift)
                    t_lat = tgt['base_lat'] + (dlat % 0.05)
                    t_lon = tgt['base_lon'] + (dlon % 0.05)

                    msg = encode_ais_msg1(
                        tgt['mmsi'], tgt['nav_status'], tgt['speed'],
                        t_lon, t_lat, tgt['course'],
                        tgt['course'], int(timestamp) % 60)
                    sock.sendto(msg.encode(), (TARGET_IP, AIS_PORT))

            # Encrypted AIS (SA-AIS) position reports — same rate as normal
            if tick % 30 == 0:
                for tgt in ENCRYPTED_AIS_TARGETS:
                    elapsed_nm = tgt['speed'] * (timestamp / 3600.0)
                    crs_rad = math.radians(tgt['course'])
                    dlat = (elapsed_nm * math.cos(crs_rad)) / 60.0
                    dlon = (elapsed_nm * math.sin(crs_rad)) / (
                        60.0 * math.cos(math.radians(tgt['base_lat'])))
                    t_lat = tgt['base_lat'] + (dlat % 0.05)
                    t_lon = tgt['base_lon'] + (dlon % 0.05)

                    # Encode then encrypt the AIS payload
                    plain_sentence = encode_ais_msg1(
                        tgt['mmsi'], tgt['nav_status'], tgt['speed'],
                        t_lon, t_lat, tgt['course'],
                        tgt['course'], int(timestamp) % 60)
                    # Extract payload and pad from the AIVDM sentence
                    p_parts = plain_sentence.split(',')
                    p_payload = p_parts[5]
                    p_pad = int(p_parts[6].split('*')[0])
                    enc_payload, enc_pad = encrypt_ais_payload(
                        p_payload, p_pad, SA_AIS_TEST_KEY)
                    # Rebuild AIVDM sentence with encrypted payload
                    enc_body = f"!AIVDM,1,1,,A,{enc_payload},{enc_pad}"
                    enc_cs = generate_nmea_checksum(enc_body)
                    sock.sendto(f"{enc_body}*{enc_cs}\r\n".encode(),
                                (TARGET_IP, AIS_PORT))

            # AIS static/voyage data — send once at start, then every 300 ticks
            if tick == 1 or tick % 300 == 0:
                for tgt in AIS_TARGETS:
                    sentences = encode_ais_msg5(
                        tgt['mmsi'], tgt['name'],
                        tgt['ship_type'], tgt['call_sign'])
                    for s in sentences:
                        sock.sendto(s.encode(), (TARGET_IP, AIS_PORT))

            time.sleep(0.1)  # 100 ms base tick = 10 Hz

    except KeyboardInterrupt:
        logger.info("Stopped sending NMEA data")
    finally:
        sock.close()


if __name__ == '__main__':
    send_nmea_data()
