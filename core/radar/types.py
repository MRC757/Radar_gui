"""
Radar data types shared by every radar driver and the GUI.

These are deliberately SDK-neutral.  A driver's only job is to translate the
vendor's structs / callbacks into these objects; nothing in the GUI ever sees
a vendor type.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

METERS_PER_NM = 1852.0


@dataclass
class Spoke:
    """One radial line of radar video.

    Attributes:
        azimuth_deg: Antenna angle in degrees, clockwise from the BOW
                     (i.e. relative/head-up).  Set ``true_bearing=True`` if
                     the SDK already reports true (north-referenced) angles.
        range_m:     Range in metres covered by the LAST sample in ``samples``.
        samples:     1-D ``np.uint8`` array of echo strength (0 = none,
                     255 = strongest).  Drivers must hand over a COPY — never
                     a view onto an SDK-owned buffer.
        timestamp:   ``time.monotonic()`` when the spoke was received.
        true_bearing: True if ``azimuth_deg`` is already north-referenced.
    """
    azimuth_deg: float
    range_m: float
    samples: np.ndarray
    timestamp: float = field(default_factory=time.monotonic)
    true_bearing: bool = False


@dataclass
class RadarTarget:
    """An ARPA / TT target reported by the radar itself.

    Position is given as bearing/range from own ship because that is what
    radar SDKs report.  The GUI converts to lat/lon using own-ship data.

    Attributes:
        target_id:     Stable ID from the radar (must not change between
                       updates of the same target).
        bearing_deg:   Bearing from own ship, degrees.
        range_m:       Range from own ship, metres.
        bearing_is_true: False if ``bearing_deg`` is relative to the bow.
        course_deg:    Target course over ground (true), or None if unknown.
        speed_kts:     Target speed over ground, or None if unknown.
        state:         'acquiring' | 'tracking' | 'lost'
        filtered:      True if the radar already applies its own tracking
                       filter (the GUI then skips its Kalman filter).
    """
    target_id: str
    bearing_deg: float
    range_m: float
    bearing_is_true: bool = True
    course_deg: Optional[float] = None
    speed_kts: Optional[float] = None
    state: str = 'tracking'
    filtered: bool = True


@dataclass
class RadarStatus:
    """Hardware health and state, polled by the BIT window."""
    connected: bool = False
    transmitting: bool = False
    warming_up: bool = False
    warmup_seconds_remaining: int = 0
    transmitter_fault: bool = False
    motor_fault: bool = False
    over_temp: bool = False
    receiver_fault: bool = False
    power_supply_fault: bool = False
    signal_proc_fault: bool = False
    display_fault: bool = False
    operating_hours: Optional[float] = None
    transmit_hours: Optional[float] = None
    temperature_c: Optional[float] = None
    firmware_version: str = ''
    model: str = ''
    serial_number: str = ''
    message: str = ''

    def fault_dict(self) -> Dict[str, bool]:
        """Return fault flags keyed by the names the BIT window uses."""
        return {
            'transmitter_fault': self.transmitter_fault,
            'motor_fault': self.motor_fault,
            'over_temp': self.over_temp,
            'receiver_fault': self.receiver_fault,
            'power_supply_fault': self.power_supply_fault,
            'signal_proc_fault': self.signal_proc_fault,
            'display_fault': self.display_fault,
        }


@dataclass
class RadarCapabilities:
    """What a particular radar/driver supports.  The GUI adapts to this."""
    model: str = 'Unknown'
    ranges_nm: List[float] = field(default_factory=lambda: [
        0.125, 0.25, 0.5, 0.75, 1.5, 3.0, 6.0, 12.0, 24.0, 36.0])
    spokes_per_revolution: int = 2048
    max_samples_per_spoke: int = 1024
    gain_range: Tuple[int, int] = (0, 100)
    supports_auto_gain: bool = False
    supports_auto_sea: bool = False
    supports_auto_rain: bool = False
    supports_interference_rejection: bool = False
    supports_target_expansion: bool = False
    supports_arpa: bool = False
    max_arpa_targets: int = 0
    supports_doppler: bool = False
    supports_blind_sectors: bool = False
    requires_heading_input: bool = False
    requires_position_input: bool = False
    extra_controls: List[str] = field(default_factory=list)
