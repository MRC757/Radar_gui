"""
RadarInterface — the contract every radar driver implements.

Threading model
---------------
Vendor SDKs usually deliver echo data from their own threads (callbacks).
Drivers MUST NOT touch Qt widgets from those threads.  Instead:

* Spokes:  call ``self._queue_spoke(spoke)`` from any thread.  The base class
  batches them and emits ``spokes_received(list[Spoke])`` on the GUI thread
  about 30 times a second.  This keeps cross-thread signal traffic low even
  at thousands of spokes per second.
* Everything else (targets, status, connection, errors): emit the signal
  directly.  Qt queues signals emitted from a non-GUI thread to the GUI
  thread automatically.

Lifecycle
---------
``start()`` must return immediately.  Slow work (loading a DLL, connecting
to the radar) belongs on a worker thread; report the result through
``connection_changed`` / ``error_occurred``.  ``stop()`` must unregister
SDK callbacks BEFORE releasing the SDK, and must be safe to call twice.
"""

from __future__ import annotations

import logging
import threading
from abc import ABCMeta, abstractmethod
from collections import deque
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .types import RadarCapabilities, RadarStatus, Spoke

logger = logging.getLogger(__name__)


class _ABCQObjectMeta(ABCMeta, type(QObject)):
    """Combined metaclass so RadarInterface can be both a QObject and an ABC."""


class RadarInterface(QObject, metaclass=_ABCQObjectMeta):
    """Abstract radar driver."""

    # --- Signals (all delivered on the GUI thread) -------------------------
    connection_changed = pyqtSignal(bool)        # True = link to radar up
    transmit_state_changed = pyqtSignal(bool)    # True = transmitting, False = standby
    spokes_received = pyqtSignal(list)           # list[Spoke], batched
    targets_updated = pyqtSignal(list)           # list[RadarTarget]
    status_changed = pyqtSignal(object)          # RadarStatus
    capabilities_changed = pyqtSignal(object)    # RadarCapabilities
    error_occurred = pyqtSignal(str)             # human-readable error

    SPOKE_FLUSH_INTERVAL_MS = 33

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.config: Dict[str, Any] = dict(config or {})
        self._spoke_queue: deque = deque(maxlen=16384)
        self._spoke_lock = threading.Lock()
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_spokes)

    # ------------------------------------------------------------------
    # Spoke batching (thread-safe)
    # ------------------------------------------------------------------

    def _queue_spoke(self, spoke: Spoke) -> None:
        """Queue a spoke for delivery to the GUI.  Safe from any thread."""
        with self._spoke_lock:
            self._spoke_queue.append(spoke)

    def _flush_spokes(self) -> None:
        with self._spoke_lock:
            if not self._spoke_queue:
                return
            batch = list(self._spoke_queue)
            self._spoke_queue.clear()
        self.spokes_received.emit(batch)

    def _start_spoke_delivery(self) -> None:
        """Call from start() (GUI thread) to begin batched delivery."""
        self._flush_timer.start(self.SPOKE_FLUSH_INTERVAL_MS)

    def _stop_spoke_delivery(self) -> None:
        self._flush_timer.stop()
        with self._spoke_lock:
            self._spoke_queue.clear()

    # ------------------------------------------------------------------
    # Required: lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def start(self) -> None:
        """Begin connecting.  Must not block the GUI thread."""

    @abstractmethod
    def stop(self) -> None:
        """Stop data, unregister callbacks, disconnect and release the SDK."""

    # ------------------------------------------------------------------
    # Required: information
    # ------------------------------------------------------------------

    @abstractmethod
    def get_capabilities(self) -> RadarCapabilities:
        """Return what this radar supports (ranges, controls, ARPA ...)."""

    @abstractmethod
    def get_status(self) -> RadarStatus:
        """Return the most recent hardware status.  Must not block."""

    # ------------------------------------------------------------------
    # Required: core controls
    # ------------------------------------------------------------------

    @abstractmethod
    def set_transmit(self, transmitting: bool) -> None:
        """Transmit (True) or standby (False).  Emit transmit_state_changed
        once the radar CONFIRMS the change."""

    @abstractmethod
    def set_range(self, range_nm: float) -> None:
        """Set display/instrumented range in nautical miles."""

    @abstractmethod
    def set_gain(self, gain_percent: int) -> None:
        """Manual gain 0-100 %."""

    @abstractmethod
    def set_sea_clutter(self, value: int) -> None:
        """Manual sea clutter (STC) 0-100 %."""

    @abstractmethod
    def set_rain_clutter(self, value: int) -> None:
        """Manual rain clutter (FTC) 0-100 %."""

    # ------------------------------------------------------------------
    # Optional controls — override when the radar supports them.
    # Defaults log and do nothing so the GUI can call them unconditionally.
    # ------------------------------------------------------------------

    def set_video_mode(self, mode: str) -> None:
        """'raw' or 'processed' video, where the radar distinguishes them."""
        logger.debug("%s: set_video_mode(%s) not supported", type(self).__name__, mode)

    def set_auto_gain(self, enabled: bool) -> None:
        logger.debug("%s: auto gain not supported", type(self).__name__)

    def set_auto_sea(self, enabled: bool) -> None:
        logger.debug("%s: auto sea not supported", type(self).__name__)

    def set_auto_rain(self, enabled: bool) -> None:
        logger.debug("%s: auto rain not supported", type(self).__name__)

    def set_interference_rejection(self, level: int) -> None:
        logger.debug("%s: interference rejection not supported", type(self).__name__)

    def set_target_expansion(self, enabled: bool) -> None:
        logger.debug("%s: target expansion not supported", type(self).__name__)

    def set_control(self, name: str, value: Any) -> None:
        """Vendor-specific control listed in capabilities.extra_controls."""
        logger.debug("%s: unknown control %s=%r", type(self).__name__, name, value)

    def set_own_ship(self, lat: float, lon: float, heading: float,
                     sog_kts: float, cog: float) -> None:
        """Feed own-ship navigation data to the radar.  Many SDKs need
        heading (and sometimes position) for ARPA and true-motion."""

    def acquire_target(self, bearing_deg: float, range_m: float) -> bool:
        """Ask the radar to acquire an ARPA target at a TRUE bearing / range.
        Returns True if the request was accepted."""
        return False

    def cancel_target(self, target_id: str) -> None:
        """Ask the radar to drop an ARPA target."""

    def cancel_all_targets(self) -> None:
        """Ask the radar to drop every ARPA target."""
