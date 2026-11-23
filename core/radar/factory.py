"""
Radar driver registry.

A radar_config.json entry's "driver" field picks the class.  Drivers are
registered as "module:Class" strings and imported lazily, so the simulator
never imports ctypes/SDK code and a broken SDK driver can't stop the app
from starting.

To add a new vendor:
    register_driver('vendor_x', 'drivers.vendor_x.driver:VendorXRadar')
or add it to _BUILTIN_DRIVERS below.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, Type, Union

from .base import RadarInterface

logger = logging.getLogger(__name__)

_BUILTIN_DRIVERS: Dict[str, str] = {
    'mock': 'core.radar.mock:MockRadar',
    'furuno': 'core.radar.furuno.driver:FurunoRadar',
}

_registry: Dict[str, Union[str, Type[RadarInterface]]] = dict(_BUILTIN_DRIVERS)


def register_driver(name: str, cls: Union[str, Type[RadarInterface]]) -> None:
    """Register a driver class (or "module:Class" import string)."""
    _registry[name] = cls


def available_drivers():
    return sorted(_registry)


def _resolve(name: str) -> Type[RadarInterface]:
    entry = _registry.get(name)
    if entry is None:
        raise ValueError(f"Unknown radar driver '{name}'. "
                         f"Available: {', '.join(available_drivers())}")
    if isinstance(entry, str):
        module_name, _, cls_name = entry.partition(':')
        entry = getattr(importlib.import_module(module_name), cls_name)
        _registry[name] = entry
    if not issubclass(entry, RadarInterface):
        raise TypeError(f"Driver '{name}' is not a RadarInterface subclass")
    return entry


def create_radar(config: Dict[str, Any]) -> RadarInterface:
    """Instantiate the driver named by config['driver'] (default 'mock')."""
    name = (config or {}).get('driver', 'mock')
    cls = _resolve(name)
    logger.info("Creating radar driver '%s' (%s) for %s",
                name, cls.__name__, (config or {}).get('name', '?'))
    return cls(config)
