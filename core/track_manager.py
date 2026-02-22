"""
Track Manager
Correlates AIS tracks with radar tracks
Enhanced with CPA/TCPA calculation, Kalman filtering, and trail history
"""

import math
import threading
from collections import deque
from datetime import datetime, timedelta
from core.cpa_calculator import CPACalculator, ThreatAssessor
from core.track_filter import KalmanTrackFilter, AlphaBetaFilter
from core.guard_zone import GuardZoneManager, calculate_target_bearing_range


class TrackManager:
    """Manage and correlate radar and AIS tracks"""

    def __init__(self):
        self.radar_tracks = {}
        self.ais_tracks = {}
        self.correlated_tracks = {}
        self._lock = threading.Lock()

        # Correlation parameters
        self.correlation_distance_nm = 0.1  # Maximum distance for correlation
        self.track_timeout = timedelta(minutes=5)  # Drop tracks after 5 minutes

        # CPA/TCPA calculation
        self.cpa_calculator = CPACalculator(cpa_threshold_nm=2.0, tcpa_threshold_min=12.0)
        self.threat_assessor = ThreatAssessor()

        # Guard zone management
        self.guard_zone_manager = GuardZoneManager()
        self.guard_zone_manager.create_default_zones()

        # Track filters (Kalman filtering for smooth tracks)
        self.track_filters = {}  # track_id -> KalmanTrackFilter

        # Trail history: track_id -> deque of (lat, lon, timestamp)
        self.track_history = {}
        self._trail_interval_s = 30.0   # seconds between recorded trail dots
        self._trail_length_min = 6.0    # total trail duration in minutes
        self._last_trail_record = {}    # track_id -> last record timestamp

        # Target classifications: target_id -> 'friendly' | 'neutral' | 'hostile'
        self.target_classifications = {}

        # Own ship data (needed for CPA/TCPA)
        self.own_ship = {
            'lat': 0.0,
            'lon': 0.0,
            'course': 0.0,
            'speed': 0.0
        }

        # Priority-tiered correlation scheduling
        self._corr_tick: int = 0      # Monotonic counter; increments each correlate_tracks() call
        self._ais_grid: dict = {}     # Spatial grid: (cell_lat, cell_lon) -> list[ais_id]
        self._GRID_SCALE: int = 200   # int(lat*200) → 0.005° cells ≈ 0.3 NM × 0.2 NM

        # Range tier thresholds (nautical miles from own ship)
        self.TIER_CRITICAL_NM: float = 1.5  # Correlate every tick   — highest priority
        self.TIER_NEAR_NM: float = 3.0      # Correlate every 2nd tick
        # Tracks beyond TIER_NEAR_NM          correlate every 5th tick — lowest priority

    def update_own_ship(self, lat, lon, course, speed):
        """Update own ship position and motion"""
        self.own_ship = {
            'lat': lat,
            'lon': lon,
            'course': course,
            'speed': speed
        }

    def set_target_classification(self, target_id, classification):
        """Set target classification: 'friendly', 'neutral', 'hostile', or None to clear."""
        if classification is None:
            self.target_classifications.pop(target_id, None)
        else:
            self.target_classifications[target_id] = classification

    def get_target_classification(self, target_id):
        """Get target classification, or None if unclassified."""
        return self.target_classifications.get(target_id)

    # ------------------------------------------------------------------
    # Trail history management
    # ------------------------------------------------------------------

    def set_trail_length(self, minutes):
        """Set how many minutes of trail history to keep."""
        self._trail_length_min = float(minutes)
        self._prune_all_trails()

    def set_trail_interval(self, seconds):
        """Set the interval between recorded trail dots."""
        self._trail_interval_s = float(seconds)

    def clear_trails(self):
        """Remove all trail history."""
        self.track_history.clear()
        self._last_trail_record.clear()

    def _record_trail(self, track_id, lat, lon, now):
        """Record a trail point if enough time has elapsed."""
        last = self._last_trail_record.get(track_id)
        if last is not None and (now - last).total_seconds() < self._trail_interval_s:
            return
        if track_id not in self.track_history:
            self.track_history[track_id] = deque()
        self.track_history[track_id].append((lat, lon, now))
        self._last_trail_record[track_id] = now
        # Prune old entries
        cutoff = now - timedelta(minutes=self._trail_length_min)
        while self.track_history[track_id] and self.track_history[track_id][0][2] < cutoff:
            self.track_history[track_id].popleft()

    def _get_trail(self, track_id):
        """Return trail as a list of (lat, lon, timestamp) tuples."""
        return list(self.track_history.get(track_id, []))

    def _prune_all_trails(self):
        """Prune all trails to the current length setting."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=self._trail_length_min)
        to_delete = []
        for tid, trail in self.track_history.items():
            while trail and trail[0][2] < cutoff:
                trail.popleft()
            if not trail:
                to_delete.append(tid)
        for tid in to_delete:
            del self.track_history[tid]
            self._last_trail_record.pop(tid, None)
        
    def update_radar_tracks(self, radar_targets):
        """Update radar tracks from radar returns with Kalman filtering and CPA/TCPA"""
        current_time = datetime.now()

        with self._lock:
            self._update_radar_tracks_locked(radar_targets, current_time)

    def _update_radar_tracks_locked(self, radar_targets, current_time):
        # Process nearest targets first so high-priority tracks are always
        # fully updated even if own-ship position is at the origin (0,0) on
        # startup — the sort is a no-op cost O(n log n) and negligible vs
        # per-track Kalman/CPA work.
        radar_targets = sorted(
            radar_targets,
            key=lambda t: self.calculate_distance(
                self.own_ship['lat'], self.own_ship['lon'],
                t['lat'], t['lon']
            )
        )
        for target in radar_targets:
            track_id = target.get('id', None)
            
            if track_id is None:
                # Create new track
                track_id = self.generate_track_id('R')
                
            # Convert to meters for Kalman filter
            target_x, target_y = self._latlon_to_meters(
                self.own_ship['lat'], self.own_ship['lon'],
                target['lat'], target['lon']
            )
            
            # Apply Kalman filtering
            if track_id not in self.track_filters:
                # Initialize new filter
                self.track_filters[track_id] = KalmanTrackFilter()
                self.track_filters[track_id].initialize(target_x, target_y)
                filtered_x, filtered_y = target_x, target_y
            else:
                # Predict and update
                self.track_filters[track_id].predict()
                filtered_x, filtered_y = self.track_filters[track_id].update([target_x, target_y])
            
            # Get filtered course and speed
            filtered_speed, filtered_course = self.track_filters[track_id].get_speed_and_course()
            
            # Convert back to lat/lon
            filtered_lat, filtered_lon = self._meters_to_latlon(
                self.own_ship['lat'], self.own_ship['lon'],
                filtered_x, filtered_y
            )
            
            # Calculate CPA/TCPA with own ship
            target_data = {
                'lat': filtered_lat,
                'lon': filtered_lon,
                'course': filtered_course,
                'speed': filtered_speed
            }
            
            cpa_result = self.cpa_calculator.calculate(self.own_ship, target_data)
            threat_assessment = self.threat_assessor.assess_target(track_id, self.own_ship, target_data)
            
            # Check guard zones
            bearing, range_nm = calculate_target_bearing_range(
                self.own_ship['lat'], self.own_ship['lon'],
                filtered_lat, filtered_lon
            )
            guard_zones = self.guard_zone_manager.check_target(track_id, bearing, range_nm)
            
            # Record trail position
            self._record_trail(track_id, filtered_lat, filtered_lon, current_time)

            # Store enhanced track
            self.radar_tracks[track_id] = {
                'id': track_id,
                'lat': filtered_lat,
                'lon': filtered_lon,
                'course': filtered_course,
                'speed': filtered_speed,
                'last_update': current_time,
                'type': 'radar',
                'cpa': cpa_result.cpa_distance,
                'tcpa': cpa_result.tcpa_minutes,
                'risk_level': threat_assessment['risk_level'],
                'is_threat': threat_assessment['is_threat'],
                'guard_zones': guard_zones,
                'bearing': bearing,
                'range': range_nm,
                'trail': self._get_trail(track_id),
                'classification': self.target_classifications.get(track_id),
            }
            
        # Remove old tracks
        self.cleanup_old_tracks(self.radar_tracks, current_time)
        
        # Attempt correlation
        self.correlate_tracks()
        
    def _latlon_to_meters(self, own_lat, own_lon, target_lat, target_lon):
        """Convert lat/lon to local meters (flat Earth approximation)"""
        dlat = target_lat - own_lat
        dlon = target_lon - own_lon
        
        meters_per_degree_lat = 111120.0
        meters_per_degree_lon = 111120.0 * math.cos(math.radians(own_lat))
        
        x = dlon * meters_per_degree_lon
        y = dlat * meters_per_degree_lat
        
        return x, y
        
    def _meters_to_latlon(self, own_lat, own_lon, x, y):
        """Convert local meters to lat/lon"""
        meters_per_degree_lat = 111120.0
        meters_per_degree_lon = 111120.0 * math.cos(math.radians(own_lat))
        
        dlat = y / meters_per_degree_lat
        dlon = x / meters_per_degree_lon
        
        target_lat = own_lat + dlat
        target_lon = own_lon + dlon
        
        return target_lat, target_lon
        
    def update_ais_tracks(self, ais_targets):
        """Update AIS tracks with CPA/TCPA calculation"""
        current_time = datetime.now()

        with self._lock:
            self._update_ais_tracks_locked(ais_targets, current_time)

    def _update_ais_tracks_locked(self, ais_targets, current_time):
        # Process nearest AIS targets first — same priority rationale as radar.
        ais_targets = sorted(
            ais_targets,
            key=lambda t: self.calculate_distance(
                self.own_ship['lat'], self.own_ship['lon'],
                t['lat'], t['lon']
            )
        )
        for target in ais_targets:
            mmsi = target.get('mmsi')
            if mmsi:
                # Calculate CPA/TCPA
                target_data = {
                    'lat': target['lat'],
                    'lon': target['lon'],
                    'course': target.get('course', 0),
                    'speed': target.get('speed', 0)
                }
                
                cpa_result = self.cpa_calculator.calculate(self.own_ship, target_data)
                threat_assessment = self.threat_assessor.assess_target(mmsi, self.own_ship, target_data)
                
                # Check guard zones
                bearing, range_nm = calculate_target_bearing_range(
                    self.own_ship['lat'], self.own_ship['lon'],
                    target['lat'], target['lon']
                )
                guard_zones = self.guard_zone_manager.check_target(mmsi, bearing, range_nm)
                
                # Record trail position
                self._record_trail(mmsi, target['lat'], target['lon'], current_time)

                self.ais_tracks[mmsi] = {
                    'id': mmsi,
                    'mmsi': mmsi,
                    'lat': target['lat'],
                    'lon': target['lon'],
                    'course': target.get('course', 0),
                    'speed': target.get('speed', 0),
                    'name': target.get('name', f'Unknown-{mmsi}'),
                    'last_update': current_time,
                    'type': 'ais',
                    'cpa': cpa_result.cpa_distance,
                    'tcpa': cpa_result.tcpa_minutes,
                    'risk_level': threat_assessment['risk_level'],
                    'is_threat': threat_assessment['is_threat'],
                    'guard_zones': guard_zones,
                    'bearing': bearing,
                    'range': range_nm,
                    'trail': self._get_trail(mmsi),
                    'classification': self.target_classifications.get(mmsi)
                                     or ('friendly' if target.get('encrypted') else None),
                    'encrypted': target.get('encrypted', False),
                    'decrypt_key': target.get('decrypt_key', ''),
                }
                
        # Remove old tracks
        self.cleanup_old_tracks(self.ais_tracks, current_time)
        
        # Attempt correlation
        self.correlate_tracks()
        
    def get_threat_summary(self):
        """Get summary of current threats"""
        threats = []
        
        # Check radar tracks
        for track in self.radar_tracks.values():
            if track.get('is_threat'):
                threats.append({
                    'id': track['id'],
                    'type': 'radar',
                    'cpa': track['cpa'],
                    'tcpa': track['tcpa'],
                    'risk_level': track['risk_level']
                })
                
        # Check AIS tracks
        for track in self.ais_tracks.values():
            if track.get('is_threat'):
                threats.append({
                    'id': track['id'],
                    'type': 'ais',
                    'name': track['name'],
                    'cpa': track['cpa'],
                    'tcpa': track['tcpa'],
                    'risk_level': track['risk_level']
                })
                
        # Sort by risk level (critical > warning > caution)
        priority = {'critical': 3, 'warning': 2, 'caution': 1}
        threats.sort(key=lambda t: priority.get(t['risk_level'], 0), reverse=True)
        
        return threats
        
    def _build_ais_grid(self):
        """Bucket all AIS tracks into a spatial grid for fast candidate lookup.

        Each cell covers ~0.005° × 0.005° (≈ 0.3 NM × 0.2 NM at mid-latitudes).
        Called once per correlate_tracks() — O(m) where m = number of AIS tracks.
        """
        grid = {}
        for ais_id, track in self.ais_tracks.items():
            cell = (int(track['lat'] * self._GRID_SCALE),
                    int(track['lon'] * self._GRID_SCALE))
            grid.setdefault(cell, []).append(ais_id)
        self._ais_grid = grid

    def _get_ais_candidates(self, lat, lon):
        """Return AIS IDs from the 3×3 grid neighbourhood around (lat, lon).

        The neighbourhood spans ±1 cell (≈ ±0.3 NM) in each axis, which is
        well beyond the 0.1 NM correlation threshold, so no eligible target
        is ever missed.  In a dense port scene this reduces the candidate set
        from hundreds to single digits.
        """
        cx = int(lat * self._GRID_SCALE)
        cy = int(lon * self._GRID_SCALE)
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidates.extend(self._ais_grid.get((cx + dx, cy + dy), []))
        return candidates

    def correlate_tracks(self):
        """Correlate radar tracks with AIS tracks.

        Uses two techniques to keep CPU load manageable in high-density ports:

        1. Spatial grid index — build_ais_grid() buckets AIS targets into a
           lat/lon grid so each radar track only inspects the handful of AIS
           targets in its immediate 3×3-cell neighbourhood rather than all m
           AIS targets.  Reduces inner loop from O(m) to O(k), k ≈ 1–10 in
           typical port conditions.

        2. Priority tiers — radar tracks are processed nearest-first (highest
           threat priority).  Tracks beyond TIER_CRITICAL_NM are correlated
           at reduced rates: every 2nd tick for NEAR, every 5th tick for FAR.
           Previous correlation results are carried forward on skipped ticks so
           the display remains consistent and nothing disappears.
        """
        self._corr_tick += 1
        tick = self._corr_tick
        new_corr = {}

        # Build spatial AIS index once per call — O(m)
        self._build_ais_grid()

        # Process radar tracks nearest-first so closest targets always get
        # freshest correlation data regardless of the throttle schedule.
        sorted_radar = sorted(
            self.radar_tracks.items(),
            key=lambda kv: kv[1].get('range', 999.0)
        )

        for radar_id, radar_track in sorted_radar:
            rng = radar_track.get('range', 999.0)

            # Determine whether this track should be correlated this tick
            if rng < self.TIER_CRITICAL_NM:
                do_correlate = True               # always — every tick
            elif rng < self.TIER_NEAR_NM:
                do_correlate = (tick % 2 == 0)   # every 2nd tick (~5 Hz)
            else:
                do_correlate = (tick % 5 == 0)   # every 5th tick (~2 Hz)

            if not do_correlate:
                # Carry forward previous result if the AIS target is still live
                prev = self.correlated_tracks.get(radar_id)
                if prev and prev['ais_id'] in self.ais_tracks:
                    new_corr[radar_id] = prev
                continue

            # Spatial grid lookup — O(k), k << m in dense scenes
            candidates = self._get_ais_candidates(
                radar_track['lat'], radar_track['lon']
            )

            best_match = None
            best_distance = float('inf')
            for ais_id in candidates:
                ais_track = self.ais_tracks[ais_id]
                distance = self.calculate_distance(
                    radar_track['lat'], radar_track['lon'],
                    ais_track['lat'], ais_track['lon']
                )
                if distance < best_distance and distance < self.correlation_distance_nm:
                    best_distance = distance
                    best_match = ais_id

            if best_match:
                new_corr[radar_id] = {
                    'radar_id': radar_id,
                    'ais_id': best_match,
                    'distance': best_distance,
                    'radar_track': radar_track,
                    'ais_track': self.ais_tracks[best_match],
                }

        self.correlated_tracks = new_corr
                
    def cleanup_old_tracks(self, track_dict, current_time):
        """Remove tracks that haven't been updated recently"""
        to_remove = []
        for track_id, track in track_dict.items():
            if current_time - track['last_update'] > self.track_timeout:
                to_remove.append(track_id)

        for track_id in to_remove:
            del track_dict[track_id]
            # Clean up trail history and filters for expired tracks
            self.track_history.pop(track_id, None)
            self._last_trail_record.pop(track_id, None)
            self.track_filters.pop(track_id, None)
            
    def get_radar_tracks(self):
        """Get list of radar tracks (snapshot copy, thread-safe)."""
        with self._lock:
            return list(self.radar_tracks.values())

    def get_ais_tracks(self):
        """Get list of AIS tracks (snapshot copy, thread-safe)."""
        with self._lock:
            return list(self.ais_tracks.values())
        
    def get_correlated_tracks(self):
        """Get list of correlated tracks"""
        return list(self.correlated_tracks.values())
        
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two positions in nautical miles"""
        # Haversine formula
        R = 3440.065  # Earth radius in nautical miles
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = R * c
        return distance
        
    def generate_track_id(self, prefix):
        """Generate unique track ID"""
        import uuid
        return f"{prefix}-{uuid.uuid4().hex[:8]}"
