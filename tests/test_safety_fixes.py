"""
Regression tests for the code-review safety / correctness fixes.

Run:  python -m unittest discover -s tests -v
"""

import math
import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication

from core.alarm_manager import AlarmManager
from core.alarm_rules import SensorState, evaluate_alarms
from core.cpa_calculator import CPACalculator
from core.guard_zone import GuardZone, GuardZoneManager
from core.multi_source_nmea_parser import MultiSourceNMEAParser
from core.test_scenarios import ScenarioRunner
from core.track_filter import KalmanTrackFilter
from core.track_manager import TrackManager

app = QApplication.instance() or QApplication([])

# Keep test alarm events out of the real logs/alarm_log.txt
import tempfile  # noqa: E402
import core.alarm_manager as _am  # noqa: E402
_am._LOG_DIR = Path(tempfile.mkdtemp(prefix='radar_test_logs_'))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def nmea(body):
    """Add '$' framing and checksum to a sentence body."""
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"${body}*{cs:02X}"


def aivdm(payload, pad=0, frag_count=1, frag_num=1, seq='', channel='A'):
    body = f"AIVDM,{frag_count},{frag_num},{seq},{channel},{payload},{pad}"
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"!{body}*{cs:02X}"


def put(bits, start, length, value):
    if value < 0:
        value += 1 << length
    for i in range(length):
        bits[start + i] = (value >> (length - 1 - i)) & 1


def armor(bits):
    pad = (6 - len(bits) % 6) % 6
    bits = bits + [0] * pad
    out = []
    for i in range(0, len(bits), 6):
        v = 0
        for b in bits[i:i + 6]:
            v = (v << 1) | b
        v += 48
        if v > 87:
            v += 8
        out.append(chr(v))
    return ''.join(out), pad


def type1(mmsi, lat, lon, sog_raw, cog_raw, hdg=511):
    bits = [0] * 168
    put(bits, 0, 6, 1)
    put(bits, 8, 30, mmsi)
    put(bits, 50, 10, sog_raw)
    put(bits, 61, 28, int(round(lon * 600000)))
    put(bits, 89, 27, int(round(lat * 600000)))
    put(bits, 116, 12, cog_raw)
    put(bits, 128, 9, hdg)
    return armor(bits)


def type5(mmsi, name):
    bits = [0] * 424
    put(bits, 0, 6, 5)
    put(bits, 8, 30, mmsi)
    chars = "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_ !\"#$%&'()*+,-./0123456789:;<=>?"
    for i, ch in enumerate(name.ljust(20, '@')[:20]):
        put(bits, 112 + i * 6, 6, chars.index(ch))
    return armor(bits)


def make_parser():
    p = MultiSourceNMEAParser()
    p.ais_decryptor._keys = []          # no decryption in these tests
    return p


# ---------------------------------------------------------------------------
# 1. GPS fix loss / checksum
# ---------------------------------------------------------------------------

class GpsFixTests(unittest.TestCase):
    def setUp(self):
        self.p = make_parser()
        self.src = self.p.gps_sources[0]
        self.pos = []
        self.p.position_updated.connect(lambda *a: self.pos.append(a[:2]))

    def test_gga_without_fix_is_ignored(self):
        self.p.parse_sentence(nmea("GPGGA,120000.00,3700.000,N,07618.000,W,1,08,0.9,10.0,M,,M,,"), self.src)
        self.p.parse_sentence(nmea("GPGGA,120001.00,,,,,0,00,,,M,,M,,"), self.src)
        self.p.parse_sentence(nmea("GPGGA,120002.00,3700.000,N,07618.000,W,0,00,,,M,,M,,"), self.src)
        self.assertEqual(self.pos, [(37.0, -76.3)])
        self.assertEqual((self.p.latitude, self.p.longitude), (37.0, -76.3))

    def test_rmc_void_and_empty_ignored(self):
        self.p.parse_sentence(nmea("GPRMC,120000,V,,,,,,,221126,,"), self.src)
        self.p.parse_sentence(nmea("GPRMC,120000,A,,,,,,,221126,,"), self.src)
        self.assertEqual(self.pos, [])

    def test_lowercase_checksum_accepted(self):
        s = nmea("GPGGA,120000.00,3700.000,N,07618.000,W,1,08,0.9,10.0,M,,M,,")
        self.p.parse_sentence(s[:-2] + s[-2:].lower(), self.src)
        self.assertEqual(len(self.pos), 1)


# ---------------------------------------------------------------------------
# 2 & 7 & 13. AIS expiry, unavailable values, phantom targets, reassembly
# ---------------------------------------------------------------------------

class AisTests(unittest.TestCase):
    def setUp(self):
        self.p = make_parser()
        self.p.running = True
        self.src = self.p.ais_sources[0]
        self.published = []
        self.p.ais_updated.connect(self.published.append)

    def feed(self, payload_pad, **kw):
        payload, pad = payload_pad
        self.p.parse_sentence(aivdm(payload, pad, **kw), self.src)

    def test_unavailable_sog_cog_are_none(self):
        self.feed(type1(366000001, 37.01, -76.29, 1023, 3600))
        self.p._publish_ais()
        t = self.published[-1][0]
        self.assertIsNone(t['course'])
        self.assertIsNone(t['speed'])

    def test_static_data_alone_creates_no_target(self):
        self.feed(type5(366000002, "PHANTOM"))
        self.p._publish_ais()
        self.assertEqual(self.p.ais_targets, {})
        # ...but the name is applied once a position arrives
        self.feed(type1(366000002, 37.0, -76.3, 50, 900))
        self.p._publish_ais()
        self.assertEqual(self.published[-1][0]['name'], 'PHANTOM')

    def test_lost_target_is_pruned(self):
        self.feed(type1(366000003, 37.0, -76.3, 50, 900))
        self.p._publish_ais()
        self.assertEqual(len(self.published[-1]), 1)
        self.p.ais_targets['366000003']['rx_time'] -= self.p.AIS_TARGET_TIMEOUT_S + 1
        self.p._publish_ais()
        self.assertEqual(self.published[-1], [])

    def test_publish_is_rate_limited_not_per_message(self):
        for i in range(20):
            self.feed(type1(366000100 + i, 37.0, -76.3, 50, 900))
        self.assertEqual(self.published, [])      # nothing until the publisher runs
        self.p._publish_ais()
        self.assertEqual(len(self.published), 1)
        self.assertEqual(len(self.published[0]), 20)

    def test_missing_middle_fragment_discarded(self):
        payload, pad = type5(366000004, "SPLIT")
        a, b, c = payload[:25], payload[25:50], payload[50:]
        self.p.parse_sentence(aivdm(a, 0, 3, 1, '7'), self.src)
        self.p.parse_sentence(aivdm(c, pad, 3, 3, '7'), self.src)   # fragment 2 lost
        self.assertNotIn('366000004', self.p._ais_static)
        self.p.parse_sentence(aivdm(a, 0, 3, 1, '8'), self.src)
        self.p.parse_sentence(aivdm(b, 0, 3, 2, '8'), self.src)
        self.p.parse_sentence(aivdm(c, pad, 3, 3, '8'), self.src)
        self.assertEqual(self.p._ais_static['366000004']['name'], 'SPLIT')


class TrackManagerAisTests(unittest.TestCase):
    def setUp(self):
        self.tm = TrackManager()
        self.tm.update_own_ship(37.0, -76.3, 0.0, 10.0)

    def test_stale_rx_time_expires_track(self):
        old = time.monotonic() - self.tm.track_timeout - 5
        self.tm.update_ais_tracks([{'mmsi': '1', 'lat': 37.01, 'lon': -76.3,
                                    'course': 180.0, 'speed': 5.0, 'rx_time': old}])
        self.assertEqual(self.tm.get_ais_tracks(), [])

    def test_track_removed_when_parser_drops_it(self):
        t = {'mmsi': '1', 'lat': 37.01, 'lon': -76.3, 'course': 180.0, 'speed': 5.0,
             'rx_time': time.monotonic()}
        self.tm.update_ais_tracks([t])
        self.assertEqual(len(self.tm.get_ais_tracks()), 1)
        self.tm.update_ais_tracks([])
        self.assertEqual(self.tm.get_ais_tracks(), [])

    def test_unknown_motion_gives_no_cpa(self):
        self.tm.update_ais_tracks([{'mmsi': '2', 'lat': 37.01, 'lon': -76.3,
                                    'course': None, 'speed': None,
                                    'rx_time': time.monotonic()}])
        trk = self.tm.get_ais_tracks()[0]
        self.assertIsNone(trk['cpa'])
        self.assertIsNone(trk['tcpa'])
        self.assertFalse(trk['course_valid'])

    def _encrypted(self):
        return {'mmsi': '3', 'lat': 37.01, 'lon': -76.3, 'course': 0.0, 'speed': 1.0,
                'encrypted': True, 'rx_time': time.monotonic()}

    def test_encrypted_auto_friendly(self):
        self.tm.update_ais_tracks([self._encrypted()])
        self.assertEqual(self.tm.get_ais_tracks()[0]['classification'], 'friendly')

    def test_operator_classification_overrides_auto_friendly(self):
        self.tm.set_target_classification('3', 'hostile')
        self.tm.update_ais_tracks([self._encrypted()])
        self.assertEqual(self.tm.get_ais_tracks()[0]['classification'], 'hostile')

    def test_unencrypted_not_classified(self):
        t = dict(self._encrypted(), encrypted=False)
        self.tm.update_ais_tracks([t])
        self.assertIsNone(self.tm.get_ais_tracks()[0]['classification'])


# ---------------------------------------------------------------------------
# 3 & 14. CPA
# ---------------------------------------------------------------------------

class CpaTests(unittest.TestCase):
    def setUp(self):
        self.c = CPACalculator()

    def test_receding_target_has_negative_tcpa(self):
        r = self.c.calculate({'lat': 37.0, 'lon': -76.3, 'course': 0, 'speed': 10},
                             {'lat': 36.98, 'lon': -76.3, 'course': 180, 'speed': 10})
        self.assertLess(r.tcpa_minutes, 0)
        self.assertFalse(r.is_threat)

    def test_approaching_target_has_positive_tcpa(self):
        r = self.c.calculate({'lat': 37.0, 'lon': -76.3, 'course': 0, 'speed': 10},
                             {'lat': 37.1, 'lon': -76.3, 'course': 180, 'speed': 15})
        self.assertAlmostEqual(r.tcpa_minutes, 14.4, delta=0.1)
        self.assertAlmostEqual(r.cpa_distance, 0.0, delta=0.01)

    def test_bow_crossing_range(self):
        own = {'lat': 37.0, 'lon': -76.3, 'course': 0, 'speed': 10}
        # Own ship north at 10 kn.  Target 3 NM north, 2 NM east, heading west
        # at 10 kn: reaches own track line after 0.2 h, by which time own ship
        # has moved 2 NM -> target crosses 3 - 2 = 1 NM ahead.
        tgt = {'lat': 37.05, 'lon': -76.3 + 2 / (60 * math.cos(math.radians(37))),
               'course': 270, 'speed': 10}
        bcr = self.c.calculate_bow_crossing_range(own, tgt)
        self.assertAlmostEqual(bcr, 1.0, delta=0.02)    # crosses 1 NM ahead
        tgt_astern = dict(tgt, lat=37.0167)               # ~1 NM north
        self.assertLess(self.c.calculate_bow_crossing_range(own, tgt_astern), 0)
        parallel = dict(tgt, course=0)
        self.assertIsNone(self.c.calculate_bow_crossing_range(own, parallel))

    def test_all_reference_scenarios_pass(self):
        ok, summary = ScenarioRunner(CPACalculator()).run_all_scenarios()
        self.assertTrue(ok, [(s['name'], s['errors']) for s in summary if not s['passed']])


# ---------------------------------------------------------------------------
# 4 & 10. Alarm rules / alarm manager
# ---------------------------------------------------------------------------

def sensors(**kw):
    base = dict(gps_active=True, heading_active=True, depth_active=False,
                depth_seen=False, radar_selected=True, radar_connected=True,
                radar_transmitting=False, seconds_without_video=None)
    base.update(kw)
    return SensorState(**base)


class AlarmRuleTests(unittest.TestCase):
    def test_critical_clears_when_only_warning_remains(self):
        r = evaluate_alarms([{'id': 'A', 'risk_level': 'critical'},
                             {'id': 'B', 'risk_level': 'warning'}], {}, sensors())
        self.assertTrue(r['cpa_critical'])
        self.assertTrue(r['cpa_warning'])
        r = evaluate_alarms([{'id': 'B', 'risk_level': 'warning'}], {}, sensors())
        self.assertIsNone(r['cpa_critical'])
        self.assertTrue(r['cpa_warning'])

    def test_depth_only_alarms_after_it_has_worked(self):
        self.assertIsNone(evaluate_alarms([], {}, sensors())['sensor_loss'])
        r = evaluate_alarms([], {}, sensors(depth_seen=True))
        self.assertIn('Depth', r['sensor_loss'])

    def test_radar_link_and_video_loss(self):
        self.assertTrue(evaluate_alarms([], {}, sensors(radar_connected=False))['radar_link'])
        r = evaluate_alarms([], {}, sensors(radar_transmitting=True, seconds_without_video=8))
        self.assertTrue(r['radar_video'])
        r = evaluate_alarms([], {}, sensors(radar_transmitting=True, seconds_without_video=1))
        self.assertIsNone(r['radar_video'])

    def test_alarm_manager_never_drops_active_entries(self):
        am = AlarmManager()
        am.trigger('sensor_loss', 'GPS')
        for _ in range(30):                       # churn many short alarms
            am.trigger('guard_zone')
            am.clear('guard_zone')
        am.silence_type('sensor_loss')
        before = len(am.get_recent_entries(100))
        am.trigger('sensor_loss', 'GPS')          # same condition persists
        self.assertEqual(len(am.get_recent_entries(100)), before)
        self.assertIn('sensor_loss', am.active_alarms)
        am.clear('sensor_loss')


# ---------------------------------------------------------------------------
# 5 & 6. Guard zones
# ---------------------------------------------------------------------------

class GuardZoneTests(unittest.TestCase):
    def test_relative_zone_follows_heading(self):
        z = GuardZone("Bow", 330, 30, 0, 3, relative=True)
        self.assertTrue(z.contains_point(90, 1.0, own_heading=90))    # dead ahead
        self.assertFalse(z.contains_point(0, 1.0, own_heading=90))    # on port beam
        tz = GuardZone("North", 330, 30, 0, 3, relative=False)
        self.assertTrue(tz.contains_point(0, 1.0, own_heading=90))

    def test_events_reported_once(self):
        gzm = GuardZoneManager()
        gzm.add_zone(GuardZone("Z", 0, 360, 0, 3))
        gzm.check_target('T', 10, 1.0)
        self.assertEqual(len(gzm.pop_new_alarms()), 1)
        gzm.check_target('T', 10, 1.0)
        self.assertEqual(gzm.pop_new_alarms(), [])

    def test_expired_track_clears_intrusion(self):
        tm = TrackManager()
        tm.update_own_ship(37.0, -76.3, 0.0, 0.0)
        tm.update_radar_tracks([{'id': 'R-1', 'lat': 37.01, 'lon': -76.3,
                                 'course': 0.0, 'speed': 0.0, 'filtered': True}])
        self.assertTrue(any(tm.guard_zone_manager.intrusions.values()))
        tm.radar_tracks['R-1']['last_update'] -= tm.radar_track_timeout + 1
        tm.update_radar_tracks([])
        self.assertFalse(any(tm.guard_zone_manager.intrusions.values()))


# ---------------------------------------------------------------------------
# 8. Kalman dt  /  11. HDG deviation + variation
# ---------------------------------------------------------------------------

class KalmanDtTests(unittest.TestCase):
    def test_speed_correct_at_10hz(self):
        f = KalmanTrackFilter()
        f.initialize(0.0, 0.0)
        v = 5.0                                  # m/s north = 9.72 kn
        for k in range(1, 300):
            f.predict(0.1)
            f.update([0.0, v * 0.1 * k])
        speed, course = f.get_speed_and_course()
        self.assertAlmostEqual(speed, v / 0.514444, delta=0.3)
        self.assertAlmostEqual(course, 0.0, delta=2.0)


class HeadingTests(unittest.TestCase):
    def setUp(self):
        self.p = make_parser()
        self.src = self.p.heading_sources[0]

    def test_hdg_applies_deviation_and_variation(self):
        self.p.parse_sentence(nmea("HCHDG,100.0,2.0,E,10.0,W"), self.src)
        self.assertAlmostEqual(self.p.heading, 92.0)       # 100 + 2 - 10

    def test_hdg_uses_rmc_variation(self):
        gps = self.p.gps_sources[0]
        self.p.parse_sentence(nmea("GPRMC,120000,A,3700.000,N,07618.000,W,5.0,90.0,221126,11.0,W"), gps)
        self.p.parse_sentence(nmea("HCHDG,100.0,,,,"), self.src)
        self.assertAlmostEqual(self.p.heading, 89.0)


# ---------------------------------------------------------------------------
# 15. True Motion: overlays drawn from own ship
# ---------------------------------------------------------------------------

class TrueMotionTests(unittest.TestCase):
    def test_polar_origin_is_own_ship(self):
        from gui.ppi_display import OrientationMode, PPIDisplayWidget
        ppi = PPIDisplayWidget()
        ppi.resize(900, 900)
        ppi.center_x, ppi.center_y, ppi.radius = 450, 450, 400
        ppi.set_own_ship_position(37.0, -76.3)
        ppi.set_orientation_mode(OrientationMode.TRUE_MOTION)
        ppi.set_own_ship_position(37.02, -76.3)      # own ship has moved north
        ox, oy = ppi.latlon_to_screen(37.02, -76.3)
        px, py = ppi.polar_to_screen(0.0, 0.0)
        self.assertAlmostEqual(px, ox, delta=0.5)
        self.assertAlmostEqual(py, oy, delta=0.5)
        self.assertLess(oy, ppi.center_y)            # really offset from centre


# ---------------------------------------------------------------------------
# Second review: ADS-B, camera, anchor watch
# ---------------------------------------------------------------------------

class AdsbTests(unittest.TestCase):
    def setUp(self):
        from core.adsb_receiver import AdsbReceiver
        self.rx = AdsbReceiver()
        self.got = []
        self.rx.targets_updated.connect(self.got.append)

    def test_bad_checksum_rejected(self):
        self.rx.set_own_position(37.0, -76.3)
        good = nmea("PFLAA,0,1000,500,200,1,ABC123,90,,50,,8")
        self.rx.parse_sentence(good[:-2] + ("00" if good[-2:] != "00" else "01"))
        self.assertEqual(self.got, [])
        self.rx.parse_sentence(good)
        self.assertEqual(len(self.got[-1]), 1)

    def test_not_plotted_before_own_position_known(self):
        self.rx.parse_sentence(nmea("PFLAA,0,1000,500,200,1,ABC123,90,,50,,8"))
        self.assertEqual(self.got, [])


class CameraTests(unittest.TestCase):
    def setUp(self):
        from core.camera_controller import CameraController, nmea_checksum
        self.cam = CameraController()
        self.cam.config['response_header'] = 'PCAMR'
        self.cam.config['response_bearing_field'] = 1
        self.cs = nmea_checksum

    def test_valid_and_normalised(self):
        body = "PCAMR,370.5"
        self.assertAlmostEqual(self.cam.parse_response(f"${body}*{self.cs(body)}"), 10.5)

    def test_bad_checksum_and_nan_rejected(self):
        self.assertIsNone(self.cam.parse_response("$PCAMR,045.0*00"))
        body = "PCAMR,nan"
        self.assertIsNone(self.cam.parse_response(f"${body}*{self.cs(body)}"))


class AnchorWatchTests(unittest.TestCase):
    def test_no_gps_does_not_clear_drag_alarm(self):
        from gui.anchor_watch_dialog import AnchorWatchDialog
        p = make_parser()
        tm = TrackManager()
        am = AlarmManager()
        dlg = AnchorWatchDialog(p, tm, am)
        dlg.active = True
        dlg.anchor_lat, dlg.anchor_lon = 37.0, -76.3
        dlg.swing_radius_nm = 0.1
        p.latitude, p.longitude = 37.01, -76.3          # 0.6 NM away -> drag
        p.active_gps_source = p.gps_sources[0]
        p.gps_sources[0].mark_data()
        dlg._check_position()
        self.assertIn('anchor_drag', am.active_alarms)
        p.gps_sources[0].last_data_time = time.monotonic() - 60   # GPS goes stale
        p.latitude, p.longitude = 37.0, -76.3            # frozen/stale "back at anchor"
        dlg._check_position()
        self.assertIn('anchor_drag', am.active_alarms)   # not cleared on stale data
        dlg.active = False
        am.clear('anchor_drag')


if __name__ == '__main__':
    unittest.main()
