"""
Furuno Sensor SDK radar driver.

Selected with ``"driver": "furuno"`` in radar_config.json.  All SDK calls are
made from ONE worker thread (SDKs are rarely thread-safe); GUI-thread methods
only enqueue commands.  SDK callbacks arrive on SDK threads and are converted
to Spoke / RadarTarget / RadarStatus objects immediately.

See core/radar/furuno/bindings.py for the parts that must be matched to the
real SDK header, and README.md ("Furuno SDK DLLs") for installation.
"""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from typing import Any, List, Optional

import numpy as np

from ..base import RadarInterface
from ..types import RadarStatus, RadarTarget, Spoke
from .models import capabilities_for

logger = logging.getLogger(__name__)

STATUS_POLL_S = 1.0
_STOP = object()


class FurunoRadar(RadarInterface):
    """Driver for Furuno DRS-NXT / FAR radar sensors via the Furuno Sensor SDK.

    Config keys (radar_config.json entry):
        model               e.g. "DRS4D-NXT"
        ip, port            radar / SDK network address
        dll_path            full path to the SDK DLL
        dll_dirs            optional list of extra folders holding dependent DLLs
        calling_convention  "cdecl" (default) or "stdcall"
        symbol_map          optional {logical_name: dll_symbol} overrides
        bearing_is_true     whether SDK target bearings are true (default False)
    """

    def __init__(self, config=None):
        super().__init__(config)
        self.model = self.config.get('model', 'DRS4D-NXT')
        self._caps = capabilities_for(self.model)
        self._status = RadarStatus(model=f'Furuno {self.model}')
        self._status_lock = threading.Lock()

        self._sdk = None
        self._thread: Optional[threading.Thread] = None
        self._cmds: "queue.Queue[Any]" = queue.Queue()
        self._stop_evt = threading.Event()
        self._callbacks = {}     # MUST keep references or ctypes callbacks get GC'd -> crash
        self._transmitting = False
        self._range_nm = 12.0
        self._accepting_callbacks = False

    # ------------------------------------------------------------------
    # Lifecycle (GUI thread)
    # ------------------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._start_spoke_delivery()
        self._thread = threading.Thread(target=self._worker, name='FurunoSDK', daemon=True)
        self._thread.start()

    def stop(self):
        if not self._thread:
            return
        self._stop_evt.set()
        self._cmds.put(_STOP)
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            logger.warning("Furuno SDK worker did not exit within 5 s")
        self._thread = None
        self._stop_spoke_delivery()

    def get_capabilities(self):
        return self._caps

    def get_status(self):
        with self._status_lock:
            return RadarStatus(**vars(self._status))

    # ------------------------------------------------------------------
    # Controls (GUI thread) — enqueue only, never block
    # ------------------------------------------------------------------

    def set_transmit(self, transmitting):
        self._enqueue('set_transmit', 1 if transmitting else 0)

    def set_range(self, range_nm):
        self._range_nm = float(range_nm)
        self._enqueue('set_range', self._range_to_sdk(range_nm))

    def set_gain(self, gain_percent):
        self._enqueue('set_gain', self._scale(gain_percent), 0)

    def set_auto_gain(self, enabled):
        self._enqueue('set_gain', 0, 1 if enabled else 0)

    def set_sea_clutter(self, value):
        self._enqueue('set_sea', self._scale(value), 0)

    def set_auto_sea(self, enabled):
        self._enqueue('set_sea', 0, 1 if enabled else 0)

    def set_rain_clutter(self, value):
        self._enqueue('set_rain', self._scale(value), 0)

    def set_auto_rain(self, enabled):
        self._enqueue('set_rain', 0, 1 if enabled else 0)

    def set_interference_rejection(self, level):
        self._enqueue('set_interference_rej', int(level))

    def set_target_expansion(self, enabled):
        self._enqueue('set_target_expansion', 1 if enabled else 0)

    def set_own_ship(self, lat, lon, heading, sog_kts, cog):
        self._enqueue('set_nav_data', float(lat), float(lon), float(heading or 0.0),
                      float(sog_kts or 0.0), float(cog if cog is not None else heading or 0.0),
                      quiet=True)

    def acquire_target(self, bearing_deg, range_m):
        if not self._caps.supports_arpa:
            return False
        self._enqueue('acquire_target', float(bearing_deg), float(range_m))
        return True

    def cancel_target(self, target_id):
        try:
            tid = int(str(target_id).split('-')[-1])
        except ValueError:
            logger.warning("Furuno: cannot cancel non-numeric target id %r", target_id)
            return
        self._enqueue('cancel_target', tid)

    def cancel_all_targets(self):
        self._enqueue('cancel_all_targets')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _enqueue(self, name, *args, quiet=False):
        self._cmds.put((name, args, quiet))

    def _scale(self, percent):
        lo, hi = self._caps.gain_range
        return int(round(lo + (hi - lo) * max(0, min(100, percent)) / 100.0))

    def _range_to_sdk(self, range_nm):
        """Map NM to the SDK's range value.  Assumes the SDK takes an INDEX
        into the model's range ladder (VERIFY — it may take metres or NM)."""
        ranges = self._caps.ranges_nm
        return min(range(len(ranges)), key=lambda i: abs(ranges[i] - range_nm))

    # ------------------------------------------------------------------
    # Worker thread — the ONLY place SDK functions are called
    # ------------------------------------------------------------------

    def _worker(self):
        try:
            self._open_sdk()
        except Exception as exc:
            logger.error("Furuno SDK start failed: %s", exc)
            self.error_occurred.emit(str(exc))
            self._close_sdk()
            return

        self.capabilities_changed.emit(self._caps)
        self.connection_changed.emit(True)

        next_poll = 0.0
        while not self._stop_evt.is_set():
            timeout = max(0.0, next_poll - time.monotonic())
            try:
                cmd = self._cmds.get(timeout=timeout)
            except queue.Empty:
                cmd = None
            if cmd is _STOP:
                break
            if cmd is not None:
                self._run_command(*cmd)
            if time.monotonic() >= next_poll:
                self._poll_status()
                next_poll = time.monotonic() + STATUS_POLL_S

        self._close_sdk()
        self.connection_changed.emit(False)

    def _open_sdk(self):
        from .bindings import FurunoSDK, FurunoSDKError  # deferred: only needed for real hardware

        cfg = self.config
        self._sdk = FurunoSDK(
            cfg.get('dll_path', ''),
            extra_dirs=cfg.get('dll_dirs', []),
            calling_convention=cfg.get('calling_convention', 'cdecl'),
            symbol_map=cfg.get('symbol_map'),
        )
        sdk = self._sdk
        sdk.check(sdk.call('init'), 'SDK initialise')

        cb_types = sdk.callback_types
        self._callbacks['echo'] = cb_types['echo'](self._on_echo)
        sdk.check(sdk.call('register_echo_cb', self._callbacks['echo'], None), 'register echo callback')
        if sdk.has('register_target_cb'):
            self._callbacks['targets'] = cb_types['targets'](self._on_targets)
            sdk.check(sdk.call('register_target_cb', self._callbacks['targets'], None),
                      'register target callback')
        if sdk.has('register_status_cb'):
            self._callbacks['status'] = cb_types['status'](self._on_status)
            sdk.check(sdk.call('register_status_cb', self._callbacks['status'], None),
                      'register status callback')
        self._accepting_callbacks = True

        ip = str(cfg.get('ip', '')).encode('ascii')
        port = int(cfg.get('port', 0))
        if not ip:
            raise FurunoSDKError("No radar IP address configured")
        sdk.check(sdk.call('connect', ip, port), f'connect to {ip.decode()}:{port}')

        with self._status_lock:
            self._status.connected = True
        logger.info("Furuno %s connected at %s:%s", self.model, ip.decode(), port)

    def _close_sdk(self):
        sdk = self._sdk
        self._accepting_callbacks = False
        if sdk is None:
            return
        # Unregister callbacks FIRST so the DLL can't call into freed objects.
        for name, kind in (('register_echo_cb', 'echo'),
                           ('register_target_cb', 'targets'),
                           ('register_status_cb', 'status')):
            if kind in self._callbacks and sdk.has(name):
                try:
                    null_cb = sdk.callback_types[kind]()   # NULL function pointer
                    sdk.call(name, null_cb, None)
                except Exception as exc:
                    logger.debug("Unregister %s failed: %s", name, exc)
        for name in ('disconnect', 'shutdown'):
            try:
                sdk.call(name)
            except Exception as exc:
                logger.debug("%s failed: %s", name, exc)
        self._callbacks.clear()
        self._sdk = None
        with self._status_lock:
            self._status.connected = False
            self._status.transmitting = False

    def _run_command(self, name, args, quiet):
        sdk = self._sdk
        if sdk is None or not sdk.has(name):
            if not quiet:
                logger.info("Furuno: %s not supported by this SDK build", name)
            return
        try:
            sdk.check(sdk.call(name, *args), name)
        except Exception as exc:
            logger.warning("Furuno command %s%s failed: %s", name, args, exc)
            if not quiet:
                self.error_occurred.emit(str(exc))

    def _poll_status(self):
        sdk = self._sdk
        if sdk is None or not sdk.has('get_status'):
            return
        from .bindings import FurunoStatusData
        data = FurunoStatusData()
        try:
            if sdk.call('get_status', ctypes.byref(data)) == 0:
                self._apply_status(data)
        except Exception as exc:
            logger.debug("get_status failed: %s", exc)

    # ------------------------------------------------------------------
    # SDK callbacks — run on SDK threads.  Never raise; never touch widgets.
    # ------------------------------------------------------------------

    def _on_echo(self, echo_ptr, _user):
        if not self._accepting_callbacks:
            return
        try:
            e = echo_ptr.contents
            n = int(e.sample_count)
            if n <= 0 or not e.data:
                return
            # COPY: the SDK reuses this buffer as soon as we return.
            samples = np.ctypeslib.as_array(e.data, shape=(n,)).copy()
            res = int(e.angle_resolution) or self._caps.spokes_per_revolution
            self._queue_spoke(Spoke(
                azimuth_deg=(int(e.angle) % res) * 360.0 / res,
                range_m=float(e.range_m),
                samples=samples,
                true_bearing=False,
            ))
        except Exception:
            logger.exception("Furuno echo callback error")

    def _on_targets(self, targets_ptr, count, _user):
        if not self._accepting_callbacks:
            return
        try:
            from .bindings import TARGET_STATES
            is_true = bool(self.config.get('bearing_is_true', False))
            out: List[RadarTarget] = []
            for i in range(int(count)):
                t = targets_ptr[i]
                state = TARGET_STATES.get(int(t.state), 'tracking')
                if state == 'lost':
                    continue
                out.append(RadarTarget(
                    target_id=str(int(t.target_id)),
                    bearing_deg=float(t.bearing_deg),
                    range_m=float(t.range_m),
                    bearing_is_true=is_true,
                    course_deg=float(t.course_deg),
                    speed_kts=float(t.speed_kts),
                    state=state,
                    filtered=True,
                ))
            self.targets_updated.emit(out)
        except Exception:
            logger.exception("Furuno target callback error")

    def _on_status(self, status_ptr, _user):
        if not self._accepting_callbacks:
            return
        try:
            self._apply_status(status_ptr.contents)
        except Exception:
            logger.exception("Furuno status callback error")

    def _apply_status(self, d):
        from .bindings import FAULT_BITS
        tx = bool(d.transmitting)
        with self._status_lock:
            s = self._status
            s.transmitting = tx
            s.warming_up = bool(d.warming_up)
            s.warmup_seconds_remaining = int(d.warmup_seconds)
            for bit, attr in FAULT_BITS.items():
                setattr(s, attr, bool(d.fault_flags & (1 << bit)))
            s.operating_hours = float(d.operating_hours)
            s.transmit_hours = float(d.transmit_hours)
            s.temperature_c = float(d.temperature_c)
            s.firmware_version = d.firmware_version.decode(errors='replace').rstrip('\x00')
            s.serial_number = d.serial_number.decode(errors='replace').rstrip('\x00')
            snapshot = RadarStatus(**vars(s))
        if tx != self._transmitting:
            self._transmitting = tx
            self.transmit_state_changed.emit(tx)   # confirmed by hardware
        self.status_changed.emit(snapshot)
