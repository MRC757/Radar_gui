"""
ADS-B / FLARM Receiver
Receives FLARM-standard NMEA sentences ($PFLAA, $PFLAU) over UDP and
converts aircraft positions from receiver-relative meters to absolute
lat/lon using own ship's GPS position.

$PFLAA sentence format:
  $PFLAA,<AlarmLevel>,<RelativeNorth>,<RelativeEast>,<RelativeVertical>,
         <IDType>,<ID>,<Track>,<TurnRate>,<GroundSpeed>,<ClimbRate>,
         <AircraftType>*<Checksum>

  AlarmLevel : 0=none, 1=low, 2=important, 3=urgent
  RelativeNorth/East : metres from own ship (positive = N/E)
  RelativeVertical   : metres altitude difference (positive = above)
  IDType  : 1=ICAO 24-bit, 2=FLARM, 3=OGN
  ID      : 6-char hex address
  Track   : true heading 0-359 (degrees)
  GroundSpeed : m/s
  AircraftType: 0=unknown … 8=piston, 9=jet, etc.
"""

import json
import logging
import math
import os
import socket
import threading
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from core.multi_source_nmea_parser import NMEASource

logger = logging.getLogger(__name__)

_CONFIG_FILE = 'nmea_config.json'
_STALE_SECONDS = 15.0          # aircraft removed after this many seconds without update
_PRUNE_INTERVAL = 5.0          # staleness check interval (seconds)
_DEFAULT_PORT = 10117


# ---------------------------------------------------------------------------
# AdsbReceiver
# ---------------------------------------------------------------------------

class AdsbReceiver(QObject):
    """
    Multi-source UDP listener that parses FLARM/ADS-B NMEA sentences and
    publishes aircraft tracks to the PPI display.
    """

    targets_updated = pyqtSignal(list)   # list of target dicts
    status_updated  = pyqtSignal(str)    # human-readable log/status message

    def __init__(self):
        super().__init__()

        self.own_lat = 0.0
        self.own_lon = 0.0

        self._targets = {}           # icao_id (str) → target dict
        self._lock = threading.Lock()

        self.adsb_sources = []       # list of NMEASource
        self._running = False
        self._threads = []

        self.load_config()

    # ------------------------------------------------------------------
    # Own-ship position update
    # ------------------------------------------------------------------

    def set_own_position(self, lat: float, lon: float):
        """Update own ship position used for relative→absolute conversion."""
        self.own_lat = lat
        self.own_lon = lon

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_config(self):
        """Load adsb source list from nmea_config.json."""
        if not os.path.exists(_CONFIG_FILE):
            self._setup_defaults()
            return
        try:
            with open(_CONFIG_FILE, 'r') as fh:
                data = json.load(fh)
            for src in data.get('adsb', []):
                addr = src.get('listen_address', src.get('ip', '0.0.0.0'))
                self.adsb_sources.append(NMEASource(
                    src.get('name', 'ADS-B'),
                    addr,
                    int(src.get('port', _DEFAULT_PORT)),
                    int(src.get('priority', 1)),
                    bool(src.get('enabled', True)),
                ))
            logger.info("ADS-B: loaded %d source(s)", len(self.adsb_sources))
        except Exception as exc:
            logger.error("ADS-B config load error: %s", exc)
            self._setup_defaults()

    def _setup_defaults(self):
        self.adsb_sources = [
            NMEASource('ADS-B 1', '0.0.0.0', _DEFAULT_PORT, 1, True)
        ]

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start_listening(self):
        """Spawn UDP listener threads for all enabled ADS-B sources."""
        if self._running:
            return
        self._running = True

        enabled = [s for s in self.adsb_sources if s.enabled]
        if not enabled:
            logger.info("ADS-B: no enabled sources, listener not started")
            return

        # Deduplicate by address:port
        seen = {}
        for src in enabled:
            key = f"{src.listen_address}:{src.port}"
            if key not in seen:
                seen[key] = src

        for src in seen.values():
            t = threading.Thread(
                target=self._listen_to_source,
                args=(src,),
                daemon=True,
                name=f"adsb-{src.port}",
            )
            t.start()
            self._threads.append(t)

        # Stale-target pruning thread
        prune_t = threading.Thread(
            target=self._prune_loop,
            daemon=True,
            name="adsb-prune",
        )
        prune_t.start()
        self._threads.append(prune_t)

        logger.info("ADS-B: started %d listener thread(s)", len(seen))
        self.status_updated.emit(f"ADS-B listener started on {list(seen.keys())}")

    def stop_listening(self):
        """Stop all UDP listeners and the prune thread."""
        self._running = False
        for src in self.adsb_sources:
            if src.socket:
                try:
                    src.socket.close()
                except Exception:
                    pass
        logger.info("ADS-B: listener stopped")

    # ------------------------------------------------------------------
    # UDP listener thread
    # ------------------------------------------------------------------

    def _listen_to_source(self, source: NMEASource):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            sock.bind((source.listen_address, source.port))
            sock.settimeout(1.0)
            source.socket = sock
            logger.info("ADS-B listening on %s:%d", source.listen_address, source.port)
        except Exception as exc:
            logger.error("ADS-B bind error on %s:%d: %s",
                         source.listen_address, source.port, exc)
            self.status_updated.emit(f"ADS-B LISTEN ERROR: {exc}")
            return

        while self._running:
            try:
                data, _addr = sock.recvfrom(4096)
                raw = data.decode('ascii', errors='ignore')
                for line in raw.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
                    sentence = line.strip()
                    if sentence:
                        self.parse_sentence(sentence, source)
                        source.last_data_time = datetime.now()
                        source.data_count += 1
            except socket.timeout:
                continue
            except Exception as exc:
                if self._running:
                    source.error_count += 1
                    if source.error_count % 100 == 0:
                        logger.error("ADS-B recv error: %s", exc)

    # ------------------------------------------------------------------
    # Sentence parsing
    # ------------------------------------------------------------------

    def parse_sentence(self, sentence: str, source=None):
        """Dispatch a raw NMEA sentence to the appropriate handler."""
        if not sentence.startswith('$'):
            return
        # Strip checksum
        core = sentence[1:]
        if '*' in core:
            core = core[:core.index('*')]
        parts = core.split(',')
        if not parts:
            return

        talker = parts[0].upper()
        if talker == 'PFLAA':
            self._parse_pflaa(parts)
        elif talker == 'PFLAU':
            self._parse_pflau(parts)

    def _parse_pflaa(self, parts: list):
        """
        Parse a $PFLAA position record and store/update the target.

        Fields (1-based after talker):
          1  AlarmLevel
          2  RelativeNorth (m)
          3  RelativeEast  (m)
          4  RelativeVertical (m)
          5  IDType
          6  ID  (hex)
          7  Track (degrees true)
          8  TurnRate
          9  GroundSpeed (m/s)
          10 ClimbRate
          11 AircraftType
        """
        if len(parts) < 7:
            return
        try:
            alarm_level   = int(parts[1])   if parts[1]  else 0
            rel_north     = float(parts[2]) if parts[2]  else 0.0
            rel_east      = float(parts[3]) if parts[3]  else 0.0
            rel_vert      = int(float(parts[4])) if parts[4] else 0
            icao_id       = parts[6].strip().upper() if parts[6] else 'UNKNOWN'
            track         = float(parts[7]) if len(parts) > 7 and parts[7] else 0.0
            speed_ms      = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0
            aircraft_type = int(parts[11]) if len(parts) > 11 and parts[11] else 0
        except (ValueError, IndexError) as exc:
            logger.debug("PFLAA parse error: %s  parts=%s", exc, parts)
            return

        # Convert relative metres to absolute lat/lon
        own_lat = self.own_lat
        own_lon = self.own_lon
        if own_lat == 0.0 and own_lon == 0.0:
            # Own position not yet known — still store with placeholder coords
            tgt_lat = 0.0
            tgt_lon = 0.0
        else:
            tgt_lat = own_lat + rel_north / 111320.0
            cos_lat = math.cos(math.radians(own_lat))
            tgt_lon = own_lon + rel_east / (111320.0 * cos_lat if cos_lat else 1.0)

        speed_kts = speed_ms * 1.94384

        target = {
            'id':            icao_id,
            'lat':           tgt_lat,
            'lon':           tgt_lon,
            'alt_rel_m':     rel_vert,
            'track':         track,
            'speed_ms':      speed_ms,
            'speed_kts':     speed_kts,
            'alarm_level':   alarm_level,
            'aircraft_type': aircraft_type,
            'last_update':   datetime.now(),
        }

        with self._lock:
            self._targets[icao_id] = target
            snapshot = list(self._targets.values())

        self.targets_updated.emit(snapshot)

    def _parse_pflau(self, parts: list):
        """
        Parse $PFLAU receiver status sentence.
        Fields: RX,TX,GPS,Power,AlarmLevel,RelBearing,AlarmType,RelVert,RelDist,ID
        Only used for logging; no target plotted.
        """
        if len(parts) < 5:
            return
        try:
            rx_count  = int(parts[1]) if parts[1] else 0
            gps_ok    = int(parts[3]) if parts[3] else 0
            alarm_lvl = int(parts[5]) if len(parts) > 5 and parts[5] else 0
            logger.debug("PFLAU: RX=%d GPS=%d alarm=%d", rx_count, gps_ok, alarm_lvl)
        except (ValueError, IndexError):
            pass

    # ------------------------------------------------------------------
    # Stale-target pruning
    # ------------------------------------------------------------------

    def _prune_loop(self):
        """Background thread: remove aircraft not heard from recently."""
        while self._running:
            threading.Event().wait(_PRUNE_INTERVAL)
            if not self._running:
                break
            self._prune_stale()

    def _prune_stale(self):
        now = datetime.now()
        pruned = False
        with self._lock:
            stale = [
                k for k, v in self._targets.items()
                if (now - v['last_update']).total_seconds() > _STALE_SECONDS
            ]
            for k in stale:
                del self._targets[k]
                pruned = True
            snapshot = list(self._targets.values())

        if pruned:
            self.targets_updated.emit(snapshot)
