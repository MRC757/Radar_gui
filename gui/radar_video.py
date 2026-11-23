"""
Radar video buffer: accumulates spokes in polar form and renders a PPI image.

Spokes are stored north-referenced (true bearing) in a
``(num_angles, num_bins)`` uint8 array covering the current display range.
Rendering converts polar -> cartesian with a cached index lookup table, then
colours via a 256-entry ARGB palette — a few milliseconds per frame in numpy,
independent of how many spokes arrived.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QColor, QImage

METERS_PER_NM = 1852.0


class RadarVideoBuffer:
    MAX_GAP_FILL = 8        # fill up to this many missing angle cells between spokes
    MAX_RENDER_PX = 1024    # render resolution cap; the painter scales up from here

    def __init__(self, num_angles: int = 2048, num_bins: int = 512):
        self.num_angles = num_angles
        self.num_bins = num_bins
        self.range_m = 12.0 * METERS_PER_NM
        self.polar = np.zeros((num_angles, num_bins), dtype=np.uint8)
        self._last_idx = None
        self._lut_cache = {}       # size_px -> (pixel positions, polar indices, total)
        self._palette = np.zeros(256, dtype=np.uint32)
        self._image = None
        self._image_size = 0
        self._dirty = True
        self.last_true_azimuth = None
        self.set_colors(QColor(0, 200, 0), QColor(0, 255, 0))

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, num_angles: int, num_bins: int) -> None:
        """Resize the buffer (e.g. when a new radar reports its resolution)."""
        num_angles = max(64, int(num_angles))
        num_bins = max(64, min(int(num_bins), 2048))
        if (num_angles, num_bins) != (self.num_angles, self.num_bins):
            self.num_angles, self.num_bins = num_angles, num_bins
            self.polar = np.zeros((num_angles, num_bins), dtype=np.uint8)
            self._lut_cache.clear()
            self._last_idx = None
            self._dirty = True

    def set_range(self, range_nm: float) -> None:
        new_range = float(range_nm) * METERS_PER_NM
        if abs(new_range - self.range_m) > 1e-6:
            self.range_m = new_range
            self.clear()

    def set_colors(self, weak: QColor, strong: QColor, threshold: int = 12) -> None:
        """Build the 256-level palette from the theme's echo colours."""
        lvl = np.arange(256, dtype=np.float64) / 255.0
        t = np.clip((lvl - 0.25) / 0.5, 0.0, 1.0)     # blend weak -> strong
        r = weak.red() + (strong.red() - weak.red()) * t
        g = weak.green() + (strong.green() - weak.green()) * t
        b = weak.blue() + (strong.blue() - weak.blue()) * t
        a = np.clip(60 + lvl * 195, 0, 255)
        pal = ((a.astype(np.uint32) << 24) | (r.astype(np.uint32) << 16)
               | (g.astype(np.uint32) << 8) | b.astype(np.uint32))
        pal[:threshold] = 0
        self._palette[:] = pal
        self._dirty = True

    def clear(self) -> None:
        self.polar.fill(0)
        self._last_idx = None
        self.last_true_azimuth = None
        self._dirty = True

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def add_spokes(self, spokes, heading_deg: float = 0.0) -> None:
        """Write a batch of Spoke objects into the polar buffer."""
        if not spokes:
            return
        n_ang, n_bins = self.num_angles, self.num_bins
        bin_pos = (np.arange(n_bins) + 0.5) / n_bins * self.range_m   # metres

        for sp in spokes:
            samples = sp.samples
            n = samples.shape[0]
            if n == 0 or sp.range_m <= 0:
                continue
            true_az = sp.azimuth_deg if sp.true_bearing else sp.azimuth_deg + heading_deg
            true_az %= 360.0
            # Resample spoke onto display bins (handles any range mismatch)
            src = (bin_pos / sp.range_m * n).astype(np.int64)
            row = np.zeros(n_bins, dtype=np.uint8)
            valid = src < n
            row[valid] = samples[src[valid]]

            idx = int(true_az / 360.0 * n_ang) % n_ang
            last = self._last_idx
            if last is not None:
                gap = (idx - last) % n_ang
                if 1 < gap <= self.MAX_GAP_FILL:
                    fill = (np.arange(last + 1, last + gap) % n_ang)
                    self.polar[fill] = row
            self.polar[idx] = row
            self._last_idx = idx
            self.last_true_azimuth = true_az
        self._dirty = True

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _lookup(self, size: int) -> np.ndarray:
        lut = self._lut_cache.get(size)
        if lut is not None:
            return lut
        half = size / 2.0
        c = np.arange(size, dtype=np.float32) + 0.5 - half
        x, y = np.meshgrid(c, c)            # y grows downward
        r = np.sqrt(x * x + y * y) / half   # 0..1 at edge
        ang = (np.degrees(np.arctan2(x, -y)) + 360.0) % 360.0
        a_idx = (ang / 360.0 * self.num_angles).astype(np.int64) % self.num_angles
        r_idx = (r * self.num_bins).astype(np.int64)
        flat = a_idx * self.num_bins + r_idx
        flat = flat.ravel()
        inside = np.flatnonzero(r_idx.ravel() < self.num_bins)
        lut = (inside, flat[inside], size * size)
        self._lut_cache = {size: lut}       # keep only the current size
        return lut

    def render(self, diameter_px: int):
        """Return a QImage (north-up, own ship at centre) or None if empty."""
        size = int(min(max(diameter_px, 16), self.MAX_RENDER_PX))
        if not self._dirty and self._image is not None and self._image_size == size:
            return self._image
        inside, src, total = self._lookup(size)
        argb = np.zeros(total, dtype=np.uint32)
        argb[inside] = self._palette[self.polar.ravel()[src]]
        argb = argb.reshape(size, size)
        img = QImage(argb.data, size, size, size * 4, QImage.Format.Format_ARGB32)
        self._image = img.copy()          # detach from numpy memory
        self._image_size = size
        self._dirty = False
        return self._image
