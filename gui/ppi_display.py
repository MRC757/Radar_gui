"""
PPI (Plan Position Indicator) Display Widget
IMO ARPA compliant radar display with rotating sweep,
orientation modes, target selection, trails, and guard zones.
"""

import math
import time
from enum import Enum, auto

import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

from gui.color_themes import DisplayMode, get_theme
from gui.radar_video import RadarVideoBuffer
from gui.formatting import fmt, fmt_tcpa


class OrientationMode(Enum):
    NORTH_UP = auto()
    HEAD_UP = auto()
    COURSE_UP = auto()
    TRUE_MOTION = auto()


class PPIDisplayWidget(QWidget):
    """PPI radar display with rotating sweep - IMO ARPA compliant"""

    # Signals for target interaction
    target_selected = pyqtSignal(dict)
    target_deselected = pyqtSignal()
    cursor_moved = pyqtSignal(float, float)
    range_rings_changed = pyqtSignal()
    context_menu_requested = pyqtSignal(dict, QPointF)  # (target_data, screen_pos)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 800)
        self.setMouseTracking(True)

        # Theme
        self.display_mode = DisplayMode.DAY
        self.theme = get_theme(self.display_mode)

        # Display settings
        self.range_nm = 12.0
        self.center_x = 0
        self.center_y = 0
        self.radius = 0

        # Own ship data
        self.own_lat = 0.0
        self.own_lon = 0.0
        self.own_heading = 0.0
        self.own_course = 0.0

        # Display options
        self.show_adsb = True
        self.show_ais = True
        self.show_stationary_ais = True   # When False, AIS targets with speed < 0.5 kts are hidden
        self.show_base_stations = True    # Toggle for AIS base station squares (Type 4)
        self.base_station_tracks = []     # Populated by main_window via base_stations_updated signal
        self._anchor_watch = None         # AnchorWatchDialog reference for swing-radius overlay
        self.show_tracks = True
        self.show_trails = True
        self.show_guard_zones = True
        self.show_range_rings = True
        self.range_ring_distances = [3.0, 6.0, 9.0, 12.0]
        self.show_azimuth_lines = True
        self.video_mode = 'processed'

        # Orientation
        self.orientation_mode = OrientationMode.NORTH_UP
        self.true_motion_ref_lat = None
        self.true_motion_ref_lon = None
        self.true_motion_reset_fraction = 0.75

        # Radar video (spoke buffer) — sweep angle follows the latest spoke
        self.video = RadarVideoBuffer()
        self.video.set_colors(self.theme.radar_echo_weak, self.theme.radar_echo_strong)
        self.radar_sweep_angle = 0.0
        self._last_spoke_time = None

        # Track data
        self.radar_tracks = []
        self.ais_tracks = []
        self.adsb_tracks = []

        # Guard zone data
        self.guard_zones = []
        self.guard_zone_intrusions = {}

        # Target selection
        self.selected_target_id = None
        self.selected_target_type = None
        self.hit_test_radius = 15

        # EBL / VRM state
        self.ebl1_bearing = 0.0
        self.ebl1_visible = False
        self.ebl2_bearing = 90.0
        self.ebl2_visible = False
        self.vrm1_range = 3.0   # NM
        self.vrm1_visible = False
        self.vrm2_range = 6.0   # NM
        self.vrm2_visible = False

        # EBL/VRM drag state
        self._ebl_drag = None       # 'ebl1' | 'ebl2' | None
        self._vrm_drag = None       # 'vrm1' | 'vrm2' | None
        self._ebl_hit_tolerance = 5   # degrees
        self._vrm_hit_tolerance = 8   # pixels

        # Range ring drag interaction
        self._drag_ring_index = -1
        self._drag_active = False
        self._hover_ring_index = -1
        self._ring_hit_tolerance = 8  # pixels

        # Cursor overlay
        self._cursor_sx = -1.0
        self._cursor_sy = -1.0

        # Camera bearing line
        self.camera_azimuth = None      # degrees true (None = not shown)

        # Danger flash
        self.flash_state = True
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self._toggle_flash)
        self.flash_timer.start(500)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_camera_azimuth(self, azimuth):
        """Set camera bearing line.  Pass None to hide."""
        self.camera_azimuth = azimuth
        self.update()

    def set_display_mode(self, mode: DisplayMode):
        self.display_mode = mode
        self.theme = get_theme(mode)
        self.video.set_colors(self.theme.radar_echo_weak, self.theme.radar_echo_strong)
        self.update()

    def set_orientation_mode(self, mode: OrientationMode):
        self.orientation_mode = mode
        if mode == OrientationMode.TRUE_MOTION:
            self.true_motion_ref_lat = self.own_lat
            self.true_motion_ref_lon = self.own_lon
        self.update()

    def set_range(self, range_nm):
        self.range_nm = range_nm
        self.video.set_range(range_nm)
        self.update()

    def set_video_mode(self, mode):
        self.video_mode = mode
        self.update()

    def set_show_ais(self, show):
        self.show_ais = show
        self.update()

    def set_adsb_tracks(self, tracks):
        self.adsb_tracks = tracks
        self.update()

    def set_show_adsb(self, show):
        self.show_adsb = show
        self.update()

    def set_show_stationary_ais(self, show):
        self.show_stationary_ais = show
        self.update()

    def set_show_base_stations(self, show):
        self.show_base_stations = show
        self.update()

    def set_anchor_watch(self, dialog_or_none):
        """Set the AnchorWatchDialog reference used for the PPI swing-radius overlay."""
        self._anchor_watch = dialog_or_none
        self.update()

    def set_show_tracks(self, show):
        self.show_tracks = show
        self.update()

    def set_show_range_rings(self, show):
        self.show_range_rings = show
        self.update()

    def set_range_ring_count(self, count):
        """Rebuild range_ring_distances as equally-spaced rings."""
        if count <= 0:
            self.range_ring_distances = []
        else:
            interval = self.range_nm / count
            self.range_ring_distances = [interval * (i + 1) for i in range(count)]
        self.update()

    def set_range_ring_distances(self, distances):
        self.range_ring_distances = sorted(distances)
        self.update()

    def get_range_ring_distances(self):
        return list(self.range_ring_distances)

    def _screen_dist_from_center(self, sx, sy):
        """Pixel distance from PPI center (range rings are centred here)."""
        dx = sx - self.center_x
        dy = sy - self.center_y
        return math.sqrt(dx * dx + dy * dy)

    def _screen_dist_from_own_ship(self, sx, sy):
        """Pixel distance from own ship (VRMs are centred on own ship)."""
        ox, oy = self._own_ship_screen_pos()
        return math.hypot(sx - ox, sy - oy)

    def _hit_test_ebl(self, sx, sy):
        """Return 'ebl1', 'ebl2', or None if cursor is near a visible EBL."""
        bearing, _ = self.screen_to_bearing_range(sx, sy)
        dist_from_center = self._screen_dist_from_own_ship(sx, sy)
        if dist_from_center < 20:
            return None  # too close to center, ambiguous
        for name, brg, vis in [('ebl1', self.ebl1_bearing, self.ebl1_visible),
                                ('ebl2', self.ebl2_bearing, self.ebl2_visible)]:
            if not vis:
                continue
            diff = abs(bearing - brg)
            if diff > 180:
                diff = 360 - diff
            if diff <= self._ebl_hit_tolerance:
                return name
        return None

    def _hit_test_vrm(self, sx, sy):
        """Return 'vrm1', 'vrm2', or None if cursor is near a visible VRM."""
        cursor_dist = self._screen_dist_from_own_ship(sx, sy)
        for name, rng, vis in [('vrm1', self.vrm1_range, self.vrm1_visible),
                                ('vrm2', self.vrm2_range, self.vrm2_visible)]:
            if not vis:
                continue
            vrm_px = self.radius * (rng / self.range_nm) if self.range_nm > 0 else 0
            if abs(cursor_dist - vrm_px) <= self._vrm_hit_tolerance:
                return name
        return None

    def _hit_test_ring(self, sx, sy):
        """Return index of nearest ring within tolerance, or -1."""
        if not self.show_range_rings or not self.range_ring_distances:
            return -1
        cursor_dist = self._screen_dist_from_center(sx, sy)
        best_idx = -1
        best_gap = self._ring_hit_tolerance + 1
        for i, dist_nm in enumerate(self.range_ring_distances):
            ring_px = self.radius * (dist_nm / self.range_nm) if self.range_nm > 0 else 0
            gap = abs(cursor_dist - ring_px)
            if gap <= self._ring_hit_tolerance and gap < best_gap:
                best_gap = gap
                best_idx = i
        return best_idx

    # EBL / VRM API
    def set_ebl1(self, bearing, visible=True):
        self.ebl1_bearing = bearing % 360
        self.ebl1_visible = visible
        self.update()

    def set_ebl2(self, bearing, visible=True):
        self.ebl2_bearing = bearing % 360
        self.ebl2_visible = visible
        self.update()

    def set_vrm1(self, range_nm, visible=True):
        self.vrm1_range = max(0.01, range_nm)
        self.vrm1_visible = visible
        self.update()

    def set_vrm2(self, range_nm, visible=True):
        self.vrm2_range = max(0.01, range_nm)
        self.vrm2_visible = visible
        self.update()

    def set_show_azimuth_lines(self, show):
        self.show_azimuth_lines = show
        self.update()

    def set_own_ship_position(self, lat, lon):
        self.own_lat = lat
        self.own_lon = lon
        # True Motion auto-reset
        if self.orientation_mode == OrientationMode.TRUE_MOTION and self.true_motion_ref_lat is not None:
            dlat = (lat - self.true_motion_ref_lat) * 60.0
            dlon = (lon - self.true_motion_ref_lon) * 60.0 * math.cos(math.radians(lat))
            dist_nm = math.sqrt(dlat ** 2 + dlon ** 2)
            if dist_nm > self.range_nm * self.true_motion_reset_fraction:
                self.true_motion_ref_lat = lat
                self.true_motion_ref_lon = lon

    def set_own_ship_heading(self, heading):
        self.own_heading = heading
        self.update()

    def configure_video(self, spokes_per_revolution, samples_per_spoke):
        """Match the video buffer to the connected radar's resolution."""
        self.video.configure(spokes_per_revolution, min(samples_per_spoke, 1024))
        self.video.set_range(self.range_nm)

    def add_spokes(self, spokes):
        """Receive a batch of core.radar.Spoke objects from the radar driver."""
        self.video.add_spokes(spokes, self.own_heading)
        if self.video.last_true_azimuth is not None:
            self.radar_sweep_angle = self.video.last_true_azimuth
        self._last_spoke_time = time.monotonic()
        self.update()

    def clear_video(self):
        """Blank the radar picture (standby / disconnect / radar change)."""
        self.video.clear()
        self._last_spoke_time = None
        self.update()

    def _video_active(self):
        return (self._last_spoke_time is not None
                and time.monotonic() - self._last_spoke_time < 2.0)

    def update_tracks(self, radar_tracks, ais_tracks):
        self.radar_tracks = radar_tracks
        self.ais_tracks = ais_tracks
        self.update()

    def update_guard_zones(self, zones, intrusions):
        self.guard_zones = zones
        self.guard_zone_intrusions = intrusions

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _toggle_flash(self):
        self.flash_state = not self.flash_state

    # ------------------------------------------------------------------
    # Orientation helpers
    # ------------------------------------------------------------------

    def _get_rotation_angle(self) -> float:
        if self.orientation_mode == OrientationMode.HEAD_UP:
            return -self.own_heading
        elif self.orientation_mode == OrientationMode.COURSE_UP:
            return -self.own_course
        return 0.0

    def _get_display_center(self):
        """Get the reference lat/lon for the display center."""
        if self.orientation_mode == OrientationMode.TRUE_MOTION:
            return (
                self.true_motion_ref_lat if self.true_motion_ref_lat is not None else self.own_lat,
                self.true_motion_ref_lon if self.true_motion_ref_lon is not None else self.own_lon,
            )
        return self.own_lat, self.own_lon

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def latlon_to_screen(self, lat, lon):
        ref_lat, ref_lon = self._get_display_center()
        delta_lat = (lat - ref_lat) * 60.0
        delta_lon = (lon - ref_lon) * 60.0 * math.cos(math.radians(ref_lat)) if ref_lat != 0 else (lon - ref_lon) * 60.0

        bearing = math.degrees(math.atan2(delta_lon, delta_lat))
        range_nm = math.sqrt(delta_lat ** 2 + delta_lon ** 2)

        bearing += self._get_rotation_angle()

        range_fraction = range_nm / self.range_nm if self.range_nm > 0 else 0
        screen_range = range_fraction * self.radius

        rad = math.radians(bearing)
        x = self.center_x + screen_range * math.sin(rad)
        y = self.center_y - screen_range * math.cos(rad)
        return x, y

    def polar_to_screen(self, azimuth, range_m):
        range_nm = range_m / 1852.0
        range_fraction = range_nm / self.range_nm if self.range_nm > 0 else 0
        screen_range = range_fraction * self.radius

        # Origin is OWN SHIP (differs from the screen centre in True Motion)
        ox, oy = self._own_ship_screen_pos()
        adjusted_azimuth = azimuth + self._get_rotation_angle()
        rad = math.radians(adjusted_azimuth)
        x = ox + screen_range * math.sin(rad)
        y = oy - screen_range * math.cos(rad)
        return x, y

    def screen_to_bearing_range(self, sx, sy):
        ox, oy = self._own_ship_screen_pos()     # bearing/range FROM OWN SHIP
        dx = sx - ox
        dy = -(sy - oy)
        bearing = (math.degrees(math.atan2(dx, dy)) - self._get_rotation_angle()) % 360
        pixel_range = math.sqrt(dx ** 2 + dy ** 2)
        range_nm = (pixel_range / self.radius) * self.range_nm if self.radius > 0 else 0
        return bearing, range_nm

    def screen_to_latlon(self, sx, sy):
        """Convert screen coordinates to latitude/longitude."""
        bearing, range_nm = self.screen_to_bearing_range(sx, sy)
        ref_lat, ref_lon = self.own_lat, self.own_lon   # bearing/range are from own ship
        rad = math.radians(bearing)
        delta_lat = range_nm * math.cos(rad)  # NM north
        cos_lat = math.cos(math.radians(ref_lat)) if ref_lat != 0 else 1.0
        delta_lon = range_nm * math.sin(rad) / cos_lat if cos_lat > 0 else 0
        lat = ref_lat + delta_lat / 60.0
        lon = ref_lon + delta_lon / 60.0
        return lat, lon

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        click_x = event.position().x()
        click_y = event.position().y()

        # Priority 1: target selection
        best_target = None
        best_dist_sq = self.hit_test_radius ** 2

        for track in self.radar_tracks:
            tx, ty = self.latlon_to_screen(track['lat'], track['lon'])
            d = (click_x - tx) ** 2 + (click_y - ty) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best_target = dict(track, _selection_type='radar')

        for ais in self.ais_tracks:
            ax, ay = self.latlon_to_screen(ais['lat'], ais['lon'])
            d = (click_x - ax) ** 2 + (click_y - ay) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best_target = dict(ais, _selection_type='ais')

        if best_target:
            self.selected_target_id = best_target.get('id')
            self.selected_target_type = best_target.get('_selection_type')
            self.target_selected.emit(best_target)
            self.update()
            return

        # Priority 1.5: EBL drag
        ebl_hit = self._hit_test_ebl(click_x, click_y)
        if ebl_hit:
            self._ebl_drag = ebl_hit
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        # Priority 1.6: VRM drag
        vrm_hit = self._hit_test_vrm(click_x, click_y)
        if vrm_hit:
            self._vrm_drag = vrm_hit
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return

        # Priority 2: range ring drag
        ring_idx = self._hit_test_ring(click_x, click_y)
        if ring_idx >= 0:
            self._drag_ring_index = ring_idx
            self._drag_active = True
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.update()
            return

        # Nothing hit — deselect
        self.selected_target_id = None
        self.selected_target_type = None
        self.target_deselected.emit()
        self.update()

    def mouseMoveEvent(self, event):
        sx = event.position().x()
        sy = event.position().y()

        # Track cursor position for overlay drawing
        self._cursor_sx = sx
        self._cursor_sy = sy

        # Always emit cursor position
        bearing, range_nm = self.screen_to_bearing_range(sx, sy)
        self.cursor_moved.emit(bearing, range_nm)

        if self._ebl_drag:
            new_bearing, _ = self.screen_to_bearing_range(sx, sy)
            if self._ebl_drag == 'ebl1':
                self.ebl1_bearing = new_bearing % 360
            else:
                self.ebl2_bearing = new_bearing % 360
            self.update()
            return

        if self._vrm_drag:
            cursor_dist_px = self._screen_dist_from_own_ship(sx, sy)
            new_nm = (cursor_dist_px / self.radius) * self.range_nm if self.radius > 0 else 0
            new_nm = max(0.01, min(new_nm, self.range_nm))
            if self._vrm_drag == 'vrm1':
                self.vrm1_range = round(new_nm, 2)
            else:
                self.vrm2_range = round(new_nm, 2)
            self.update()
            return

        if self._drag_active:
            # Update dragged ring distance from cursor
            cursor_dist_px = self._screen_dist_from_center(sx, sy)
            new_nm = (cursor_dist_px / self.radius) * self.range_nm if self.radius > 0 else 0
            new_nm = max(0.1, min(new_nm, self.range_nm))
            self.range_ring_distances[self._drag_ring_index] = round(new_nm, 2)
            self.update()
        else:
            # Hover detection for ring highlight
            old_hover = self._hover_ring_index
            self._hover_ring_index = self._hit_test_ring(sx, sy)
            if self._hover_ring_index >= 0:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._hover_ring_index != old_hover:
                self.update()

    def mouseReleaseEvent(self, event):
        if self._ebl_drag:
            self._ebl_drag = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._vrm_drag:
            self._vrm_drag = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._drag_active:
            self._drag_active = False
            self._drag_ring_index = -1
            # Sort so rings stay in distance order
            self.range_ring_distances.sort()
            self.range_rings_changed.emit()
            self.update()
            # Reset cursor based on current position
            sx = event.position().x()
            sy = event.position().y()
            if self._hit_test_ring(sx, sy) >= 0:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event):
        self._cursor_sx = -1.0
        self._cursor_sy = -1.0
        self.update()

    def contextMenuEvent(self, event):
        """Right-click context menu on targets."""
        sx = event.pos().x()
        sy = event.pos().y()

        best_target = None
        best_dist_sq = self.hit_test_radius ** 2

        for track in self.radar_tracks:
            tx, ty = self.latlon_to_screen(track['lat'], track['lon'])
            d = (sx - tx) ** 2 + (sy - ty) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best_target = dict(track, _selection_type='radar')

        for ais in self.ais_tracks:
            ax, ay = self.latlon_to_screen(ais['lat'], ais['lon'])
            d = (sx - ax) ** 2 + (sy - ay) ** 2
            if d < best_dist_sq:
                best_dist_sq = d
                best_target = dict(ais, _selection_type='ais')

        if best_target:
            self.selected_target_id = best_target.get('id')
            self.selected_target_type = best_target.get('_selection_type')
            self.target_selected.emit(best_target)
            self.context_menu_requested.emit(best_target, QPointF(sx, sy))
            self.update()

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.center_x = self.width() // 2
        self.center_y = self.height() // 2
        self.radius = min(self.width(), self.height()) // 2 - 40

    # ------------------------------------------------------------------
    # Paint pipeline
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), self.theme.ppi_background)

        self.draw_grid(painter)

        self.draw_radar_video(painter)

        if self._video_active():
            self.draw_sweep(painter)

        if self.show_guard_zones:
            self.draw_guard_zones(painter)

        if self.show_trails:
            self.draw_trails(painter)

        if self.show_tracks:
            self.draw_tracks(painter)

        if self.show_ais:
            self.draw_ais_targets(painter)

        if self.show_adsb:
            self.draw_adsb_targets(painter)

        if self.show_base_stations:
            self.draw_base_stations(painter)

        self.draw_anchor_watch(painter)

        self.draw_ebl_vrm(painter)
        self.draw_camera_bearing_line(painter)
        self.draw_own_ship(painter)
        self.draw_heading_indicator(painter)
        self.draw_range_scale(painter)
        self.draw_orientation_indicator(painter)
        self.draw_ring_interval_indicator(painter)
        self.draw_cursor_info(painter)
        self.draw_cpa_summary(painter)

    # ------------------------------------------------------------------
    # Drawing methods
    # ------------------------------------------------------------------

    def draw_grid(self, painter):
        rotation = self._get_rotation_angle()

        # Range rings (don't rotate)
        if self.show_range_rings and self.range_ring_distances:
            for i, dist_nm in enumerate(self.range_ring_distances):
                fraction = dist_nm / self.range_nm if self.range_nm > 0 else 0
                r = self.radius * fraction
                if i == self._drag_ring_index:
                    painter.setPen(QPen(self.theme.selection_highlight, 2))
                elif i == self._hover_ring_index:
                    painter.setPen(QPen(self.theme.range_ring_labels, 1))
                else:
                    painter.setPen(QPen(self.theme.grid_lines, 1))
                painter.drawEllipse(QPointF(self.center_x, self.center_y), r, r)

        # Azimuth lines
        if self.show_azimuth_lines:
            for angle in range(0, 360, 10):
                display_angle = angle + rotation
                if angle % 30 == 0:
                    painter.setPen(QPen(self.theme.grid_lines_major, 2))
                else:
                    painter.setPen(QPen(self.theme.grid_lines, 1))
                rad = math.radians(display_angle)
                x = self.center_x + self.radius * math.sin(rad)
                y = self.center_y - self.radius * math.cos(rad)
                painter.drawLine(self.center_x, self.center_y, int(x), int(y))

        # Compass degree labels (show true bearing)
        painter.setPen(QPen(self.theme.compass_text, 1))
        painter.setFont(QFont('Consolas', 9))
        for angle in range(0, 360, 30):
            display_angle = angle + rotation
            rad = math.radians(display_angle)
            tx = self.center_x + (self.radius + 15) * math.sin(rad)
            ty = self.center_y - (self.radius + 15) * math.cos(rad)
            painter.drawText(int(tx - 12), int(ty + 5), f"{angle:03d}")

    def _own_ship_screen_pos(self):
        if self.orientation_mode == OrientationMode.TRUE_MOTION:
            return self.latlon_to_screen(self.own_lat, self.own_lon)
        return float(self.center_x), float(self.center_y)

    def draw_radar_video(self, painter):
        if self.radius <= 0:
            return
        image = self.video.render(2 * self.radius)
        if image is None:
            return
        ox, oy = self._own_ship_screen_pos()
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(self.center_x, self.center_y), self.radius, self.radius)
        painter.setClipPath(clip)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(ox, oy)
        painter.rotate(self._get_rotation_angle())
        r = self.radius
        painter.drawImage(QRectF(-r, -r, 2 * r, 2 * r), image)
        painter.restore()

    def draw_sweep(self, painter):
        painter.setPen(QPen(self.theme.sweep_line, 2))
        rotation = self._get_rotation_angle()
        rad = math.radians(self.radar_sweep_angle + rotation)
        ox, oy = self._own_ship_screen_pos()
        x = ox + self.radius * math.sin(rad)
        y = oy - self.radius * math.cos(rad)
        painter.drawLine(QPointF(ox, oy), QPointF(x, y))

    def draw_guard_zones(self, painter):
        for zone in self.guard_zones:
            if not zone.enabled:
                continue
            has_intrusion = bool(self.guard_zone_intrusions.get(zone.name))
            if has_intrusion:
                boundary_color = self.theme.guard_zone_alarm
                fill_color = QColor(self.theme.guard_zone_alarm)
                fill_color.setAlpha(40)
            else:
                boundary_color = self.theme.guard_zone_boundary
                fill_color = self.theme.guard_zone_fill

            points = zone.get_boundary_points(num_points=60, own_heading=self.own_heading)
            path = QPainterPath()
            first = True
            for bearing, range_nm in points:
                range_m = range_nm * 1852.0
                sx, sy = self.polar_to_screen(bearing, range_m)
                if first:
                    path.moveTo(sx, sy)
                    first = False
                else:
                    path.lineTo(sx, sy)
            path.closeSubpath()

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_color))
            painter.drawPath(path)

            painter.setPen(QPen(boundary_color, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

            # Zone label
            mid_angle = (zone.start_angle + zone.end_angle) / 2
            if zone.start_angle > zone.end_angle:
                mid_angle = ((zone.start_angle + zone.end_angle + 360) / 2) % 360
            lx, ly = self.polar_to_screen(mid_angle, zone.outer_range * 1852.0)
            painter.setPen(QPen(boundary_color, 1))
            painter.setFont(QFont('Consolas', 8))
            painter.drawText(int(lx) + 5, int(ly), zone.name)

    def draw_trails(self, painter):
        all_tracks = []
        if self.show_tracks:
            for t in self.radar_tracks:
                trail = t.get('trail', [])
                risk = t.get('risk_level', 'safe')
                color = self.theme.arpa_target_dangerous if risk in ('critical', 'warning') else self.theme.arpa_past_position
                all_tracks.append((trail, color))
        if self.show_ais:
            for a in self.ais_tracks:
                trail = a.get('trail', [])
                all_tracks.append((trail, self.theme.ais_target_normal))

        for trail, base_color in all_tracks:
            if not trail:
                continue
            n = len(trail)
            for i, entry in enumerate(trail):
                lat, lon = entry[0], entry[1]
                sx, sy = self.latlon_to_screen(lat, lon)
                alpha = int(255 * (i + 1) / n * 0.7)
                dot_color = QColor(base_color)
                dot_color.setAlpha(alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(dot_color))
                painter.drawEllipse(QPointF(sx, sy), 3, 3)

    def draw_tracks(self, painter):
        for track in self.radar_tracks:
            x, y = self.latlon_to_screen(track['lat'], track['lon'])

            classification = track.get('classification')
            risk = track.get('risk_level', 'safe')

            # Hostile targets always show as dangerous
            if classification == 'hostile':
                if not self.flash_state:
                    continue
                color = self.theme.arpa_target_dangerous
            elif risk == 'critical' or risk == 'warning':
                if not self.flash_state:
                    continue  # Flash dangerous targets
                color = self.theme.arpa_target_dangerous
            elif risk == 'caution':
                color = self.theme.arpa_target_caution
            else:
                color = QColor(0, 200, 0)  # Green — ARPA normal contact

            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # ARPA symbol: circle (IMO distinct from AIS triangle)
            painter.drawEllipse(QPointF(x, y), 6, 6)

            if 'course' in track and 'speed' in track:
                self.draw_vector(painter, x, y, track['course'],
                                 track['speed'] * 2, color)

            # Classification tag
            if classification:
                tag_colors = {
                    'friendly': QColor(0, 140, 255),
                    'neutral': QColor(0, 180, 255),
                    'hostile': QColor(255, 0, 0),
                }
                painter.setPen(QPen(tag_colors.get(classification, QColor(255, 255, 255)), 1))
                painter.setFont(QFont('Consolas', 7, QFont.Weight.Bold))
                painter.drawText(int(x) + 8, int(y) - 8, classification[0].upper())

            # Selection highlight
            if track.get('id') == self.selected_target_id:
                painter.setPen(QPen(self.theme.selection_ring, 2, Qt.PenStyle.DashLine))
                painter.drawEllipse(QPointF(x, y), 14, 14)

    def draw_ais_targets(self, painter):
        for ais in self.ais_tracks:
            # Stationary AIS filter — skip moored/anchored vessels when the
            # operator has turned off their display.  Threats and the selected
            # target are always shown regardless of speed.
            if not self.show_stationary_ais:
                _is_threat = (ais.get('is_threat', False) or
                              ais.get('risk_level', 'safe') in ('critical', 'warning'))
                _is_selected = ais.get('id') == self.selected_target_id
                if not _is_threat and not _is_selected and ais.get('speed', 1.0) < 0.5:
                    continue

            x, y = self.latlon_to_screen(ais['lat'], ais['lon'])

            classification = ais.get('classification')
            risk = ais.get('risk_level', 'safe')
            is_selected = ais.get('id') == self.selected_target_id

            # Hostile targets always show as dangerous
            if classification == 'hostile':
                if not self.flash_state:
                    continue
                color = self.theme.ais_target_dangerous
            elif risk in ('critical', 'warning'):
                if not self.flash_state:
                    continue
                color = self.theme.ais_target_dangerous
            elif is_selected:
                color = self.theme.ais_target_selected
            elif ais.get('encrypted'):
                color = QColor(0, 120, 255)   # Blue — encrypted/secure AIS
            else:
                color = QColor(0, 200, 0)     # Green — standard unencrypted AIS

            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # AIS symbol: triangle (IMO distinct from ARPA circle)
            size = 10
            path = QPainterPath()
            path.moveTo(x, y - size)
            path.lineTo(x - size * 0.7, y + size * 0.5)
            path.lineTo(x + size * 0.7, y + size * 0.5)
            path.closeSubpath()
            painter.drawPath(path)

            # No vector when COG is "not available" (it would point due north)
            if ais.get('speed', 0) > 0.5 and ais.get('course_valid', True):
                self.draw_vector(painter, x, y, ais.get('course', 0),
                                 ais['speed'] * 3, color)

            # Classification tag
            if classification:
                tag_colors = {
                    'friendly': QColor(0, 140, 255),
                    'neutral': QColor(0, 180, 255),
                    'hostile': QColor(255, 0, 0),
                }
                painter.setPen(QPen(tag_colors.get(classification, QColor(255, 255, 255)), 1))
                painter.setFont(QFont('Consolas', 7, QFont.Weight.Bold))
                painter.drawText(int(x) + 8, int(y) - 8, classification[0].upper())

            # Info box for selected or dangerous targets
            if is_selected or risk in ('critical', 'warning'):
                self.draw_ais_info_box(painter, ais, x, y)

            # Selection highlight
            if is_selected:
                painter.setPen(QPen(self.theme.selection_ring, 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 14, 14)

    def draw_base_stations(self, painter):
        """Draw AIS base stations (Type 4) as teal hollow squares.

        Symbol is deliberately distinct from:
          - ARPA targets  : filled circle
          - AIS vessels   : hollow triangle
          - Base stations : hollow square (this method)
        """
        color = QColor(0, 210, 190)   # Teal — distinct from yellow AIS, blue friendly
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 2))
        painter.setFont(QFont('Consolas', 7))

        for bs in self.base_station_tracks:
            x, y = self.latlon_to_screen(bs['lat'], bs['lon'])
            size = 8
            painter.drawRect(int(x - size), int(y - size), size * 2, size * 2)
            # MMSI label below the square
            painter.drawText(int(x) - 20, int(y) + size + 11, bs['mmsi'])

    def draw_anchor_watch(self, painter):
        """Draw swing-radius circle when Anchor Watch is active."""
        aw = self._anchor_watch
        if aw is None or not aw.active:
            return
        if self.range_nm <= 0 or self.radius <= 0:
            return

        ax, ay = self.latlon_to_screen(aw.anchor_lat, aw.anchor_lon)
        r_pixels = (aw.swing_radius_nm / self.range_nm) * self.radius

        gold = QColor(255, 200, 0)

        # Dashed swing-radius circle
        painter.setPen(QPen(gold, 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(ax, ay), r_pixels, r_pixels)

        # Anchor symbol: cross (+) at anchor point
        painter.setPen(QPen(gold, 3, Qt.PenStyle.SolidLine))
        ax_i = int(ax)
        ay_i = int(ay)
        painter.drawLine(ax_i, ay_i - 10, ax_i, ay_i + 10)   # vertical
        painter.drawLine(ax_i - 10, ay_i, ax_i + 10, ay_i)   # horizontal

        # Small filled circle at centre
        painter.setBrush(QBrush(gold))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(ax, ay), 3, 3)

        # "ANC" label
        painter.setPen(QPen(gold, 1))
        painter.setFont(QFont('Consolas', 8))
        painter.drawText(ax_i + 14, ay_i - 12, "ANC")

    def draw_adsb_targets(self, painter):
        """Draw ADS-B / FLARM aircraft tracks as cyan directional triangles."""
        import math as _math
        for ac in self.adsb_tracks:
            lat = ac.get('lat', 0.0)
            lon = ac.get('lon', 0.0)
            if lat == 0.0 and lon == 0.0:
                continue   # own position not yet known

            x, y = self.latlon_to_screen(lat, lon)

            # Off-screen culling
            margin = 20
            if (x < -margin or x > self.width() + margin or
                    y < -margin or y > self.height() + margin):
                continue

            alarm = ac.get('alarm_level', 0)
            if alarm >= 2:
                if not self.flash_state:
                    continue
                color = QColor(255, 0, 0)        # red — urgent alarm
            elif alarm == 1:
                color = QColor(255, 220, 0)      # yellow — caution
            else:
                color = QColor(0, 220, 220)      # cyan — normal

            track = ac.get('track', 0.0)
            size  = 9

            # Rotate the triangle to face the aircraft's track direction
            painter.save()
            painter.translate(x, y)
            painter.rotate(track)

            path = QPainterPath()
            path.moveTo(0, -size)                    # nose (forward)
            path.lineTo(-size * 0.65, size * 0.6)   # left rear
            path.lineTo( size * 0.65, size * 0.6)   # right rear
            path.closeSubpath()

            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.restore()

            # Speed vector (uses draw_vector which works in screen coords)
            speed_kts = ac.get('speed_kts', 0.0)
            if speed_kts > 5.0:
                self.draw_vector(painter, x, y, track, speed_kts * 3, color)

            # ICAO hex label above symbol
            icao = ac.get('id', '')
            painter.setPen(QPen(color, 1))
            painter.setFont(QFont('Consolas', 7))
            painter.drawText(int(x) - 14, int(y) - size - 4, icao)

            # Altitude label below symbol
            alt_m = ac.get('alt_rel_m', None)
            if alt_m is not None:
                sign = '+' if alt_m >= 0 else ''
                painter.setFont(QFont('Consolas', 7))
                painter.drawText(int(x) - 14, int(y) + size + 10, f"{sign}{alt_m}m")

    def draw_camera_bearing_line(self, painter):
        """Draw camera line-of-bearing from own ship, extending up to 12 NM.

        The line is drawn in bright cyan so it is immediately distinct from:
          - EBL / VRM lines   (amber/orange)
          - ARPA / AIS tracks (green)
          - Radar video       (green)
          - Guard zones       (red)
        An arrowhead marks the far end and a label shows the current azimuth.
        """
        if self.camera_azimuth is None:
            return
        if self.range_nm <= 0 or self.radius <= 0:
            return

        # Own ship screen origin
        if self.orientation_mode == OrientationMode.TRUE_MOTION:
            ox, oy = self.latlon_to_screen(self.own_lat, self.own_lon)
        else:
            ox, oy = float(self.center_x), float(self.center_y)

        # Line extends to 12 NM, clipped to the current display range
        line_nm = min(12.0, self.range_nm)
        line_px = self.radius * (line_nm / self.range_nm)

        rotation = self._get_rotation_angle()
        rad = math.radians(self.camera_azimuth + rotation)
        ex = ox + line_px * math.sin(rad)
        ey = oy - line_px * math.cos(rad)

        cam_color = QColor(0, 220, 220)   # bright cyan

        # Main line — solid, 2 px
        painter.setPen(QPen(cam_color, 2, Qt.PenStyle.SolidLine))
        painter.drawLine(int(ox), int(oy), int(ex), int(ey))

        # Arrowhead at the tip (two short back-angled strokes)
        arrow_len = 14
        for offset in (-30, 30):
            ar  = math.radians(self.camera_azimuth + rotation + 180 + offset)
            axp = ex + arrow_len * math.sin(ar)
            ayp = ey - arrow_len * math.cos(ar)
            painter.drawLine(int(ex), int(ey), int(axp), int(ayp))

        # Azimuth label positioned at 65 % along the line
        frac = 0.65
        lx = int(ox + line_px * frac * math.sin(rad))
        ly = int(oy - line_px * frac * math.cos(rad))
        painter.setPen(QPen(cam_color, 1))
        painter.setFont(QFont('Consolas', 9, QFont.Weight.Bold))
        painter.drawText(lx + 6, ly - 4, f"CAM {self.camera_azimuth:05.1f}\u00b0")

    def draw_ebl_vrm(self, painter):
        """Draw Electronic Bearing Lines and Variable Range Markers."""
        rotation = self._get_rotation_angle()
        ox, oy = self._own_ship_screen_pos()

        # EBLs — dashed lines from own ship to edge at the given bearing
        for brg, vis, label in [(self.ebl1_bearing, self.ebl1_visible, "EBL1"),
                                 (self.ebl2_bearing, self.ebl2_visible, "EBL2")]:
            if not vis:
                continue
            pen = QPen(self.theme.ebl_line, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            rad = math.radians(brg + rotation)
            x = ox + self.radius * math.sin(rad)
            y = oy - self.radius * math.cos(rad)
            painter.drawLine(QPointF(ox, oy), QPointF(x, y))
            # Label at 80% of radius
            lx = ox + self.radius * 0.82 * math.sin(rad)
            ly = oy - self.radius * 0.82 * math.cos(rad)
            painter.setFont(QFont('Consolas', 8, QFont.Weight.Bold))
            painter.drawText(int(lx) + 4, int(ly) - 4,
                             f"{label} {brg:05.1f}\u00b0")

        # VRMs — dashed circles at the given range
        for rng, vis, label in [(self.vrm1_range, self.vrm1_visible, "VRM1"),
                                 (self.vrm2_range, self.vrm2_visible, "VRM2")]:
            if not vis:
                continue
            pen = QPen(self.theme.vrm_circle, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            r = self.radius * (rng / self.range_nm) if self.range_nm > 0 else 0
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(ox, oy), r, r)
            # Label at right side
            painter.setFont(QFont('Consolas', 8, QFont.Weight.Bold))
            painter.drawText(int(ox + r + 4),
                             int(oy + 4),
                             f"{label} {rng:.2f}NM")

    def draw_cursor_info(self, painter):
        """Draw cursor bearing, range, lat/lon in the fixed data readout area."""
        sx, sy = self._cursor_sx, self._cursor_sy
        if sx < 0 or sy < 0:
            return
        dist = self._screen_dist_from_center(sx, sy)
        if dist > self.radius + 5:
            return

        bearing, range_nm = self.screen_to_bearing_range(sx, sy)
        lat, lon = self.screen_to_latlon(sx, sy)

        lat_dir = 'N' if lat >= 0 else 'S'
        lon_dir = 'E' if lon >= 0 else 'W'

        painter.setPen(QPen(self.theme.text_overlay, 1))
        painter.setFont(QFont('Consolas', 10))
        painter.drawText(10, 55, f"BRG: {bearing:05.1f}\u00b0  RNG: {range_nm:.2f}NM")
        painter.drawText(10, 72, f"{abs(lat):.5f}\u00b0{lat_dir}  {abs(lon):.5f}\u00b0{lon_dir}")

    def draw_cpa_summary(self, painter):
        """Draw top-3 closest CPA tracks in the fixed data readout area."""
        # Combine all tracks with valid CPA/TCPA
        all_tracks = []
        for t in self.radar_tracks:
            if t.get('cpa') is not None and t.get('tcpa') is not None and t['tcpa'] >= 0:
                all_tracks.append(t)
        for t in self.ais_tracks:
            # tcpa < 0 = CPA already passed (receding) — not listed
            if t.get('cpa') is not None and t.get('tcpa') is not None and t['tcpa'] >= 0:
                all_tracks.append(t)

        if not all_tracks:
            return

        # Sort by CPA distance (closest first), take top 3
        all_tracks.sort(key=lambda t: t['cpa'])
        top3 = all_tracks[:3]

        painter.setFont(QFont('Consolas', 9))
        fm = painter.fontMetrics()
        line_h = fm.height()

        # Start below cursor readout area (y=72) with a separator gap
        y_start = 95

        # Section header
        risk_color = self.theme.text_overlay
        painter.setPen(QPen(risk_color, 1))
        painter.drawText(10, y_start, "CLOSEST CPA")
        y = y_start + 4

        painter.setFont(QFont('Consolas', 8))
        line_h = painter.fontMetrics().height()

        for i, t in enumerate(top3):
            track_id = t.get('id', '?')
            name = t.get('name', '')
            cpa = t.get('cpa', 0)
            tcpa = t.get('tcpa', 0)
            spd = t.get('speed', 0)
            crs = t.get('course', 0)
            risk = t.get('risk_level', 'safe')

            # Color by risk level
            if risk == 'critical':
                color = self.theme.ais_target_dangerous
            elif risk == 'warning':
                color = QColor(255, 165, 0)
            elif risk == 'caution':
                color = QColor(255, 255, 0)
            else:
                color = self.theme.text_overlay
            painter.setPen(QPen(color, 1))

            # Line 1: track ID / name
            label = name if name else str(track_id)
            if len(label) > 16:
                label = label[:16]
            y += line_h
            painter.drawText(10, y, f"{i + 1}. {label}  [{track_id}]")

            # Line 2: CPA, TCPA, speed, course
            y += line_h
            painter.drawText(18, y,
                             f"CPA:{cpa:.2f}NM TCPA:{tcpa:.1f}m "
                             f"SPD:{spd:.1f}kt CRS:{crs:05.1f}\u00b0")

            # Small gap between entries
            y += 3

    def draw_own_ship(self, painter):
        if self.orientation_mode == OrientationMode.TRUE_MOTION:
            ox, oy = self.latlon_to_screen(self.own_lat, self.own_lon)
        else:
            ox, oy = self.center_x, self.center_y
        painter.setPen(QPen(self.theme.own_ship_symbol, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(ox, oy), 5, 5)

    def draw_heading_indicator(self, painter):
        rotation = self._get_rotation_angle()
        rad = math.radians(self.own_heading + rotation)
        if self.orientation_mode == OrientationMode.TRUE_MOTION:
            ox, oy = self.latlon_to_screen(self.own_lat, self.own_lon)
        else:
            ox, oy = self.center_x, self.center_y
        hx = ox + self.radius * 0.3 * math.sin(rad)
        hy = oy - self.radius * 0.3 * math.cos(rad)
        painter.setPen(QPen(self.theme.heading_line, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(ox), int(oy), int(hx), int(hy))

    def draw_range_scale(self, painter):
        if self.show_range_rings and self.range_ring_distances:
            painter.setFont(QFont('Consolas', 10))
            for i, dist_nm in enumerate(self.range_ring_distances):
                fraction = dist_nm / self.range_nm if self.range_nm > 0 else 0
                ring_radius = self.radius * fraction
                if i == self._drag_ring_index:
                    painter.setPen(QPen(self.theme.selection_highlight, 1))
                else:
                    painter.setPen(QPen(self.theme.range_ring_labels, 1))
                painter.drawText(self.center_x + 5,
                                 int(self.center_y - ring_radius + 5),
                                 f"{dist_nm:.1f} NM")

        # Cardinal directions
        rotation = self._get_rotation_angle()
        painter.setPen(QPen(self.theme.compass_text, 1))
        for angle, label in [(0, "N"), (90, "E"), (180, "S"), (270, "W")]:
            rad = math.radians(angle + rotation)
            x = self.center_x + (self.radius + 25) * math.sin(rad)
            y = self.center_y - (self.radius + 25) * math.cos(rad)
            painter.drawText(int(x - 5), int(y + 5), label)

    def draw_orientation_indicator(self, painter):
        labels = {
            OrientationMode.NORTH_UP: "N-UP",
            OrientationMode.HEAD_UP: "H-UP",
            OrientationMode.COURSE_UP: "C-UP",
            OrientationMode.TRUE_MOTION: "TM",
        }
        painter.setPen(QPen(self.theme.text_overlay, 1))
        painter.setFont(QFont('Consolas', 11, QFont.Weight.Bold))
        painter.drawText(10, 20, labels.get(self.orientation_mode, ""))

    def draw_ring_interval_indicator(self, painter):
        """Draw range scale on PPI overlay."""
        painter.setPen(QPen(self.theme.text_overlay, 1))
        painter.setFont(QFont('Consolas', 10))
        painter.drawText(10, 35, f"RNG: {self.range_nm:.1f} NM")

    def draw_vector(self, painter, x, y, course, length, color):
        rotation = self._get_rotation_angle()
        rad = math.radians(course + rotation)
        end_x = x + length * math.sin(rad)
        end_y = y - length * math.cos(rad)
        painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(x), int(y), int(end_x), int(end_y))

    def draw_ais_info_box(self, painter, ais, x, y):
        if not ais.get('mmsi') and not ais.get('id'):
            return
        painter.setFont(QFont('Consolas', 8))

        info_lines = []
        if ais.get('name'):
            info_lines.append(f"NAME: {ais['name'][:20]}")
        if ais.get('mmsi'):
            info_lines.append(f"MMSI: {ais['mmsi']}")
        cog = fmt(ais.get('course'), '05.1f') if ais.get('course_valid', True) else '---'
        sog = fmt(ais.get('speed'), '04.1f') if ais.get('speed_valid', True) else '---'
        info_lines.append(f"COG:{cog} SOG:{sog}")
        info_lines.append(f"CPA:{fmt(ais.get('cpa'), '.2f', 'NM')} "
                          f"TCPA:{fmt_tcpa(ais.get('tcpa'), 'm')}")
        if ais.get('encrypted'):
            key = ais.get('decrypt_key', '?')
            info_lines.append(f"SA-AIS [{key}]")
        if not info_lines:
            return

        max_w = max(painter.fontMetrics().horizontalAdvance(l) for l in info_lines)
        lh = painter.fontMetrics().height()
        bh = len(info_lines) * lh + 6
        bw = max_w + 10
        bx = int(x + 15)
        by = int(y - bh / 2)

        painter.setPen(QPen(self.theme.ais_info_text, 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.drawRect(bx, by, bw, bh)

        painter.setPen(QPen(self.theme.ais_info_text, 1))
        for i, line in enumerate(info_lines):
            painter.drawText(bx + 5, by + (i + 1) * lh, line)
