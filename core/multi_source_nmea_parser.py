"""
Multi-Source NMEA Parser with Priority Management
Handles multiple NMEA-0183 sources via UDP with automatic failover.

Designed for use with Perle IOLAN Terminal Servers that convert
RS-422/RS-232 serial NMEA-0183 instrument data to UDP/IP.

Typical IOLAN configuration:
  - Each serial port on the IOLAN maps to a unique UDP destination port
  - IOLAN sends raw NMEA sentences as UDP payloads to this application
  - Listen address should be 0.0.0.0 (all interfaces) in most installations
"""

import logging
import socket
import time
import threading
from PyQt6.QtCore import QObject, pyqtSignal
import json
import os
from datetime import datetime, timedelta
from core.ais_decrypt import AISDecryptor

from core.gps_spoofing_detector import GPSSpoofingDetector

logger = logging.getLogger(__name__)


class NMEASource:
    """Individual NMEA source (typically one port on a Perle IOLAN)"""

    def __init__(self, name, listen_address, port, priority, enabled=True):
        self.name = name
        self.listen_address = listen_address  # local bind address (0.0.0.0 = all)
        self.port = port
        self.priority = priority
        self.enabled = enabled
        self.last_data_time = None
        self.data_count = 0
        self.error_count = 0
        self.socket = None

    # Keep .ip as alias for backward-compat with saved configs
    @property
    def ip(self):
        return self.listen_address

    @ip.setter
    def ip(self, value):
        self.listen_address = value

    def mark_data(self):
        """Record that data arrived (monotonic clock — immune to clock changes)."""
        self.last_data_time = time.monotonic()
        self.data_count += 1

    def is_active(self, timeout_seconds=5):
        """Check if source is active (received data recently)"""
        if not self.last_data_time:
            return False
        return (time.monotonic() - self.last_data_time) < timeout_seconds


class MultiSourceNMEAParser(QObject):
    """Parse NMEA-0183 from multiple sources with priority management"""
    
    # Signals for data updates
    position_updated = pyqtSignal(float, float, float, str)  # lat, lon, speed, source_name
    heading_updated = pyqtSignal(float, str)  # heading, source_name
    depth_updated = pyqtSignal(float, str)  # depth, source_name
    ais_updated = pyqtSignal(list)  # list of AIS targets
    source_status_updated = pyqtSignal(dict)  # source status information
    time_updated = pyqtSignal(str, str)  # utc_time, utc_date (HH:MM:SS, YYYY-MM-DD)
    rot_updated = pyqtSignal(float)  # rate of turn in deg/min
    wind_updated = pyqtSignal(float, float, str)  # angle, speed_kts, reference (R/T)
    water_temp_updated = pyqtSignal(float)  # water temperature in Celsius
    stw_updated = pyqtSignal(float)  # speed through water in knots
    sentence_received = pyqtSignal(str, str)  # source_name, raw_sentence
    base_stations_updated = pyqtSignal(list)  # list of AIS base station dicts (Type 4)
    cog_updated = pyqtSignal(float, float)  # course over ground (deg true), SOG (kts)

    # AIS target lifetime.  A Class A ship at anchor reports every 3 min and a
    # Class B unit can be similar, so a target with no position report for
    # 6 min is considered lost and removed (it would otherwise be frozen at
    # its last position while CPA is computed against it).
    AIS_TARGET_TIMEOUT_S = 360.0
    AIS_STATIC_TIMEOUT_S = 1800.0
    AIS_BASE_STATION_TIMEOUT_S = 600.0
    AIS_PUBLISH_INTERVAL_S = 1.0
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.threads = []
        
        # Source lists
        self.gps_sources = []
        self.heading_sources = []
        self.depth_sources = []
        self.ais_sources = []
        
        # Current state
        self.latitude = 0.0
        self.longitude = 0.0
        self.speed = 0.0            # primary speed (SOG preferred)
        self.speed_over_ground = 0.0   # SOG from RMC/VTG
        self.speed_through_water = 0.0 # STW from VHW
        self.heading = 0.0
        self.depth = 0.0
        self.course = 0.0           # COG (from RMC/VTG)
        self.utc_time = ""          # HH:MM:SS
        self.utc_date = ""          # YYYY-MM-DD
        self.rate_of_turn = 0.0     # deg/min (from ROT)
        self.wind_angle = 0.0       # degrees (from MWV)
        self.wind_speed = 0.0       # knots  (from MWV)
        self.wind_reference = "R"   # R=relative, T=true
        self.water_temp = 0.0       # Celsius (from MTW)
        self.ais_targets = {}
        self.ais_base_stations = {}   # mmsi -> dict (Type 4 messages; never passed to track manager)
        self._ais_static = {}         # mmsi -> static/voyage data, merged into position reports
        self._ais_dirty = False       # True when targets changed since last publish
        self._base_dirty = False
        self.magnetic_variation = None  # degrees (+E / -W) from RMC, used by HDG
        self._warned_no_variation = False
        self._ais_lock = threading.Lock()

        # Encrypted AIS decryptor
        self.ais_decryptor = AISDecryptor()
        self.ais_decryptor.load_keys()

        # Active sources
        self.active_gps_source = None
        self.active_heading_source = None
        self.active_depth_source = None

        # GPS spoofing detector
        self.spoofing_detector = GPSSpoofingDetector()

        # Load configuration
        self.load_config()
        
    def load_config(self):
        """Load NMEA source configuration"""
        config_file = 'nmea_config.json'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    
                # Load GPS sources
                for src in config.get('gps', []):
                    addr = src.get('listen_address', src.get('ip', '0.0.0.0'))
                    self.gps_sources.append(NMEASource(
                        src['name'], addr, src['port'],
                        src['priority'], src['enabled']
                    ))

                # Load heading sources
                for src in config.get('heading', []):
                    addr = src.get('listen_address', src.get('ip', '0.0.0.0'))
                    self.heading_sources.append(NMEASource(
                        src['name'], addr, src['port'],
                        src['priority'], src['enabled']
                    ))

                # Load depth sources
                for src in config.get('depth', []):
                    addr = src.get('listen_address', src.get('ip', '0.0.0.0'))
                    self.depth_sources.append(NMEASource(
                        src['name'], addr, src['port'],
                        src['priority'], src['enabled']
                    ))

                # Load AIS sources
                for src in config.get('ais', []):
                    addr = src.get('listen_address', src.get('ip', '0.0.0.0'))
                    self.ais_sources.append(NMEASource(
                        src['name'], addr, src['port'],
                        src['priority'], src['enabled']
                    ))
                    
                logger.info("Loaded NMEA config: %d GPS, %d heading, %d depth, %d AIS sources",
                            len(self.gps_sources), len(self.heading_sources),
                            len(self.depth_sources), len(self.ais_sources))
                      
            except Exception as e:
                logger.error("Error loading NMEA config: %s", e)
                self.setup_default_sources()
        else:
            self.setup_default_sources()
            
    def setup_default_sources(self):
        """Setup default NMEA sources for Perle IOLAN terminal servers"""
        self.gps_sources = [NMEASource("GPS 1", "0.0.0.0", 10110, 1, True)]
        self.heading_sources = [NMEASource("Gyro 1", "0.0.0.0", 10111, 1, True)]
        self.depth_sources = [NMEASource("Depth 1", "0.0.0.0", 10112, 1, True)]
        self.ais_sources = [NMEASource("AIS 1", "0.0.0.0", 10113, 1, True)]
        
    def start_listening(self):
        """Start listening to all configured sources"""
        self.running = True
        
        # Start threads for each source type
        all_sources = (self.gps_sources + self.heading_sources + 
                      self.depth_sources + self.ais_sources)
        
        # Deduplicate by listen_address:port combination
        unique_sources = {}
        for source in all_sources:
            if source.enabled:
                key = f"{source.listen_address}:{source.port}"
                if key not in unique_sources:
                    unique_sources[key] = source
                    
        # Start listener thread for each unique source
        for key, source in unique_sources.items():
            thread = threading.Thread(
                target=self._listen_to_source,
                args=(source,),
                daemon=True
            )
            thread.start()
            self.threads.append(thread)
            
        logger.info("Started %d NMEA listener threads", len(unique_sources))
        
        # Start source monitoring thread
        monitor_thread = threading.Thread(
            target=self._monitor_sources,
            daemon=True
        )
        monitor_thread.start()
        self.threads.append(monitor_thread)

        # AIS publisher: prunes lost targets and publishes at most once per
        # AIS_PUBLISH_INTERVAL_S, instead of once per received AIS message.
        ais_thread = threading.Thread(target=self._ais_publisher, daemon=True)
        ais_thread.start()
        self.threads.append(ais_thread)
        
    def stop_listening(self):
        """Stop listening"""
        self.running = False
        
        # Close all sockets
        for source in (self.gps_sources + self.heading_sources + 
                      self.depth_sources + self.ais_sources):
            if source.socket:
                try:
                    source.socket.close()
                except OSError:
                    pass
                    
        # Wait for threads
        for thread in self.threads:
            thread.join(timeout=1.0)
            
    def _listen_to_source(self, source):
        """Listen to a specific NMEA source via UDP.

        Perle IOLAN terminal servers forward serial NMEA-0183 data as UDP
        packets.  The socket binds to the configured listen address (usually
        0.0.0.0) and port, then receives whatever the IOLAN sends.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Allow quick restart without "address already in use" errors
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Increase receive buffer for high-rate NMEA streams
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            sock.bind((source.listen_address, source.port))
            sock.settimeout(1.0)
            source.socket = sock

            logger.info("Listening on %s (%s:%d)", source.name,
                        source.listen_address, source.port)

            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                    # NMEA-0183 uses CR/LF line endings; handle both
                    raw = data.decode('ascii', errors='ignore')
                    sentences = raw.replace('\r\n', '\n').replace('\r', '\n').split('\n')

                    for sentence in sentences:
                        sentence = sentence.strip()
                        if sentence:
                            self.parse_sentence(sentence, source)
                            source.mark_data()
                            self.sentence_received.emit(source.name, sentence)

                except socket.timeout:
                    continue
                except Exception as e:
                    source.error_count += 1
                    if source.error_count % 100 == 0:
                        logger.error("Error on %s: %s", source.name, e)

        except Exception as e:
            logger.error("Failed to start listener for %s: %s", source.name, e)
            
    def _monitor_sources(self):
        """Monitor source health and update active sources"""
        while self.running:
            try:
                # Update active GPS source
                self.active_gps_source = self._select_active_source(self.gps_sources)
                
                # Update active heading source
                self.active_heading_source = self._select_active_source(self.heading_sources)
                
                # Update active depth source
                self.active_depth_source = self._select_active_source(self.depth_sources)
                
                # Emit status update
                status = {
                    'gps': self._get_source_status(self.gps_sources),
                    'heading': self._get_source_status(self.heading_sources),
                    'depth': self._get_source_status(self.depth_sources),
                    'ais': self._get_source_status(self.ais_sources),
                    'active_gps': self.active_gps_source.name if self.active_gps_source else None,
                    'active_heading': self.active_heading_source.name if self.active_heading_source else None,
                    'active_depth': self.active_depth_source.name if self.active_depth_source else None
                }
                self.source_status_updated.emit(status)
                
            except Exception as e:
                logger.error("Error in source monitor: %s", e)
                
            # Check every 2 seconds
            threading.Event().wait(2.0)
            
    def _select_active_source(self, sources):
        """Select active source based on priority and availability"""
        # Sort by priority (lower number = higher priority)
        sorted_sources = sorted(
            [s for s in sources if s.enabled],
            key=lambda x: x.priority
        )
        
        # Return first active source
        for source in sorted_sources:
            if source.is_active():
                return source
                
        return None
        
    def _get_source_status(self, sources):
        """Get status of all sources in a list"""
        status = []
        for source in sources:
            status.append({
                'name': source.name,
                'active': source.is_active(),
                'data_count': source.data_count,
                'error_count': source.error_count,
                'priority': source.priority
            })
        return status

    def get_source_status(self):
        """Return current source status dict (used by BIT window)."""
        return {
            'active_gps': (self.active_gps_source.name
                           if self.active_gps_source else None),
            'active_heading': (self.active_heading_source.name
                               if self.active_heading_source else None),
            'active_depth': (self.active_depth_source.name
                             if self.active_depth_source else None),
        }

    def parse_sentence(self, sentence, source):
        """Parse NMEA-0183 sentence from a specific source.

        Handles all common maritime sentence types.  The parser is
        rate-agnostic — it processes whatever sentences arrive on the
        UDP socket regardless of whether the source sends at 1 Hz,
        2 Hz, 10 Hz, or any other rate.
        """
        if not sentence.startswith('$') and not sentence.startswith('!'):
            return

        # Verify checksum if present
        star = sentence.rfind('*')
        if star != -1:
            data, checksum = sentence[:star], sentence[star + 1:star + 3]
            if not self.verify_checksum(data, checksum):
                return

        parts = sentence.split(',')
        # Extract the 3-letter sentence ID (e.g. "GGA" from "$GPGGA")
        sentence_type = parts[0]
        sid = sentence_type[-3:] if len(sentence_type) >= 5 else sentence_type

        try:
            is_active_gps = (source == self.active_gps_source
                             or not self.active_gps_source)
            is_active_hdg = (source == self.active_heading_source
                             or not self.active_heading_source)
            is_active_dep = (source == self.active_depth_source
                             or not self.active_depth_source)

            # ---- Position sentences ----
            if sid in ('GGA', 'GLL'):
                if is_active_gps:
                    self.parse_position(parts, source)

            # ---- RMC — Recommended Minimum (position + time + date + SOG/COG) ----
            elif sid == 'RMC':
                if is_active_gps:
                    self._parse_rmc(parts, source)

            # ---- Heading sentences ----
            elif sid in ('HDT', 'HDG'):
                if is_active_hdg:
                    self.parse_heading(parts, source)

            # ---- Speed / course ----
            elif sid == 'VTG':
                if is_active_gps:
                    self.parse_speed(parts, source)

            # ---- Depth sentences ----
            elif sid in ('DBT', 'DPT'):
                if is_active_dep:
                    self.parse_depth(parts, source)

            # ---- ZDA — Time & Date ----
            elif sid == 'ZDA':
                self._parse_zda(parts, source)

            # ---- ROT — Rate of Turn ----
            elif sid == 'ROT':
                if is_active_hdg:
                    self._parse_rot(parts, source)

            # ---- VHW — Water Speed and Heading ----
            elif sid == 'VHW':
                if is_active_hdg:
                    self._parse_vhw(parts, source)

            # ---- MWV — Wind Speed and Angle ----
            elif sid == 'MWV':
                self._parse_mwv(parts, source)

            # ---- MTW — Water Temperature ----
            elif sid == 'MTW':
                self._parse_mtw(parts, source)

            # ---- RSA — Rudder Sensor Angle ----
            elif sid == 'RSA':
                self._parse_rsa(parts, source)

            # ---- XTE — Cross Track Error ----
            elif sid == 'XTE':
                self._parse_xte(parts, source)

            # ---- AIS sentences ----
            elif sentence_type.startswith('!AIVDM') or sentence_type.startswith('!AIVDO'):
                self.parse_ais(parts, source)

            # ---- Informational — log once but do not error ----
            elif sid in ('GSA', 'GSV', 'TXT', 'ABK', 'ALR'):
                pass  # satellite / text / alert info — no action needed

        except Exception:
            source.error_count += 1
            logger.debug("Failed to parse %r from %s", sentence, source.name, exc_info=True)

    def verify_checksum(self, data, checksum):
        """Verify NMEA checksum"""
        calc_checksum = 0
        for char in data[1:]:
            calc_checksum ^= ord(char)
        return f"{calc_checksum:02X}" == checksum.upper()

    @staticmethod
    def _parse_gga_utc(time_str):
        """Parse GGA UTC time field (HHMMSS.ss) to seconds of day."""
        if not time_str or len(time_str) < 6:
            return None
        try:
            hours = int(time_str[0:2])
            minutes = int(time_str[2:4])
            seconds = float(time_str[4:])
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return None

    def parse_position(self, parts, source):
        """Parse position from GGA or GLL sentence."""
        try:
            if 'GGA' in parts[0]:
                # $GPGGA,HHMMSS.ss,lat,N/S,lon,E/W,qual,nsat,hdop,alt,M,geoid,M,age,stn*CS
                # Fix quality 0 (or empty) = no fix.  Receivers keep sending
                # GGA with empty position fields when the fix is lost; those
                # must NOT be treated as a position (would move own ship to 0,0).
                if len(parts) < 7 or parts[6] in ('', '0'):
                    return
                utc_seconds = self._parse_gga_utc(parts[1])
                lat = self.parse_coordinate(parts[2], parts[3])
                lon = self.parse_coordinate(parts[4], parts[5])
                if lat is None or lon is None:
                    return

                if lat != self.latitude or lon != self.longitude:
                    self.latitude = lat
                    self.longitude = lon
                    self.position_updated.emit(lat, lon, self.speed, source.name)

                # Feed every fix to spoofing detector (even if position unchanged)
                self.spoofing_detector.update_fix(
                    utc_seconds, lat, lon, self.speed
                )

            elif 'GLL' in parts[0]:
                # $GPGLL,lat,N/S,lon,E/W,HHMMSS.ss,status,mode*CS
                if len(parts) >= 7 and parts[6].split('*')[0] in ('A', ''):
                    # 'A' = data valid; some units omit status
                    lat = self.parse_coordinate(parts[1], parts[2])
                    lon = self.parse_coordinate(parts[3], parts[4])
                    if lat is None or lon is None:
                        return
                    if lat != self.latitude or lon != self.longitude:
                        self.latitude = lat
                        self.longitude = lon
                        self.position_updated.emit(lat, lon, self.speed, source.name)
        except (IndexError, ValueError):
            pass
            
    def parse_coordinate(self, coord_str, direction):
        """Parse NMEA coordinate.

        Uses the direction indicator (N/S/E/W) to determine degree width:
          - N or S (latitude)  -> 2-digit degrees (DDMM.MMMM)
          - E or W (longitude) -> 3-digit degrees (DDDMM.MMMM)

        Returns None when the field is empty or malformed (no fix).
        """
        if not coord_str or not direction:
            return None
        try:
            if direction in ('N', 'S'):
                degrees = int(coord_str[:2])
                minutes = float(coord_str[2:])
            elif direction in ('E', 'W'):
                degrees = int(coord_str[:3])
                minutes = float(coord_str[3:])
            else:
                return None
            decimal = degrees + minutes / 60.0
            if direction in ('S', 'W'):
                decimal = -decimal
            return decimal
        except (ValueError, IndexError):
            return None
        
    def parse_heading(self, parts, source):
        """Parse heading from HDT or HDG sentence."""
        try:
            if 'HDT' in parts[0]:
                # $HEHDT,heading,T*CS  (True heading)
                if parts[1]:
                    heading = float(parts[1])
                    if heading != self.heading:
                        self.heading = heading
                        self.heading_updated.emit(heading, source.name)
            elif 'HDG' in parts[0]:
                # $HCHDG,heading,deviation,dev_dir,variation,var_dir*CS
                # True = magnetic sensor heading + deviation + variation
                if parts[1]:
                    heading = float(parts[1])
                    if len(parts) >= 4 and parts[2] and parts[3]:
                        deviation = float(parts[2])
                        heading += -deviation if parts[3].startswith('W') else deviation
                    variation = None
                    if len(parts) >= 6 and parts[4] and parts[5]:
                        variation = float(parts[4])
                        if parts[5].startswith('W'):
                            variation = -variation
                    elif self.magnetic_variation is not None:
                        variation = self.magnetic_variation   # from RMC
                    if variation is None:
                        if not self._warned_no_variation:
                            logger.warning("HDG from %s has no magnetic variation and none "
                                           "is available from RMC — heading is MAGNETIC, "
                                           "not true", source.name)
                            self._warned_no_variation = True
                    else:
                        heading += variation
                    heading %= 360.0
                    if heading != self.heading:
                        self.heading = heading
                        self.heading_updated.emit(heading, source.name)
        except (IndexError, ValueError):
            pass
            
    def parse_speed(self, parts, source):
        """Parse speed from VTG sentence.
        $GPVTG,COG_T,T,COG_M,M,SOG_N,N,SOG_K,K*CS
        """
        try:
            # Speed over ground in knots is field 5
            if len(parts) >= 6 and parts[5]:
                speed = float(parts[5])
                self.speed_over_ground = speed
                if speed != self.speed:
                    self.speed = speed
                    self.position_updated.emit(self.latitude, self.longitude, speed, source.name)
            # Also extract COG if available
            if len(parts) >= 2 and parts[1]:
                self.course = float(parts[1])
                self.cog_updated.emit(self.course, self.speed_over_ground)
        except (IndexError, ValueError):
            pass
            
    def parse_depth(self, parts, source):
        """Parse depth"""
        try:
            if 'DBT' in parts[0]:
                depth = float(parts[3])
                if depth != self.depth:
                    self.depth = depth
                    self.depth_updated.emit(depth, source.name)
            elif 'DPT' in parts[0]:
                depth = float(parts[1])
                if depth != self.depth:
                    self.depth = depth
                    self.depth_updated.emit(depth, source.name)
        except (IndexError, ValueError):
            pass
            
    # ------------------------------------------------------------------
    # RMC — Recommended Minimum Navigation Information
    # $GPRMC,HHMMSS.ss,A,lat,N,lon,W,SOG,COG,DDMMYY,magvar,vardir*CS
    # ------------------------------------------------------------------
    def _parse_rmc(self, parts, source):
        """Parse RMC sentence for position, SOG, COG, and UTC time/date."""
        try:
            if len(parts) < 10:
                return
            status = parts[2]
            if status != 'A':
                return  # V = receiver warning / invalid

            # Position
            lat = self.parse_coordinate(parts[3], parts[4])
            lon = self.parse_coordinate(parts[5], parts[6])
            if lat is None or lon is None:
                return
            if lat != self.latitude or lon != self.longitude:
                self.latitude = lat
                self.longitude = lon

            # Speed over ground (knots)
            if parts[7]:
                sog = float(parts[7])
                self.speed_over_ground = sog
                if sog != self.speed:
                    self.speed = sog

            # Course over ground (degrees true)
            if parts[8]:
                self.course = float(parts[8])
                self.cog_updated.emit(self.course, self.speed_over_ground)

            # Magnetic variation (fields 10/11) — used to correct HDG headings
            if len(parts) >= 12 and parts[10] and parts[11]:
                var = float(parts[10])
                self.magnetic_variation = -var if parts[11].startswith('W') else var

            self.position_updated.emit(self.latitude, self.longitude,
                                       self.speed, source.name)

            # UTC time from field 1 (HHMMSS.ss)
            if parts[1] and len(parts[1]) >= 6:
                hh = parts[1][0:2]
                mm = parts[1][2:4]
                ss = parts[1][4:6]
                self.utc_time = f"{hh}:{mm}:{ss}"

            # UTC date from field 9 (DDMMYY)
            if parts[9] and len(parts[9]) == 6:
                dd = parts[9][0:2]
                mo = parts[9][2:4]
                yy = parts[9][4:6]
                year = 2000 + int(yy)
                self.utc_date = f"{year}-{mo}-{dd}"
                self.time_updated.emit(self.utc_time, self.utc_date)

            # Feed spoofing detector
            utc_seconds = self._parse_gga_utc(parts[1])
            self.spoofing_detector.update_fix(
                utc_seconds, lat, lon, self.speed
            )
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # ZDA — Time & Date
    # $GPZDA,HHMMSS.ss,DD,MM,YYYY,tz_h,tz_m*CS
    # ------------------------------------------------------------------
    def _parse_zda(self, parts, source):
        """Parse ZDA sentence for UTC date and time."""
        try:
            if len(parts) < 5:
                return
            # UTC time
            if parts[1] and len(parts[1]) >= 6:
                hh = parts[1][0:2]
                mm = parts[1][2:4]
                ss = parts[1][4:6]
                self.utc_time = f"{hh}:{mm}:{ss}"
            # Date
            day = parts[2].zfill(2)
            month = parts[3].zfill(2)
            year = parts[4]
            self.utc_date = f"{year}-{month}-{day}"
            self.time_updated.emit(self.utc_time, self.utc_date)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # ROT — Rate of Turn
    # $HEROT,rate,A*CS   (deg/min, A=valid)
    # ------------------------------------------------------------------
    def _parse_rot(self, parts, source):
        """Parse ROT sentence for rate of turn."""
        try:
            if len(parts) < 3:
                return
            # Check validity flag
            status = parts[2].split('*')[0] if '*' in parts[2] else parts[2]
            if status != 'A':
                return
            rot = float(parts[1])
            if rot != self.rate_of_turn:
                self.rate_of_turn = rot
                self.rot_updated.emit(rot)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # VHW — Water Speed and Heading
    # $VWVHW,hdg_T,T,hdg_M,M,speed_kts,N,speed_kmh,K*CS
    # ------------------------------------------------------------------
    def _parse_vhw(self, parts, source):
        """Parse VHW sentence for heading through water and water speed."""
        try:
            if len(parts) < 6:
                return
            # True heading through water
            if parts[1]:
                heading = float(parts[1])
                if heading != self.heading:
                    self.heading = heading
                    self.heading_updated.emit(heading, source.name)
            # Speed through water in knots (separate from SOG)
            if parts[5]:
                stw = float(parts[5])
                if stw != self.speed_through_water:
                    self.speed_through_water = stw
                    self.stw_updated.emit(stw)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # MWV — Wind Speed and Angle
    # $WIMWV,angle,R/T,speed,unit,A*CS
    # ------------------------------------------------------------------
    def _parse_mwv(self, parts, source):
        """Parse MWV sentence for wind angle and speed."""
        try:
            if len(parts) < 6:
                return
            status = parts[5].split('*')[0] if '*' in parts[5] else parts[5]
            if status != 'A':
                return
            angle = float(parts[1])
            reference = parts[2]  # R=relative, T=true
            speed_val = float(parts[3])
            unit = parts[4]
            # Convert to knots
            if unit == 'K':       # km/h
                speed_val /= 1.852
            elif unit == 'M':     # m/s
                speed_val *= 1.94384

            self.wind_angle = angle
            self.wind_speed = speed_val
            self.wind_reference = reference
            self.wind_updated.emit(angle, speed_val, reference)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # MTW — Water Temperature
    # $YXMTW,temp,C*CS
    # ------------------------------------------------------------------
    def _parse_mtw(self, parts, source):
        """Parse MTW sentence for water temperature."""
        try:
            if len(parts) < 3:
                return
            temp = float(parts[1])
            unit = parts[2].split('*')[0] if '*' in parts[2] else parts[2]
            if unit == 'F':
                temp = (temp - 32.0) * 5.0 / 9.0  # convert to Celsius
            if temp != self.water_temp:
                self.water_temp = temp
                self.water_temp_updated.emit(temp)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # RSA — Rudder Sensor Angle
    # $AGRSA,stbd,A,port,A*CS
    # ------------------------------------------------------------------
    def _parse_rsa(self, parts, source):
        """Parse RSA sentence. Logged for diagnostic use."""
        try:
            if len(parts) < 3:
                return
            if parts[1]:
                logger.debug("Rudder angle: %.1f°", float(parts[1]))
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # XTE — Cross Track Error
    # $GPXTE,A,A,magnitude,L/R,N*CS
    # ------------------------------------------------------------------
    def _parse_xte(self, parts, source):
        """Parse XTE sentence. Logged for diagnostic use."""
        try:
            if len(parts) < 6:
                return
            if parts[3]:
                xte = float(parts[3])
                direction = parts[4]  # L or R
                logger.debug("Cross track error: %.3f NM %s", xte, direction)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------
    # AIS decoding  (ITU-R M.1371 via AIVDM/AIVDO sentences)
    # ------------------------------------------------------------------

    # Multi-sentence reassembly buffer: seq_id -> {count, payloads, pad, ts}
    _ais_reassembly: dict = {}
    _AIS_REASSEMBLY_TIMEOUT = 10.0  # seconds before discarding incomplete fragments

    def _prune_ais_reassembly(self):
        """Remove stale AIS reassembly buffers to prevent memory leaks."""
        now = time.monotonic()
        stale = [k for k, v in self._ais_reassembly.items()
                 if now - v.get('ts', 0) > self._AIS_REASSEMBLY_TIMEOUT]
        for k in stale:
            del self._ais_reassembly[k]

    def parse_ais(self, parts, source):
        """Decode AIVDM / AIVDO sentences.

        Handles single- and multi-sentence messages.  Decodes the 6-bit
        payload and dispatches to message-type-specific handlers for:
          - Types 1, 2, 3  : Class A position report
          - Type 5          : Class A static / voyage data
          - Type 18         : Class B position report
          - Type 24         : Class B static data (parts A & B)
        """
        try:
            # Periodically prune stale reassembly buffers
            self._prune_ais_reassembly()

            # !AIVDM,frag_count,frag_num,seq_id,channel,payload,pad*CS
            if len(parts) < 7:
                return
            frag_count = int(parts[1])
            frag_num = int(parts[2])
            seq_id = parts[3]          # may be empty for single-sentence
            payload_str = parts[5]
            pad_bits = int(parts[6].split('*')[0]) if '*' in parts[6] else 0

            if frag_count == 1:
                # Single-sentence — try decrypt then decode
                dec_payload, dec_pad, encrypted, key_name = \
                    self.ais_decryptor.try_decrypt(payload_str, pad_bits)
                bits = _ais_decode_payload(dec_payload, dec_pad)
                self._ais_dispatch(bits, source, encrypted, key_name)
            else:
                # Multi-sentence — reassemble.  Key on source + channel +
                # sequence id so interleaved messages can't be mixed, and
                # require fragments in order so a lost middle fragment
                # discards the message instead of decoding garbage.
                key = (source.name, parts[4], seq_id or '_default')
                if frag_num == 1:
                    self._ais_reassembly[key] = {
                        'count': frag_count,
                        'payloads': [payload_str],
                        'pad': 0,
                        'ts': time.monotonic(),
                    }
                elif key in self._ais_reassembly:
                    buf = self._ais_reassembly[key]
                    if frag_num != len(buf['payloads']) + 1 or frag_count != buf['count']:
                        del self._ais_reassembly[key]      # missing / out-of-order fragment
                        return
                    buf['payloads'].append(payload_str)
                    if frag_num == frag_count:
                        buf['pad'] = pad_bits
                        full_payload = ''.join(buf['payloads'])
                        del self._ais_reassembly[key]
                        dec_payload, dec_pad, encrypted, key_name = \
                            self.ais_decryptor.try_decrypt(
                                full_payload, buf['pad'])
                        bits = _ais_decode_payload(dec_payload, dec_pad)
                        self._ais_dispatch(bits, source,
                                           encrypted, key_name)
        except Exception:
            source.error_count += 1
            logger.debug("AIS decode failed (%s)", source.name, exc_info=True)

    def _ais_dispatch(self, bits: list[int], source,
                       encrypted: bool = False, key_name: str = ''):
        """Route decoded bit-vector to the correct message handler."""
        if len(bits) < 6:
            return
        msg_type = _ais_bits_to_uint(bits, 0, 6)
        with self._ais_lock:
            if msg_type in (1, 2, 3):
                self._ais_msg_123(bits, encrypted, key_name)
            elif msg_type == 4:
                self._ais_msg_4(bits)
            elif msg_type == 5:
                self._ais_msg_5(bits, encrypted, key_name)
            elif msg_type == 18:
                self._ais_msg_18(bits, encrypted, key_name)
            elif msg_type == 24:
                self._ais_msg_24(bits, encrypted, key_name)

    def _ais_msg_123(self, bits, encrypted=False, key_name=''):
        """Class A position report (types 1, 2, 3) — 168 bits."""
        if len(bits) < 168:
            return
        mmsi = str(_ais_bits_to_uint(bits, 8, 30))
        nav_status = _ais_bits_to_uint(bits, 38, 4)
        sog_raw = _ais_bits_to_uint(bits, 50, 10)  # 1/10 knot
        lon_raw = _ais_bits_to_int(bits, 61, 28)    # 1/10000 min
        lat_raw = _ais_bits_to_int(bits, 89, 27)    # 1/10000 min
        cog_raw = _ais_bits_to_uint(bits, 116, 12)  # 1/10 deg
        hdg_raw = _ais_bits_to_uint(bits, 128, 9)   # degrees

        # Validity checks (ITU default = not available)
        if lon_raw == 0x6791AC0 or lat_raw == 0x3412140:
            return
        lon = lon_raw / 600000.0
        lat = lat_raw / 600000.0
        if abs(lon) > 180 or abs(lat) > 90:
            return

        self._store_position_report(mmsi, lat, lon, sog_raw, cog_raw, hdg_raw,
                                    'A', encrypted, key_name, nav_status=nav_status)

    # ITU-R M.1371 "not available" values
    _SOG_NA = 1023
    _COG_NA = 3600
    _HDG_NA = 511

    def _store_position_report(self, mmsi, lat, lon, sog_raw, cog_raw, hdg_raw,
                               ais_class, encrypted, key_name, nav_status=15):
        """Store a position report.  Unavailable SOG/COG/heading become None
        (never 0, which would draw a false northbound vector and false CPA)."""
        sog = sog_raw / 10.0 if sog_raw < self._SOG_NA else None
        cog = cog_raw / 10.0 if cog_raw < self._COG_NA else None
        hdg = float(hdg_raw) if hdg_raw < 360 else cog
        static = self._ais_static.get(mmsi, {})
        self.ais_targets[mmsi] = {
            'mmsi': mmsi,
            'lat': lat,
            'lon': lon,
            'course': cog,
            'speed': sog,
            'heading': hdg,
            'nav_status': nav_status,
            'name': static.get('name') or f'MMSI-{mmsi}',
            'ship_type': static.get('ship_type', 0),
            'call_sign': static.get('call_sign', ''),
            'destination': static.get('destination', ''),
            'class': ais_class,
            'encrypted': encrypted or static.get('encrypted', False),
            'decrypt_key': key_name or static.get('decrypt_key', ''),
            'rx_time': time.monotonic(),
        }
        self._ais_dirty = True

    def _store_static(self, mmsi, encrypted, key_name, **fields):
        """Store static/voyage data.  It is merged into the target when (or
        if) a position report exists — static data alone never creates a
        target, so no phantom targets appear at 0°N 0°E."""
        static = self._ais_static.setdefault(mmsi, {})
        static.update({k: v for k, v in fields.items() if v not in (None, '')})
        if encrypted:
            static['encrypted'] = True
            static['decrypt_key'] = key_name
        static['ts'] = time.monotonic()
        tgt = self.ais_targets.get(mmsi)
        if tgt is not None:
            merged = dict(tgt)                     # copy: published dicts are never mutated
            merged.update({k: v for k, v in static.items() if k != 'ts'})
            self.ais_targets[mmsi] = merged
            self._ais_dirty = True

    def _ais_publisher(self):
        """Prune lost AIS targets and publish changes at a bounded rate."""
        while self.running:
            time.sleep(self.AIS_PUBLISH_INTERVAL_S)
            try:
                self._publish_ais()
            except Exception:
                logger.exception("AIS publisher error")

    def _publish_ais(self):
        now = time.monotonic()
        with self._ais_lock:
            stale = [m for m, t in self.ais_targets.items()
                     if now - t.get('rx_time', now) > self.AIS_TARGET_TIMEOUT_S]
            for m in stale:
                del self.ais_targets[m]
            for m in [m for m, st in self._ais_static.items()
                      if now - st.get('ts', now) > self.AIS_STATIC_TIMEOUT_S]:
                del self._ais_static[m]
            old_bs = [m for m, b in self.ais_base_stations.items()
                      if now - b.get('rx_time', now) > self.AIS_BASE_STATION_TIMEOUT_S]
            for m in old_bs:
                del self.ais_base_stations[m]
            emit_targets = self._ais_dirty or bool(stale)
            emit_bases = self._base_dirty or bool(old_bs)
            targets = list(self.ais_targets.values()) if emit_targets else None
            bases = list(self.ais_base_stations.values()) if emit_bases else None
            self._ais_dirty = self._base_dirty = False
        if stale:
            logger.info("AIS: %d target(s) lost (no report for %.0f s)",
                        len(stale), self.AIS_TARGET_TIMEOUT_S)
        if targets is not None:
            self.ais_updated.emit(targets)
        if bases is not None:
            self.base_stations_updated.emit(bases)

    def _ais_msg_4(self, bits):
        """Base Station Report (type 4) — 168 bits.

        Fixed shore-based AIS infrastructure: USCG, VTS, port authority
        transmitters.  Stored in ais_base_stations (separate from vessel
        targets) and emitted via base_stations_updated.  Never forwarded to
        the track manager — no CPA, no Kalman, no correlation.

        Bit layout (ITU-R M.1371-5, 0-based offsets):
          MMSI       : offset  8, len 30
          Longitude  : offset 79, len 28  (1/10000 min, same encoding as Type 1)
          Latitude   : offset 107, len 27 (1/10000 min, same encoding as Type 1)
        """
        if len(bits) < 168:
            return
        mmsi = str(_ais_bits_to_uint(bits, 8, 30))
        lon_raw = _ais_bits_to_int(bits, 79, 28)   # 1/10000 min
        lat_raw = _ais_bits_to_int(bits, 107, 27)  # 1/10000 min

        # ITU-R sentinel values: longitude 181° / latitude 91° = not available
        if lon_raw == 0x6791AC0 or lat_raw == 0x3412140:
            return
        lon = lon_raw / 600000.0
        lat = lat_raw / 600000.0
        if abs(lon) > 180 or abs(lat) > 90:
            return

        self.ais_base_stations[mmsi] = {
            'mmsi': mmsi,
            'lat': lat,
            'lon': lon,
            'type': 'ais_base',
            'name': f'BASE-{mmsi}',
            'rx_time': time.monotonic(),
        }
        self._base_dirty = True

    def _ais_msg_5(self, bits, encrypted=False, key_name=''):
        """Class A static / voyage data (type 5) — 424 bits."""
        if len(bits) < 424:
            return
        mmsi = str(_ais_bits_to_uint(bits, 8, 30))
        ship_type = _ais_bits_to_uint(bits, 232, 8)
        name = _ais_decode_text(bits, 112, 120)       # 20 chars
        call_sign = _ais_decode_text(bits, 70, 42)     # 7 chars
        destination = _ais_decode_text(bits, 302, 120)  # 20 chars

        self._store_static(mmsi, encrypted, key_name, name=name, ship_type=ship_type,
                           call_sign=call_sign, destination=destination)

    def _ais_msg_18(self, bits, encrypted=False, key_name=''):
        """Class B position report (type 18) — 168 bits."""
        if len(bits) < 168:
            return
        mmsi = str(_ais_bits_to_uint(bits, 8, 30))
        sog_raw = _ais_bits_to_uint(bits, 46, 10)
        lon_raw = _ais_bits_to_int(bits, 57, 28)
        lat_raw = _ais_bits_to_int(bits, 85, 27)
        cog_raw = _ais_bits_to_uint(bits, 112, 12)
        hdg_raw = _ais_bits_to_uint(bits, 124, 9)

        if lon_raw == 0x6791AC0 or lat_raw == 0x3412140:
            return
        lon = lon_raw / 600000.0
        lat = lat_raw / 600000.0
        if abs(lon) > 180 or abs(lat) > 90:
            return
        self._store_position_report(mmsi, lat, lon, sog_raw, cog_raw, hdg_raw,
                                    'B', encrypted, key_name)

    def _ais_msg_24(self, bits, encrypted=False, key_name=''):
        """Class B static data (type 24) — parts A and B."""
        if len(bits) < 168:
            return
        mmsi = str(_ais_bits_to_uint(bits, 8, 30))
        part_num = _ais_bits_to_uint(bits, 38, 2)
        if part_num == 0:
            # Part A: ship name
            self._store_static(mmsi, encrypted, key_name,
                               name=_ais_decode_text(bits, 40, 120))
        elif part_num == 1:
            # Part B: call sign, ship type
            self._store_static(mmsi, encrypted, key_name,
                               call_sign=_ais_decode_text(bits, 40, 42),
                               ship_type=_ais_bits_to_uint(bits, 82, 8))


# ======================================================================
# AIS bit-level helpers (module-level, used by MultiSourceNMEAParser)
# ======================================================================

def _ais_decode_payload(payload: str, pad: int) -> list[int]:
    """Decode 6-bit ASCII-armored AIS payload into a flat bit list."""
    bits: list[int] = []
    for ch in payload:
        val = ord(ch) - 48
        if val > 40:
            val -= 8
        for shift in (5, 4, 3, 2, 1, 0):
            bits.append((val >> shift) & 1)
    if pad:
        bits = bits[:-pad]
    return bits


def _ais_bits_to_uint(bits: list[int], start: int, length: int) -> int:
    """Extract an unsigned integer from bit-vector."""
    val = 0
    for i in range(start, start + length):
        val = (val << 1) | bits[i]
    return val


def _ais_bits_to_int(bits: list[int], start: int, length: int) -> int:
    """Extract a signed (two's complement) integer from bit-vector."""
    val = _ais_bits_to_uint(bits, start, length)
    if bits[start]:  # sign bit set
        val -= (1 << length)
    return val


# AIS 6-bit character table (ITU-R M.1371, Table 47)
_AIS_CHARS = "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_ !\"#$%&'()*+,-./0123456789:;<=>?"


def _ais_decode_text(bits: list[int], start: int, bit_length: int) -> str:
    """Decode 6-bit packed AIS text field into a string."""
    chars = []
    for i in range(start, start + bit_length, 6):
        if i + 6 > len(bits):
            break
        idx = _ais_bits_to_uint(bits, i, 6)
        chars.append(_AIS_CHARS[idx])
    return ''.join(chars).rstrip('@').strip()
