"""
End-to-end test of the Furuno ctypes driver against tests/fake_sdk/fake_furuno_sdk.dll.

Skipped unless FURUNO_FAKE_DLL points at the built DLL (see the .c file
header for build instructions).  When you have the REAL SDK you can point
the same test at it by also setting FURUNO_RADAR_IP to a live radar.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_radar_drivers import Collector, pump  # noqa: E402  (also creates QApplication)
from core.radar import create_radar  # noqa: E402

DLL = os.environ.get('FURUNO_FAKE_DLL', '')


@unittest.skipUnless(DLL and os.path.isfile(DLL), "FURUNO_FAKE_DLL not set / not built")
class FurunoFakeSDKTests(unittest.TestCase):
    def setUp(self):
        self.radar = create_radar({
            'driver': 'furuno', 'model': 'DRS4D-NXT', 'dll_path': DLL,
            'ip': os.environ.get('FURUNO_RADAR_IP', '192.168.1.100'), 'port': 10001,
        })
        self.c = Collector(self.radar)
        self.radar.start()
        pump(0.5)

    def tearDown(self):
        self.radar.stop()

    def test_connect_transmit_spokes_targets_status(self):
        self.assertEqual(self.c.connected, [True], self.c.errors)
        self.radar.set_range(3.0)
        self.radar.set_transmit(True)
        pump(2.5)
        self.assertEqual(self.c.tx, [True])               # confirmed via status poll
        self.assertGreater(len(self.c.spokes), 500)
        sp = self.c.spokes[-1]
        self.assertAlmostEqual(sp.range_m, 3.0 * 1852.0, delta=1.0)
        self.assertFalse(sp.true_bearing)
        self.assertTrue(self.c.targets)
        self.assertEqual(sorted(t.target_id for t in self.c.targets[-1]), ['7', '9'])
        st = self.radar.get_status()
        self.assertTrue(st.connected)
        self.assertEqual(st.firmware_version, 'FAKE-1.00')

    def test_stop_unregisters_cleanly(self):
        self.radar.set_transmit(True)
        pump(0.5)
        self.radar.stop()
        n = len(self.c.spokes)
        pump(0.5)
        self.assertLessEqual(len(self.c.spokes), n)
        self.assertEqual(self.c.connected[-1], False)


if __name__ == '__main__':
    unittest.main()
