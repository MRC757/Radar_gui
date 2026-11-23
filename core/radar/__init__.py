"""
Radar driver package.

    from core.radar import create_radar
    radar = create_radar({'driver': 'furuno', 'model': 'DRS4D-NXT', ...})
"""

from .types import (METERS_PER_NM, RadarCapabilities, RadarStatus,
                    RadarTarget, Spoke)
from .base import RadarInterface
from .factory import available_drivers, create_radar, register_driver

__all__ = [
    'METERS_PER_NM', 'RadarCapabilities', 'RadarStatus', 'RadarTarget', 'Spoke',
    'RadarInterface', 'available_drivers', 'create_radar', 'register_driver',
]
