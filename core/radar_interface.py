"""
Backward-compatibility shim.

The radar API now lives in the core.radar package:
    core/radar/base.py      RadarInterface (abstract driver)
    core/radar/types.py     Spoke, RadarTarget, RadarStatus, RadarCapabilities
    core/radar/factory.py   create_radar(config)
    core/radar/mock.py      simulator
    core/radar/furuno/      Furuno Sensor SDK driver
"""

from core.radar.base import RadarInterface
from core.radar.mock import MockRadar as MockRadarInterface

__all__ = ['RadarInterface', 'MockRadarInterface']
