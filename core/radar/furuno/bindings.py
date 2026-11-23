"""
ctypes bindings for the Furuno Sensor SDK.

!! THIS FILE IS A TEMPLATE.  The Furuno Sensor SDK is licensed and its header
!! file is not public, so every DLL symbol name, struct layout and callback
!! signature below is a PLACEHOLDER.  When you receive the SDK:
!!
!!   1. Open the SDK's C header (.h).
!!   2. Update the ctypes Structures to match field-for-field (order, types,
!!      packing — add ``_pack_`` if the header uses #pragma pack).
!!   3. Update the callback prototypes (ECHO_CALLBACK etc.).
!!   4. Update FUNCTION_TABLE: DLL symbol names, argtypes, restype.
!!      Symbol names can also be overridden per-installation with
!!      "symbol_map" in radar_config.json without editing this file.
!!   5. Set "calling_convention" in radar_config.json to "stdcall" if the
!!      header declares functions __stdcall / WINAPI, otherwise "cdecl".
!!
!! Keep this file free of Qt and GUI code: it is ONLY the C boundary.
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import struct
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


class FurunoSDKError(RuntimeError):
    """Raised when the SDK cannot be loaded or a call fails."""


# ---------------------------------------------------------------------------
# Structures — PLACEHOLDERS, replace with the layouts from the SDK header
# ---------------------------------------------------------------------------

class FurunoEchoData(ctypes.Structure):
    """One spoke of echo (video) data.  PLACEHOLDER layout."""
    _fields_ = [
        ('angle', ctypes.c_uint16),          # antenna angle, 0..angle_resolution-1
        ('angle_resolution', ctypes.c_uint16),  # angles per revolution (e.g. 2048/4096)
        ('range_m', ctypes.c_float),         # range of the last sample, metres
        ('sample_count', ctypes.c_uint32),   # number of samples in data
        ('data', ctypes.POINTER(ctypes.c_uint8)),  # echo strength per sample
    ]


class FurunoTargetData(ctypes.Structure):
    """One ARPA / TT target.  PLACEHOLDER layout."""
    _fields_ = [
        ('target_id', ctypes.c_int32),
        ('bearing_deg', ctypes.c_double),    # VERIFY: true or relative?
        ('range_m', ctypes.c_double),
        ('course_deg', ctypes.c_double),
        ('speed_kts', ctypes.c_double),
        ('state', ctypes.c_int32),           # VERIFY codes: 0=acquiring 1=tracking 2=lost ?
    ]


class FurunoStatusData(ctypes.Structure):
    """Radar health / state.  PLACEHOLDER layout."""
    _fields_ = [
        ('transmitting', ctypes.c_int32),
        ('warming_up', ctypes.c_int32),
        ('warmup_seconds', ctypes.c_int32),
        ('fault_flags', ctypes.c_uint32),    # bitfield, see FAULT_BITS
        ('operating_hours', ctypes.c_double),
        ('transmit_hours', ctypes.c_double),
        ('temperature_c', ctypes.c_double),
        ('firmware_version', ctypes.c_char * 32),
        ('serial_number', ctypes.c_char * 32),
    ]


# fault_flags bit -> RadarStatus attribute.  PLACEHOLDER bit positions.
FAULT_BITS = {
    0: 'transmitter_fault',
    1: 'motor_fault',
    2: 'over_temp',
    3: 'receiver_fault',
    4: 'power_supply_fault',
    5: 'signal_proc_fault',
}

# Target state codes -> RadarTarget.state.  PLACEHOLDER codes.
TARGET_STATES = {0: 'acquiring', 1: 'tracking', 2: 'lost'}


# ---------------------------------------------------------------------------
# Callback prototypes — PLACEHOLDERS
# ---------------------------------------------------------------------------
# These are created by make_callback_types() because cdecl (CFUNCTYPE) and
# stdcall (WINFUNCTYPE) need different factories.

def make_callback_types(calling_convention: str):
    factory = ctypes.CFUNCTYPE
    if calling_convention == 'stdcall':
        if not hasattr(ctypes, 'WINFUNCTYPE'):
            raise FurunoSDKError("stdcall callbacks are only available on Windows")
        factory = ctypes.WINFUNCTYPE
    return {
        # void on_echo(const FurunoEchoData* echo, void* user_data)
        'echo': factory(None, ctypes.POINTER(FurunoEchoData), ctypes.c_void_p),
        # void on_targets(const FurunoTargetData* targets, int count, void* user_data)
        'targets': factory(None, ctypes.POINTER(FurunoTargetData), ctypes.c_int, ctypes.c_void_p),
        # void on_status(const FurunoStatusData* status, void* user_data)
        'status': factory(None, ctypes.POINTER(FurunoStatusData), ctypes.c_void_p),
    }


# ---------------------------------------------------------------------------
# Function table — PLACEHOLDERS
# ---------------------------------------------------------------------------
# logical name -> (default DLL symbol, argtypes or callable(cb_types)->argtypes,
#                  restype, required)
# All functions are assumed to return 0 on success (VERIFY).

def _cb(kind):
    return lambda cb_types: [cb_types[kind], ctypes.c_void_p]


FUNCTION_TABLE: Dict[str, tuple] = {
    'init':                 ('FSDK_Initialize',        [],                                   ctypes.c_int, True),
    'shutdown':             ('FSDK_Terminate',         [],                                   ctypes.c_int, True),
    'connect':              ('FSDK_Connect',           [ctypes.c_char_p, ctypes.c_int],      ctypes.c_int, True),
    'disconnect':           ('FSDK_Disconnect',        [],                                   ctypes.c_int, True),
    'register_echo_cb':     ('FSDK_SetEchoCallback',   _cb('echo'),                          ctypes.c_int, True),
    'register_target_cb':   ('FSDK_SetTargetCallback', _cb('targets'),                       ctypes.c_int, False),
    'register_status_cb':   ('FSDK_SetStatusCallback', _cb('status'),                        ctypes.c_int, False),
    'get_status':           ('FSDK_GetStatus',         [ctypes.POINTER(FurunoStatusData)],   ctypes.c_int, False),
    'set_transmit':         ('FSDK_SetTransmit',       [ctypes.c_int],                       ctypes.c_int, True),
    'set_range':            ('FSDK_SetRange',          [ctypes.c_int],                       ctypes.c_int, True),   # range INDEX (VERIFY)
    'set_gain':             ('FSDK_SetGain',           [ctypes.c_int, ctypes.c_int],         ctypes.c_int, True),   # (value, auto)
    'set_sea':              ('FSDK_SetSea',            [ctypes.c_int, ctypes.c_int],         ctypes.c_int, False),
    'set_rain':             ('FSDK_SetRain',           [ctypes.c_int, ctypes.c_int],         ctypes.c_int, False),
    'set_interference_rej': ('FSDK_SetInterferenceRejection', [ctypes.c_int],                ctypes.c_int, False),
    'set_target_expansion': ('FSDK_SetTargetExpansion', [ctypes.c_int],                      ctypes.c_int, False),
    'set_nav_data':         ('FSDK_SetNavigationData', [ctypes.c_double] * 5,                ctypes.c_int, False),  # lat, lon, hdg, sog, cog
    'acquire_target':       ('FSDK_AcquireTarget',     [ctypes.c_double, ctypes.c_double],   ctypes.c_int, False),  # bearing deg, range m
    'cancel_target':        ('FSDK_CancelTarget',      [ctypes.c_int],                       ctypes.c_int, False),
    'cancel_all_targets':   ('FSDK_CancelAllTargets',  [],                                   ctypes.c_int, False),
    'get_last_error':       ('FSDK_GetLastErrorText',  [],                                   ctypes.c_char_p, False),
}


# ---------------------------------------------------------------------------
# Library loading
# ---------------------------------------------------------------------------

def _python_bits() -> int:
    return struct.calcsize('P') * 8


def load_library(dll_path: str, extra_dirs: Iterable[str] = (),
                 calling_convention: str = 'cdecl'):
    """Load the SDK DLL with the dependency search path set up correctly.

    Raises FurunoSDKError with an actionable message on failure.
    """
    if not dll_path:
        raise FurunoSDKError(
            "No 'dll_path' configured for this Furuno radar. "
            "Set it in Settings > Radar (see README: Furuno SDK DLLs).")
    path = Path(dll_path)
    if not path.is_file():
        raise FurunoSDKError(f"Furuno SDK DLL not found: {path}")

    dll_dirs = [str(path.parent)] + [d for d in extra_dirs if d]
    handles = []
    if sys.platform == 'win32':
        # Python 3.8+ no longer searches PATH for a DLL's dependencies.
        for d in dll_dirs:
            if os.path.isdir(d):
                handles.append(os.add_dll_directory(d))

    try:
        if calling_convention == 'stdcall' and sys.platform == 'win32':
            lib = ctypes.WinDLL(str(path))
        else:
            lib = ctypes.CDLL(str(path))
    except OSError as exc:
        hint = ''
        if sys.platform == 'win32':
            hint = (f" Python is {_python_bits()}-bit ({platform.machine()}); the DLL "
                    "must match.  Also check that the SDK's dependent DLLs and the "
                    "matching Visual C++ Redistributable are installed.")
        raise FurunoSDKError(f"Could not load {path}: {exc}.{hint}") from exc

    lib._dll_dir_handles = handles   # keep search-path entries alive
    return lib


class FurunoSDK:
    """Thin, typed wrapper around the DLL.

    Usage:
        sdk = FurunoSDK(dll_path, calling_convention='cdecl')
        sdk.check(sdk.call('init'), 'init')
    """

    def __init__(self, dll_path: str, extra_dirs: Iterable[str] = (),
                 calling_convention: str = 'cdecl',
                 symbol_map: Optional[Dict[str, str]] = None):
        self.lib = load_library(dll_path, extra_dirs, calling_convention)
        self.callback_types = make_callback_types(calling_convention)
        self._funcs: Dict[str, Callable] = {}
        symbol_map = symbol_map or {}

        missing_required = []
        for name, (symbol, argtypes, restype, required) in FUNCTION_TABLE.items():
            symbol = symbol_map.get(name, symbol)
            try:
                fn = getattr(self.lib, symbol)
            except AttributeError:
                if required:
                    missing_required.append(f"{name} ({symbol})")
                else:
                    logger.info("Furuno SDK: optional function %s (%s) not found", name, symbol)
                continue
            fn.argtypes = argtypes(self.callback_types) if callable(argtypes) else argtypes
            fn.restype = restype
            self._funcs[name] = fn

        if missing_required:
            raise FurunoSDKError(
                "Furuno SDK DLL loaded but required functions are missing: "
                + ", ".join(missing_required)
                + ".  Update FUNCTION_TABLE in core/radar/furuno/bindings.py or "
                  "'symbol_map' in radar_config.json to match the SDK header.")

    def has(self, name: str) -> bool:
        return name in self._funcs

    def call(self, name: str, *args: Any):
        fn = self._funcs.get(name)
        if fn is None:
            raise FurunoSDKError(f"SDK function '{name}' is not available")
        return fn(*args)

    def last_error(self) -> str:
        if self.has('get_last_error'):
            try:
                msg = self.call('get_last_error')
                return msg.decode(errors='replace') if msg else ''
            except Exception:  # pragma: no cover - defensive
                return ''
        return ''

    def check(self, result: int, what: str) -> None:
        """Raise FurunoSDKError if an SDK call returned non-zero (VERIFY convention)."""
        if result != 0:
            detail = self.last_error()
            raise FurunoSDKError(f"{what} failed (code {result}){': ' + detail if detail else ''}")
