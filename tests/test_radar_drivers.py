"""
Radar driver contract tests.

Run:  python -m unittest discover -s tests -v
(Uses Qt's offscreen platform; no display or radar hardware needed.)
"""

import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from core.radar import (RadarCapabilities, RadarStatus, RadarTarget, Spoke,
                        available_drivers, create_radar)
from core.radar.furuno.models import SUPPORTED_MODELS, capabilities_for
from core.track_manager import TrackManager

app = QApplication.instance() or QApplication([])


def pump(seconds):
    """Run the Qt event loop for a while so timers and queued signals fire."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


class Collector:
    def __init__(self, radar):
        self.spokes, self.targets, self.connected, self.tx, self.errors = [], [], [], [], []
        radar.spokes_received.connect(self.spokes.extend)
        radar.targets_updated.connect(self.targets.append)
        radar.connection_changed.connect(self.connected.append)
        radar.transmit_state_changed.connect(self.tx.append)
        radar.error_occurred.connect(self.errors.append)


class FactoryTests(unittest.TestCase):
    def test_builtin_drivers_registered(self):
        self.assertIn('mock', available_drivers())
        self.assertIn('furuno', available_drivers())

    def test_unknown_driver_raises(self):
        with self.assertRaises(ValueError):
            create_radar({'driver': 'no-such-radar'})

    def test_default_is_mock(self):
        r = create_radar({})
        self.assertEqual(type(r).__name__, 'MockRadar')


class MockRadarTests(unittest.TestCase):
    def setUp(self):
        self.radar = create_radar({'driver': 'mock'})
        self.c = Collector(self.radar)
        self.radar.start()

    def tearDown(self):
        self.radar.stop()

    def test_connects_and_reports_capabilities(self):
        pump(0.05)
        self.assertEqual(self.c.connected, [True])
        caps = self.radar.get_capabilities()
        self.assertIsInstance(caps, RadarCapabilities)
        self.assertTrue(caps.ranges_nm)
        self.assertIsInstance(self.radar.get_status(), RadarStatus)

    def test_no_video_in_standby(self):
        pump(0.3)
        self.assertEqual(self.c.spokes, [])

    def test_transmit_produces_spokes(self):
        self.radar.set_transmit(True)
        pump(0.5)
        self.assertEqual(self.c.tx, [True])
        self.assertGreater(len(self.c.spokes), 50)
        sp = self.c.spokes[0]
        self.assertIsInstance(sp, Spoke)
        self.assertEqual(sp.samples.dtype, np.uint8)
        self.assertTrue(0.0 <= sp.azimuth_deg < 360.0)

    def test_targets_have_stable_ids(self):
        self.radar.set_transmit(True)
        pump(2.3)
        self.assertGreaterEqual(len(self.c.targets), 2)
        ids = [sorted(t.target_id for t in batch) for batch in self.c.targets]
        self.assertTrue(all(i == ids[0] for i in ids), ids)
        self.assertIsInstance(self.c.targets[0][0], RadarTarget)


class FurunoDriverTests(unittest.TestCase):
    def test_missing_dll_reports_error_not_crash(self):
        radar = create_radar({'driver': 'furuno', 'model': 'DRS4D-NXT',
                              'dll_path': r'C:\does\not\exist\sdk.dll',
                              'ip': '192.168.1.100', 'port': 10001})
        c = Collector(radar)
        radar.start()
        pump(0.5)
        radar.stop()
        self.assertTrue(c.errors, "expected error_occurred")
        self.assertIn('not found', c.errors[0])
        self.assertNotIn(True, c.connected)

    def test_model_capabilities(self):
        for m in SUPPORTED_MODELS:
            caps = capabilities_for(m)
            self.assertTrue(caps.ranges_nm, m)
            self.assertTrue(caps.supports_arpa, m)
        self.assertEqual(max(capabilities_for('DRS4D-NXT').ranges_nm), 36.0)


class VideoBufferTests(unittest.TestCase):
    def test_render_shows_echo_at_right_place(self):
        from gui.radar_video import RadarVideoBuffer
        buf = RadarVideoBuffer(num_angles=360, num_bins=100)
        buf.set_range(1.0)
        samples = np.zeros(100, dtype=np.uint8)
        samples[50:60] = 255                      # echo at ~0.5 NM
        buf.add_spokes([Spoke(azimuth_deg=90.0, range_m=1852.0, samples=samples)],
                       heading_deg=0.0)
        img = buf.render(200)
        # East of centre, ~half radius out -> lit; west -> dark
        self.assertGreater(img.pixelColor(155, 100).alpha(), 0)
        self.assertEqual(img.pixelColor(45, 100).alpha(), 0)

    def test_relative_spoke_rotated_by_heading(self):
        from gui.radar_video import RadarVideoBuffer
        buf = RadarVideoBuffer(num_angles=360, num_bins=100)
        buf.set_range(1.0)
        samples = np.full(100, 255, dtype=np.uint8)
        buf.add_spokes([Spoke(azimuth_deg=0.0, range_m=1852.0, samples=samples)],
                       heading_deg=90.0)
        self.assertAlmostEqual(buf.last_true_azimuth, 90.0)


class TrackAssociationTests(unittest.TestCase):
    def test_idless_plots_reuse_track(self):
        tm = TrackManager()
        tm.update_own_ship(37.0, -76.3, 0.0, 0.0)
        for k in range(5):
            tm.update_radar_tracks([{'lat': 37.01 + k * 1e-5, 'lon': -76.29,
                                     'course': 0.0, 'speed': 5.0}])
        self.assertEqual(len(tm.get_radar_tracks()), 1)

    def test_radar_filtered_targets_keep_reported_course(self):
        tm = TrackManager()
        tm.update_own_ship(37.0, -76.3, 0.0, 0.0)
        tm.update_radar_tracks([{'id': 'R-1', 'lat': 37.02, 'lon': -76.3,
                                 'course': 123.0, 'speed': 9.5, 'filtered': True}])
        trk = tm.get_radar_tracks()[0]
        self.assertAlmostEqual(trk['course'], 123.0)
        self.assertAlmostEqual(trk['speed'], 9.5)


if __name__ == '__main__':
    unittest.main()
