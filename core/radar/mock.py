"""
Simulated radar driver.

Produces the same data a real SDK driver does — spokes and ARPA targets with
stable IDs — so the whole GUI pipeline is exercised without hardware.
Selected with ``"driver": "mock"`` in radar_config.json.
"""

from __future__ import annotations

import logging
import math
import time
from typing import List

import numpy as np
from PyQt6.QtCore import QTimer

from .base import RadarInterface
from .types import METERS_PER_NM, RadarCapabilities, RadarStatus, RadarTarget, Spoke

logger = logging.getLogger(__name__)


class _SimTarget:
    """Target moving at constant velocity, position as metres from own ship."""

    def __init__(self, tid, bearing_deg, range_nm, course, speed_kts, size_m=60.0):
        self.tid = tid
        r = range_nm * METERS_PER_NM
        self.x = r * math.sin(math.radians(bearing_deg))   # east
        self.y = r * math.cos(math.radians(bearing_deg))   # north
        self.course = course
        self.speed = speed_kts
        self.size_m = size_m

    def step(self, dt, own_cog, own_sog):
        # Relative motion: target velocity minus own-ship velocity
        v = self.speed * METERS_PER_NM / 3600.0
        ov = own_sog * METERS_PER_NM / 3600.0
        self.x += (v * math.sin(math.radians(self.course))
                   - ov * math.sin(math.radians(own_cog))) * dt
        self.y += (v * math.cos(math.radians(self.course))
                   - ov * math.cos(math.radians(own_cog))) * dt

    @property
    def bearing(self):
        return math.degrees(math.atan2(self.x, self.y)) % 360.0

    @property
    def range_m(self):
        return math.hypot(self.x, self.y)


class MockRadar(RadarInterface):
    """Simulated radar."""

    SPOKES_PER_REV = 2048
    SAMPLES = 512
    RPM = 24.0
    TICK_MS = 33

    def __init__(self, config=None):
        super().__init__(config)
        self._caps = RadarCapabilities(
            model='Simulator',
            ranges_nm=[0.125, 0.25, 0.5, 0.75, 1.5, 3.0, 6.0, 12.0, 24.0, 36.0],
            spokes_per_revolution=self.SPOKES_PER_REV,
            max_samples_per_spoke=self.SAMPLES,
            supports_auto_gain=True, supports_auto_sea=True,
            supports_arpa=True, max_arpa_targets=100,
        )
        self._status = RadarStatus(model='Simulator', firmware_version='sim-1.0')

        self.range_nm = 12.0
        self.gain = 50
        self.sea_clutter = 0
        self.rain_clutter = 0
        self.video_mode = 'processed'
        self.transmitting = False
        self.connected = False

        self._heading = 0.0
        self._own_sog = 0.0
        self._own_cog = 0.0

        self._spoke_index = 0
        self._spoke_accum = 0.0
        self._last_tick = None
        self._target_accum = 0.0
        self._rng = np.random.default_rng()

        self._targets: List[_SimTarget] = [
            _SimTarget('1', 30, 2.0, 225, 12),
            _SimTarget('2', 120, 4.5, 300, 8),
            _SimTarget('3', 250, 6.0, 90, 15),
            _SimTarget('4', 340, 1.2, 160, 5, size_m=25),
        ]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        logger.info("Mock radar: starting")
        self.connected = True
        self._status.connected = True
        self._last_tick = time.monotonic()
        self._timer.start(self.TICK_MS)
        self._start_spoke_delivery()
        self.capabilities_changed.emit(self._caps)
        self.connection_changed.emit(True)

    def stop(self):
        if not self.connected:
            return
        logger.info("Mock radar: stopping")
        self._timer.stop()
        self._stop_spoke_delivery()
        self.connected = False
        self.transmitting = False
        self._status.connected = False
        self._status.transmitting = False
        self.connection_changed.emit(False)

    def get_capabilities(self):
        return self._caps

    def get_status(self):
        return self._status

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def set_transmit(self, transmitting):
        self.transmitting = bool(transmitting)
        self._status.transmitting = self.transmitting
        logger.info("Mock radar: %s", "TRANSMIT" if transmitting else "STANDBY")
        self.transmit_state_changed.emit(self.transmitting)
        if not self.transmitting:
            self.targets_updated.emit([])

    def set_range(self, range_nm):
        self.range_nm = float(range_nm)

    def set_gain(self, gain_percent):
        self.gain = int(gain_percent)

    def set_sea_clutter(self, value):
        self.sea_clutter = int(value)

    def set_rain_clutter(self, value):
        self.rain_clutter = int(value)

    def set_video_mode(self, mode):
        self.video_mode = mode

    def set_own_ship(self, lat, lon, heading, sog_kts, cog):
        self._heading = heading or 0.0
        self._own_sog = sog_kts or 0.0
        self._own_cog = cog if cog is not None else self._heading

    def acquire_target(self, bearing_deg, range_m):
        # Simulator tracks all its targets already; accept and ignore.
        return True

    def cancel_target(self, target_id):
        logger.info("Mock radar: cancel target %s", target_id)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _tick(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        for t in self._targets:
            t.step(dt, self._own_cog, self._own_sog)

        if not self.transmitting:
            return

        # Spokes due this tick
        self._spoke_accum += dt * self.RPM / 60.0 * self.SPOKES_PER_REV
        n = int(self._spoke_accum)
        self._spoke_accum -= n
        for _ in range(n):
            self._queue_spoke(self._make_spoke(self._spoke_index))
            self._spoke_index = (self._spoke_index + 1) % self.SPOKES_PER_REV

        # ARPA target report once per second
        self._target_accum += dt
        if self._target_accum >= 1.0:
            self._target_accum = 0.0
            self.targets_updated.emit(self._make_targets())

    def _make_spoke(self, index) -> Spoke:
        rel_az = index * 360.0 / self.SPOKES_PER_REV
        true_az = (rel_az + self._heading) % 360.0
        range_m = self.range_nm * METERS_PER_NM
        n = self.SAMPLES
        r = np.linspace(0, range_m, n, endpoint=False)

        gain = self.gain / 100.0
        noise_level = 40.0 if self.video_mode == 'raw' else 15.0
        echo = self._rng.random(n) * noise_level * gain

        # Sea clutter: strong close in, decays with range, reduced by STC
        sea = 180.0 * np.exp(-r / 600.0) * (1.0 - self.sea_clutter / 100.0)
        echo += sea * self._rng.random(n)

        # Land mass to the south-west
        if 200.0 <= true_az <= 260.0:
            coast = 5.0 * METERS_PER_NM + 400.0 * math.sin(math.radians(true_az * 7))
            land = r > coast
            echo[land] += (200.0 * gain + 30.0) * (0.45 + 0.55 * self._rng.random(int(land.sum())))

        # Targets
        bin_m = range_m / n
        for t in self._targets:
            diff = abs((true_az - t.bearing + 180.0) % 360.0 - 180.0)
            tr = t.range_m
            if tr >= range_m:
                continue
            ang_width = max(1.2, math.degrees(t.size_m / max(tr, 1.0)))
            if diff <= ang_width:
                i0 = int((tr - t.size_m / 2) / bin_m)
                i1 = max(i0 + 1, int((tr + t.size_m / 2) / bin_m) + 1)
                echo[max(i0, 0):min(i1, n)] += 230.0 * (0.6 + 0.4 * gain)

        samples = np.clip(echo, 0, 255).astype(np.uint8)
        return Spoke(azimuth_deg=rel_az, range_m=range_m, samples=samples)

    def _make_targets(self) -> List[RadarTarget]:
        out = []
        for t in self._targets:
            if t.range_m > 36 * METERS_PER_NM:
                continue
            out.append(RadarTarget(
                target_id=t.tid,
                bearing_deg=t.bearing + self._rng.normal(0, 0.2),
                range_m=t.range_m + self._rng.normal(0, 5),
                bearing_is_true=True,
                course_deg=t.course,
                speed_kts=t.speed,
                state='tracking',
                filtered=True,
            ))
        return out
