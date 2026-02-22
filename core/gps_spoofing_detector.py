"""
GPS Spoofing Detector
Monitors GPS fix data for anomalies that indicate spoofing:
  - UTC time jumps (backward or large forward)
  - Speed exceeding 40 knots
  - Position jumps implying impossible speed
"""

import math
from datetime import datetime
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal


class SpoofingState(Enum):
    NORMAL = "NORMAL"
    ALERT = "ALERT"


class GPSSpoofingDetector(QObject):
    """Detect GPS spoofing from consecutive fix analysis."""

    # Signal emitted with a human-readable description of the alert
    spoofing_alert = pyqtSignal(str)

    # Thresholds
    MAX_SPEED_KNOTS = 40.0
    MAX_IMPLIED_SPEED_KNOTS = 60.0
    MAX_TIME_FORWARD_JUMP_SEC = 10.0
    ALERT_COOLDOWN_SEC = 30.0

    def __init__(self, parent=None):
        super().__init__(parent)

        self.state = SpoofingState.NORMAL
        self.alert_history = []  # [(datetime, description), ...]

        # Previous fix tracking
        self._prev_utc_seconds = None
        self._prev_lat = None
        self._prev_lon = None
        self._prev_fix_time = None  # wall-clock datetime

        # Cooldown: { alert_type: last_alert_datetime }
        self._last_alert_times = {}

    def update_fix(self, utc_seconds, lat, lon, speed_knots):
        """Called on every GGA fix with parsed data.

        Args:
            utc_seconds: float or None -- UTC time-of-day in seconds
            lat: float -- latitude in decimal degrees
            lon: float -- longitude in decimal degrees
            speed_knots: float -- speed from VTG
        """
        now = datetime.now()

        # --- Check 1: UTC time jump ---
        if utc_seconds is not None and self._prev_utc_seconds is not None:
            delta = utc_seconds - self._prev_utc_seconds
            # Ignore midnight rollover (delta near -86400)
            if delta < -1.0 and delta > -85000:
                self._raise_alert(
                    "TIME JUMP",
                    f"GPS UTC time jumped backward by {abs(delta):.1f}s",
                    now,
                )
            elif delta > self.MAX_TIME_FORWARD_JUMP_SEC:
                self._raise_alert(
                    "TIME JUMP",
                    f"GPS UTC time jumped forward by {delta:.1f}s "
                    f"(threshold: {self.MAX_TIME_FORWARD_JUMP_SEC}s)",
                    now,
                )

        # --- Check 2: Speed exceeding threshold ---
        if speed_knots > self.MAX_SPEED_KNOTS:
            self._raise_alert(
                "OVERSPEED",
                f"Own ship speed {speed_knots:.1f} kts exceeds "
                f"{self.MAX_SPEED_KNOTS:.0f} kts limit",
                now,
            )

        # --- Check 3: Position jump (implied speed) ---
        if (self._prev_lat is not None and self._prev_lon is not None
                and self._prev_fix_time is not None):
            elapsed = (now - self._prev_fix_time).total_seconds()
            if elapsed > 0.1:
                distance_nm = self._haversine_nm(
                    self._prev_lat, self._prev_lon, lat, lon
                )
                implied_speed = distance_nm / (elapsed / 3600.0)
                if implied_speed > self.MAX_IMPLIED_SPEED_KNOTS:
                    self._raise_alert(
                        "POSITION JUMP",
                        f"Position jump implies {implied_speed:.1f} kts "
                        f"({distance_nm:.3f} NM in {elapsed:.1f}s)",
                        now,
                    )

        # Update previous-fix state
        if utc_seconds is not None:
            self._prev_utc_seconds = utc_seconds
        self._prev_lat = lat
        self._prev_lon = lon
        self._prev_fix_time = now

    @property
    def is_alert(self):
        return self.state == SpoofingState.ALERT

    def clear_alert(self):
        """Operator acknowledgement -- reset state to NORMAL."""
        self.state = SpoofingState.NORMAL

    def _raise_alert(self, alert_type, description, now):
        """Emit alert signal with cooldown to avoid flooding."""
        last = self._last_alert_times.get(alert_type)
        if last and (now - last).total_seconds() < self.ALERT_COOLDOWN_SEC:
            return

        self.state = SpoofingState.ALERT
        self._last_alert_times[alert_type] = now
        self.alert_history.append((now, description))

        # Keep history bounded
        if len(self.alert_history) > 200:
            self.alert_history = self.alert_history[-100:]

        self.spoofing_alert.emit(f"GPS SPOOFING: {description}")

    @staticmethod
    def _haversine_nm(lat1, lon1, lat2, lon2):
        """Haversine distance in nautical miles."""
        R = 3440.065  # Earth radius in NM
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat1))
             * math.cos(math.radians(lat2))
             * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
