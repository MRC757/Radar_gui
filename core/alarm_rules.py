"""
Alarm rules — decides which alarm conditions are active.

Kept free of Qt and of the main window so every rule can be unit-tested.
``evaluate_alarms()`` returns, for EVERY alarm type it manages, either a
description (condition active -> trigger) or None (condition clear -> clear).
Each type is evaluated independently, so e.g. a critical CPA alarm clears as
soon as no target is critical, even if another target is still at warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional

MANAGED_ALARMS = ('cpa_critical', 'cpa_warning', 'guard_zone', 'sensor_loss',
                  'radar_link', 'radar_video')


@dataclass
class SensorState:
    gps_active: bool
    heading_active: bool
    depth_active: bool
    depth_seen: bool                 # depth has been received this session
    radar_selected: bool             # a radar driver is active
    radar_connected: bool
    radar_transmitting: bool
    seconds_without_video: Optional[float] = None   # since last spoke (or TX start)


def _ids(tracks, limit=3):
    ids = [str(t.get('name') or t.get('id', '?')) for t in tracks[:limit]]
    more = len(tracks) - limit
    return ', '.join(ids) + (f' +{more}' if more > 0 else '')


def evaluate_alarms(tracks: Iterable[dict],
                    intrusions: Mapping[str, set],
                    sensors: SensorState,
                    video_timeout_s: float = 5.0) -> Dict[str, Optional[str]]:
    tracks = list(tracks)
    result: Dict[str, Optional[str]] = {name: None for name in MANAGED_ALARMS}

    critical = [t for t in tracks if t.get('risk_level') == 'critical']
    warning = [t for t in tracks if t.get('risk_level') == 'warning']
    if critical:
        result['cpa_critical'] = f"Collision risk: {_ids(critical)}"
    if warning:
        result['cpa_warning'] = f"Close approach: {_ids(warning)}"

    intruded = [zone for zone, tgts in intrusions.items() if tgts]
    if intruded:
        result['guard_zone'] = f"Intrusion: {', '.join(intruded[:3])}"

    lost = []
    if not sensors.gps_active:
        lost.append('GPS')
    if not sensors.heading_active:
        lost.append('Heading')
    # Depth is optional: only alarm if it was working and then stopped
    if sensors.depth_seen and not sensors.depth_active:
        lost.append('Depth')
    if lost:
        result['sensor_loss'] = f"{', '.join(lost)} data offline"

    if sensors.radar_selected and not sensors.radar_connected:
        result['radar_link'] = "Radar connection lost"
    elif (sensors.radar_connected and sensors.radar_transmitting
          and sensors.seconds_without_video is not None
          and sensors.seconds_without_video > video_timeout_s):
        result['radar_video'] = (f"No radar video for "
                                 f"{sensors.seconds_without_video:.0f} s while transmitting")
    return result
