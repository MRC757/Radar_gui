"""
Main window for Radar GUI application
Professional ARPA-style interface with IMO-compliant display modes
"""

from datetime import datetime, timedelta

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QGroupBox, QComboBox,
                             QSlider, QStatusBar, QDockWidget,
                             QMenuBar, QMenu, QTextEdit, QMessageBox,
                             QDialog, QGridLayout, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QTimer, QPointF, QEvent, pyqtSignal
from PyQt6.QtGui import (QAction, QShortcut, QKeySequence,
                         QPainter, QPen, QBrush, QFont, QPainterPath, QPixmap, QColor)

from gui.ppi_display import PPIDisplayWidget, OrientationMode
from gui.nmea_config_dialog import NMEAConfigDialog
from gui.target_panel import SelectedTargetPanel
from gui.color_themes import DisplayMode, get_theme, dialog_stylesheet
from gui.guard_zone_dialog import GuardZoneDialog
from gui.bit_window import BITWindow
from gui.radar_config_dialog import RadarConfigDialog, load_radar_config
from gui.alarm_widget import AlarmWidget
from gui.ais_encrypt_dialog import AISEncryptDialog
from gui.cpa_settings_dialog import CPASettingsDialog
from gui.nmea_monitor_dialog import NMEAMonitorDialog
from gui.anchor_watch_dialog import AnchorWatchDialog
from core.multi_source_nmea_parser import MultiSourceNMEAParser
from core.track_manager import TrackManager
from core.radar_interface import MockRadarInterface
from core.cpa_calculator import calculate_intercept
from core.alarm_manager import AlarmManager
from core.camera_controller import CameraController, bearing_between
from core.adsb_receiver import AdsbReceiver


class _SystemMessagesDialog(QDialog):
    """Non-modal popup showing the full system message log."""

    def __init__(self, messages, theme, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Messages")
        self.resize(620, 480)
        self.setMinimumSize(400, 250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            f"QTextEdit {{ background-color: {theme.ppi_background.name()};"
            f" color: {theme.text_overlay.name()};"
            " font-family: Consolas; font-size: 11px;"
            f" border: 1px solid {theme.grid_lines.name()}; }}"
        )
        layout.addWidget(self._text)

        # Populate with existing messages
        for line in messages:
            self._text.append(line)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.close)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # Style the dialog itself
        self.setStyleSheet(
            f"QDialog {{ background-color: {theme.ppi_background.name()}; }}"
            f" QPushButton {{ background-color: #333333; color: {theme.text_overlay.name()};"
            " border: 1px solid #555555; padding: 4px 12px;"
            " font-family: Consolas; font-size: 10px; }}"
            " QPushButton:hover { background-color: #555555; }"
        )

    def append_message(self, line):
        """Append a new message and auto-scroll to bottom."""
        self._text.append(line)


class _ClickableLabel(QLabel):
    """QLabel that emits a signal on left double-click."""
    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class _SymbolLegendWidget(QWidget):
    """Paints PPI contact symbol examples for the Help dialog."""

    _SYMBOLS = [
        # (label, shape, color, x, y)
        ("Unencrypted AIS",  "triangle", (0, 200, 0),   70,  45),
        ("Encrypted AIS",    "triangle", (0, 120, 255), 230,  45),
        ("ARPA Radar",       "circle",   (0, 200, 0),   390,  45),
        ("Dangerous (flash)","triangle", (255, 0, 0),    70, 120),
        ("Dangerous ARPA",   "circle",   (255, 0, 0),   230, 120),
        ("AIS Base Station", "square",   (0, 210, 190), 390, 120),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(500, 165)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 10, 0))

        for label, shape, rgb, x, y in self._SYMBOLS:
            color = QColor(*rgb)
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if shape == "triangle":
                size = 10
                path = QPainterPath()
                path.moveTo(x, y - size)
                path.lineTo(x - size * 0.7, y + size * 0.5)
                path.lineTo(x + size * 0.7, y + size * 0.5)
                path.closeSubpath()
                painter.drawPath(path)
            elif shape == "circle":
                painter.drawEllipse(QPointF(x, y), 8, 8)
            elif shape == "square":
                painter.drawRect(int(x - 8), int(y - 8), 16, 16)

            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.setFont(QFont("Consolas", 8))
            painter.drawText(x + 14, y + 4, label)


class _HelpDialog(QDialog):
    """Help dialog showing PPI symbol legend and keyboard shortcuts."""

    _SHORTCUTS = [
        ("S",          "Alarm Acknowledge — silence active alarms"),
        ("Z",          "PPI Range In  (decrease range scale)"),
        ("X",          "PPI Range Out (increase range scale)"),
        ("+  /  =",    "Range Out (increase range scale)"),
        ("-",          "Range In  (decrease range scale)"),
        ("D",          "Cycle Display Mode (Day → Dusk → Night → Red Night)"),
        ("O",          "Cycle Orientation Mode (N-Up → H-Up → C-Up → True Motion)"),
        ("A",          "Toggle AIS Target display"),
        ("T",          "Toggle ARPA Track display"),
        ("L",          "Toggle past-position Trails"),
        ("G",          "Toggle Guard Zone overlay"),
        ("R",          "Toggle Range Rings"),
        ("F1",         "Toggle EBL 1"),
        ("F2",         "Toggle EBL 2"),
        ("F3",         "Toggle VRM 1"),
        ("F4",         "Toggle VRM 2"),
        ("F12",        "Silence / Unsilence Alarms (toggle)"),
        ("Ctrl+Q",     "Exit application"),
    ]

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help — PPI Symbols & Keyboard Shortcuts")
        self.resize(560, 640)
        self.setStyleSheet(dialog_stylesheet(theme))

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Symbol legend ---
        sym_label = QLabel("PPI CONTACT SYMBOLS")
        sym_label.setStyleSheet(
            f"color: {theme.ui_text_primary.name()}; font-family: Consolas;"
            " font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(sym_label)

        legend = _SymbolLegendWidget()
        layout.addWidget(legend)

        # --- Keyboard shortcuts ---
        kb_label = QLabel("KEYBOARD SHORTCUTS")
        kb_label.setStyleSheet(sym_label.styleSheet())
        layout.addWidget(kb_label)

        shortcuts_box = QTextEdit()
        shortcuts_box.setReadOnly(True)
        shortcuts_box.setStyleSheet(
            f"QTextEdit {{ background-color: {theme.ppi_background.name()};"
            f" color: {theme.text_overlay.name()};"
            " font-family: Consolas; font-size: 11px;"
            f" border: 1px solid {theme.ui_group_border.name()}; }}"
        )
        lines = []
        for key, desc in self._SHORTCUTS:
            lines.append(f"  {key:<12}  {desc}")
        shortcuts_box.setPlainText("\n".join(lines))
        layout.addWidget(shortcuts_box)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)


class RadarMainWindow(QMainWindow):
    """Main application window - Professional ARPA interface"""

    # Map combo-box text to enum values
    _DISPLAY_MODES = {
        "Day": DisplayMode.DAY,
        "Dusk": DisplayMode.DUSK,
        "Night": DisplayMode.NIGHT,
        "Red Night": DisplayMode.RED_NIGHT,
    }
    _ORIENTATION_MODES = {
        "North-Up": OrientationMode.NORTH_UP,
        "Head-Up": OrientationMode.HEAD_UP,
        "Course-Up": OrientationMode.COURSE_UP,
        "True Motion": OrientationMode.TRUE_MOTION,
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NextGen Radar Display - CG-ARPA")
        self.setGeometry(100, 100, 1600, 1000)

        # Initialize core components
        self.nmea_parser = MultiSourceNMEAParser()
        self.track_manager = TrackManager()
        self.radar_interface = MockRadarInterface()

        # Own ship state for course propagation
        self._own_speed = 0.0
        self._own_heading = 0.0

        # Currently selected target data (auto-refreshed)
        self._selected_target_data = None

        # Alarm manager
        self.alarm_manager = AlarmManager()

        # PTZ Camera controller
        self.camera_controller = CameraController()

        # ADS-B / FLARM receiver
        self.adsb_receiver = AdsbReceiver()

        # System message history (for popup window)
        self._all_messages = []
        self._sysmsg_dialog = None

        # Anchor Watch dialog reference
        self._anchor_watch_dialog = None

        # NMEA staleness tracking — last time each supplemental sentence was received
        self._last_stw_time = None
        self._last_water_temp_time = None
        self._last_wind_time = None
        self._nmea_stale_seconds = 10.0

        # Time display state
        self._tz_offset_hours = 0.0       # UTC offset (e.g. -5.0, +5.5)
        self._nmea_utc_time = ""          # "HH:MM:SS" from NMEA ZDA/RMC
        self._nmea_utc_date = ""          # "YYYY-MM-DD" from NMEA
        self._last_nmea_time_recv = None  # datetime.now() stamp when last received

        # Load radar configuration
        self._radar_configs = load_radar_config()
        self._active_radar_config = (
            self._radar_configs[0] if self._radar_configs else None
        )

        # Setup menu bar
        self.setup_menu()

        # Setup UI
        self.setup_ui()

        # Apply initial theme
        self._current_theme = get_theme(DisplayMode.DAY)
        self.apply_ui_theme()

        # Connect signals
        self.connect_signals()

        # Start update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)  # 10 Hz update

        # Setup keyboard shortcuts
        self.setup_shortcuts()

        # Start radar and NMEA
        self.radar_interface.start()
        self.nmea_parser.start_listening()

        # Start camera controller
        self.camera_controller.azimuth_updated.connect(self.on_camera_azimuth_updated)
        self.camera_controller.status_updated.connect(self.log_message)
        self.camera_controller.start_listening()

        # Start ADS-B receiver
        self.adsb_receiver.targets_updated.connect(self.on_adsb_targets_updated)
        self.adsb_receiver.status_updated.connect(self.log_message)
        self.adsb_receiver.start_listening()

        # Log system startup
        self.log_message("SYSTEM STARTED")
        self.log_message("Radar interface initialized")
        self.log_message("NMEA parser started")
        if self.camera_controller.config.get('enabled', False):
            self.log_message("Camera controller enabled")
        self.log_message("Ready for operation")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_message(self, message):
        """Log message to system display and popup (if open)."""
        if not hasattr(self, 'message_display'):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.message_display.append(line)
        self._all_messages.append(line)
        # Also push to the popup window if it's open
        if (hasattr(self, '_sysmsg_dialog')
                and self._sysmsg_dialog is not None
                and self._sysmsg_dialog.isVisible()):
            self._sysmsg_dialog.append_message(line)

    # ------------------------------------------------------------------
    # Event filter (System Messages double-click)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Open full system messages popup on double-click."""
        if event.type() == QEvent.Type.MouseButtonDblClick:
            if obj in (getattr(self, '_sysmsg_group', None),
                       getattr(self, 'message_display', None)):
                self._open_sysmsg_popup()
                return True
        return super().eventFilter(obj, event)

    def _open_sysmsg_popup(self):
        """Open (or raise) the full system messages popup window."""
        if self._sysmsg_dialog is not None and self._sysmsg_dialog.isVisible():
            self._sysmsg_dialog.raise_()
            self._sysmsg_dialog.activateWindow()
            return

        dialog = _SystemMessagesDialog(self._all_messages, self._current_theme,
                                       parent=self)
        dialog.show()
        self._sysmsg_dialog = dialog

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")

        radar_config_action = QAction("&Radar...", self)
        radar_config_action.triggered.connect(self.open_radar_config)
        settings_menu.addAction(radar_config_action)

        nmea_config_action = QAction("&NMEA Sources...", self)
        nmea_config_action.triggered.connect(self.open_nmea_config)
        settings_menu.addAction(nmea_config_action)

        guard_zone_config_action = QAction("&Guard Zones...", self)
        guard_zone_config_action.triggered.connect(self.open_guard_zone_config)
        settings_menu.addAction(guard_zone_config_action)

        ais_encrypt_action = QAction("&Encrypted AIS Keys...", self)
        ais_encrypt_action.triggered.connect(self.open_ais_encrypt_config)
        settings_menu.addAction(ais_encrypt_action)

        cpa_settings_action = QAction("&CPA/TCPA Thresholds...", self)
        cpa_settings_action.triggered.connect(self.open_cpa_settings)
        settings_menu.addAction(cpa_settings_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        bit_action = QAction("&Built-In Test...", self)
        bit_action.triggered.connect(self.open_bit_window)
        tools_menu.addAction(bit_action)

        tools_menu.addSeparator()
        nmea_monitor_action = QAction("NMEA &Monitor...", self)
        nmea_monitor_action.triggered.connect(self.open_nmea_monitor)
        tools_menu.addAction(nmea_monitor_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        self.show_ais_action = QAction("Show &AIS Targets", self)
        self.show_ais_action.setCheckable(True)
        self.show_ais_action.setChecked(True)
        self.show_ais_action.toggled.connect(self.on_show_ais_toggled)
        view_menu.addAction(self.show_ais_action)

        self.show_stationary_ais_action = QAction("Show &Moored / Stationary AIS", self)
        self.show_stationary_ais_action.setCheckable(True)
        self.show_stationary_ais_action.setChecked(True)
        self.show_stationary_ais_action.toggled.connect(self.on_show_stationary_ais_toggled)
        view_menu.addAction(self.show_stationary_ais_action)

        self.show_base_stations_action = QAction("Show AIS &Base Stations", self)
        self.show_base_stations_action.setCheckable(True)
        self.show_base_stations_action.setChecked(True)
        self.show_base_stations_action.toggled.connect(self.on_show_base_stations_toggled)
        view_menu.addAction(self.show_base_stations_action)

        self.show_adsb_action = QAction("Show &ADS-B Targets", self)
        self.show_adsb_action.setCheckable(True)
        self.show_adsb_action.setChecked(True)
        self.show_adsb_action.toggled.connect(self.on_show_adsb_toggled)
        view_menu.addAction(self.show_adsb_action)

        view_menu.addSeparator()
        anchor_watch_action = QAction("&Anchor Watch...", self)
        anchor_watch_action.triggered.connect(self.open_anchor_watch)
        view_menu.addAction(anchor_watch_action)
        view_menu.addSeparator()

        self.show_tracks_action = QAction("Show &Tracks", self)
        self.show_tracks_action.setCheckable(True)
        self.show_tracks_action.setChecked(True)
        self.show_tracks_action.toggled.connect(self.on_show_tracks_toggled)
        view_menu.addAction(self.show_tracks_action)

        self.show_guard_zones_action = QAction("Show &Guard Zones", self)
        self.show_guard_zones_action.setCheckable(True)
        self.show_guard_zones_action.setChecked(True)
        self.show_guard_zones_action.toggled.connect(self.on_show_guard_zones_toggled)
        view_menu.addAction(self.show_guard_zones_action)

        self.show_azimuth_action = QAction("Show A&zimuth Lines", self)
        self.show_azimuth_action.setCheckable(True)
        self.show_azimuth_action.setChecked(True)
        self.show_azimuth_action.toggled.connect(self.on_show_azimuth_toggled)
        view_menu.addAction(self.show_azimuth_action)

        view_menu.addSeparator()

        # Navigation panel toggle (uses QDockWidget's built-in toggle action)
        # The action is wired after create_info_panel() runs, so we store the
        # menu reference and add it later in setup_ui().
        self._view_menu = view_menu

        view_menu.addSeparator()

        # Range rings submenu
        ring_menu = view_menu.addMenu("Range &Rings")

        self.show_rings_action = QAction("&Show Range Rings", self)
        self.show_rings_action.setCheckable(True)
        self.show_rings_action.setChecked(True)
        self.show_rings_action.toggled.connect(self.on_show_range_rings_toggled)
        ring_menu.addAction(self.show_rings_action)

        ring_menu.addSeparator()

        self._ring_count_actions = []
        for count in [0, 2, 4, 6, 8]:
            label = "Off" if count == 0 else f"{count} Rings"
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(count == 4)
            action.triggered.connect(
                lambda checked, c=count: self.set_ring_count(c)
            )
            ring_menu.addAction(action)
            self._ring_count_actions.append(action)

        ring_menu.addSeparator()
        set_rings_action = QAction("Set Ring &Distances...", self)
        set_rings_action.triggered.connect(self.show_set_ring_distances_dialog)
        ring_menu.addAction(set_rings_action)

        reset_rings_action = QAction("&Reset to Equal Spacing", self)
        reset_rings_action.triggered.connect(self.reset_range_rings)
        ring_menu.addAction(reset_rings_action)

        # Trail length submenu
        trail_menu = view_menu.addMenu("Trail &Length")
        self._trail_length_actions = []
        for minutes in [1, 3, 6, 15, 30]:
            action = QAction(f"{minutes} min", self)
            action.setCheckable(True)
            action.setChecked(minutes == 6)  # default 6 min
            action.triggered.connect(lambda checked, m=minutes: self.set_trail_length(m))
            trail_menu.addAction(action)
            self._trail_length_actions.append(action)

        # EBL/VRM submenu
        view_menu.addSeparator()
        ebl_vrm_menu = view_menu.addMenu("EBL / VR&M")

        self.ebl1_action = QAction("EBL &1", self)
        self.ebl1_action.setCheckable(True)
        self.ebl1_action.setShortcut("F1")
        self.ebl1_action.toggled.connect(self.toggle_ebl1)
        ebl_vrm_menu.addAction(self.ebl1_action)

        self.ebl2_action = QAction("EBL &2", self)
        self.ebl2_action.setCheckable(True)
        self.ebl2_action.setShortcut("F2")
        self.ebl2_action.toggled.connect(self.toggle_ebl2)
        ebl_vrm_menu.addAction(self.ebl2_action)

        ebl_vrm_menu.addSeparator()

        self.vrm1_action = QAction("VRM &1", self)
        self.vrm1_action.setCheckable(True)
        self.vrm1_action.setShortcut("F3")
        self.vrm1_action.toggled.connect(self.toggle_vrm1)
        ebl_vrm_menu.addAction(self.vrm1_action)

        self.vrm2_action = QAction("VRM &2", self)
        self.vrm2_action.setCheckable(True)
        self.vrm2_action.setShortcut("F4")
        self.vrm2_action.toggled.connect(self.toggle_vrm2)
        ebl_vrm_menu.addAction(self.vrm2_action)

        ebl_vrm_menu.addSeparator()
        set_ebl1_action = QAction("Set EBL1 Bearing...", self)
        set_ebl1_action.triggered.connect(lambda: self.show_set_ebl_dialog(1))
        ebl_vrm_menu.addAction(set_ebl1_action)

        set_ebl2_action = QAction("Set EBL2 Bearing...", self)
        set_ebl2_action.triggered.connect(lambda: self.show_set_ebl_dialog(2))
        ebl_vrm_menu.addAction(set_ebl2_action)

        set_vrm1_action = QAction("Set VRM1 Range...", self)
        set_vrm1_action.triggered.connect(lambda: self.show_set_vrm_dialog(1))
        ebl_vrm_menu.addAction(set_vrm1_action)

        set_vrm2_action = QAction("Set VRM2 Range...", self)
        set_vrm2_action.triggered.connect(lambda: self.show_set_vrm_dialog(2))
        ebl_vrm_menu.addAction(set_vrm2_action)

        # Alarm controls
        view_menu.addSeparator()
        self.silence_action = QAction("S&ilence Alarms", self)
        self.silence_action.setCheckable(True)
        self.silence_action.setShortcut("F12")
        self.silence_action.toggled.connect(self.toggle_alarm_silence)
        view_menu.addAction(self.silence_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        help_menu.addSeparator()
        shortcuts_action = QAction("PPI Symbols && Keyboard Shortcuts...", self)
        shortcuts_action.triggered.connect(self.show_help_dialog)
        help_menu.addAction(shortcuts_action)

    def open_nmea_config(self):
        """Open NMEA configuration dialog"""
        dialog = NMEAConfigDialog(self)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        dialog.exec()

    def open_radar_config(self):
        """Open radar configuration dialog"""
        dialog = RadarConfigDialog(self)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        if dialog.exec():
            self._radar_configs = load_radar_config()
            self._populate_radar_combo()
            self.log_message("Radar configuration updated")

    def open_guard_zone_config(self):
        """Open guard zone configuration dialog"""
        dialog = GuardZoneDialog(self.track_manager.guard_zone_manager, self)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        if dialog.exec():
            self.log_message("Guard zones updated")

    def open_ais_encrypt_config(self):
        """Open encrypted AIS key management dialog."""
        dialog = AISEncryptDialog(self)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        if dialog.exec():
            self.nmea_parser.ais_decryptor.load_keys()
            count = self.nmea_parser.ais_decryptor.key_count
            self.log_message(f"AIS encryption keys updated ({count} enabled)")

    def open_cpa_settings(self):
        """Open CPA/TCPA threshold configuration dialog."""
        calc = self.track_manager.cpa_calculator
        dialog = CPASettingsDialog(calc, self)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        if dialog.exec():
            vals = dialog.get_values()
            # Apply to the track manager's CPA calculator
            calc.cpa_threshold = vals['cpa_threshold']
            calc.tcpa_threshold = vals['tcpa_threshold']
            calc.critical_cpa = vals['critical_cpa']
            calc.critical_tcpa = vals['critical_tcpa']
            calc.warning_cpa = vals['warning_cpa']
            calc.warning_tcpa = vals['warning_tcpa']
            calc.caution_cpa = vals['caution_cpa']
            calc.caution_tcpa = vals['caution_tcpa']
            # Also update the ThreatAssessor's internal calculator
            ta = self.track_manager.threat_assessor.cpa_calculator
            ta.cpa_threshold = vals['cpa_threshold']
            ta.tcpa_threshold = vals['tcpa_threshold']
            ta.critical_cpa = vals['critical_cpa']
            ta.critical_tcpa = vals['critical_tcpa']
            ta.warning_cpa = vals['warning_cpa']
            ta.warning_tcpa = vals['warning_tcpa']
            ta.caution_cpa = vals['caution_cpa']
            ta.caution_tcpa = vals['caution_tcpa']
            self.log_message(
                f"CPA/TCPA thresholds updated — "
                f"Gate: {vals['cpa_threshold']:.1f} NM / {vals['tcpa_threshold']:.0f} min, "
                f"Critical: {vals['critical_cpa']:.1f} NM / {vals['critical_tcpa']:.0f} min"
            )

    def open_bit_window(self):
        """Open Built-In Test window"""
        dialog = BITWindow(
            radar_interface=self.radar_interface,
            nmea_parser=self.nmea_parser,
            parent=self,
        )
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        dialog.exec()

    def open_nmea_monitor(self):
        """Open NMEA Monitor window"""
        dialog = NMEAMonitorDialog(
            nmea_parser=self.nmea_parser,
            parent=self,
        )
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        dialog.exec()

    def open_anchor_watch(self):
        """Open (or raise) the Anchor Watch window."""
        if self._anchor_watch_dialog is None or not self._anchor_watch_dialog.isVisible():
            self._anchor_watch_dialog = AnchorWatchDialog(
                nmea_parser=self.nmea_parser,
                track_manager=self.track_manager,
                alarm_manager=self.alarm_manager,
                parent=self,
            )
            self._anchor_watch_dialog.setStyleSheet(
                dialog_stylesheet(self._current_theme)
            )
            self.ppi_display.set_anchor_watch(self._anchor_watch_dialog)
            self._anchor_watch_dialog.finished.connect(
                lambda _: self.ppi_display.set_anchor_watch(None)
            )
        self._anchor_watch_dialog.show()
        self._anchor_watch_dialog.raise_()

    def show_help_dialog(self):
        """Show PPI symbol legend and keyboard shortcuts help dialog."""
        dialog = _HelpDialog(self._current_theme, parent=self)
        dialog.exec()

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Radar GUI",
                         "Marine Radar Display System\n\n"
                         "Professional ARPA-compliant radar display\n"
                         "IMO Resolution A.823(19) compliant\n"
                         "IEC 62388 / SN.1/Circ.243/Rev.2 display modes\n\n"
                         "Version 3.7\n\n"
                         "Features:\n"
                         "- Day / Dusk / Night / Red Night modes\n"
                         "- North-Up / Head-Up / Course-Up / True Motion\n"
                         "- EBL/VRM navigation tools\n"
                         "- Target selection with detail panel\n"
                         "- Past-position trails\n"
                         "- Guard zone visualization\n"
                         "- Audible alarms with per-alarm ACK\n"
                         "- Configurable CPA/TCPA alarm thresholds\n"
                         "- Multi-source NMEA-0183 input (19 sentence types)\n"
                         "- AIS decoder (ITU-R M.1371 Types 1/2/3/5/18/24)\n"
                         "- Encrypted AIS (SA-AIS) via AES-128/256-CBC\n"
                         "- Own-ship SOG, STW, water temp, wind display\n"
                         "- CPA/TCPA calculations with threat summary\n"
                         "- GPS spoofing detection\n"
                         "- Keyboard shortcuts\n"
                         "- Graceful shutdown with signal handling\n\n"
                         "Ready for radar SDK integration")

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def setup_shortcuts(self):
        """Configure keyboard shortcuts."""
        # Range shortcuts — +/= and Z increase range (zoom out), -/X decrease (zoom in)
        QShortcut(QKeySequence(Qt.Key.Key_Plus), self, lambda: self._cycle_range(1))
        QShortcut(QKeySequence(Qt.Key.Key_Equal), self, lambda: self._cycle_range(1))
        QShortcut(QKeySequence(Qt.Key.Key_Minus), self, lambda: self._cycle_range(-1))
        QShortcut(QKeySequence("Z"), self, lambda: self._cycle_range(-1))   # Z = Range In
        QShortcut(QKeySequence("X"), self, lambda: self._cycle_range(1))    # X = Range Out

        # Alarm acknowledge
        QShortcut(QKeySequence("S"), self, self._ack_alarm)

        # Display mode cycling
        QShortcut(QKeySequence("D"), self, self._cycle_display_mode)

        # Orientation cycling
        QShortcut(QKeySequence("O"), self, self._cycle_orientation)

        # AIS / ADS-B / Tracks / Trails toggle
        QShortcut(QKeySequence("A"), self, lambda: self.show_ais_btn.toggle())
        QShortcut(QKeySequence("B"), self, lambda: self.show_adsb_btn.toggle())
        QShortcut(QKeySequence("T"), self, lambda: self.show_tracks_btn.toggle())
        QShortcut(QKeySequence("L"), self, lambda: self.show_trails_btn.toggle())

        # Guard zones toggle
        QShortcut(QKeySequence("G"), self,
                  lambda: self.show_guard_zones_action.setChecked(
                      not self.show_guard_zones_action.isChecked()))

        # Range rings toggle
        QShortcut(QKeySequence("R"), self,
                  lambda: self.show_rings_action.setChecked(
                      not self.show_rings_action.isChecked()))

    def _cycle_range(self, direction):
        """Cycle through range settings."""
        idx = self.range_combo.currentIndex()
        new_idx = max(0, min(idx + direction, self.range_combo.count() - 1))
        self.range_combo.setCurrentIndex(new_idx)

    def _cycle_display_mode(self):
        """Cycle through display modes."""
        idx = (self.display_mode_combo.currentIndex() + 1) % self.display_mode_combo.count()
        self.display_mode_combo.setCurrentIndex(idx)

    def _cycle_orientation(self):
        """Cycle through orientation modes."""
        idx = (self.orientation_combo.currentIndex() + 1) % self.orientation_combo.count()
        self.orientation_combo.setCurrentIndex(idx)

    def _ack_alarm(self):
        """Acknowledge (silence) active alarms — S key."""
        if self.alarm_manager.active_alarms:
            self.alarm_manager.silence()
            self.log_message("ALARM ACKNOWLEDGED")
            self.silence_action.blockSignals(True)
            self.silence_action.setChecked(True)
            self.silence_action.blockSignals(False)

    # ------------------------------------------------------------------
    # EBL / VRM controls
    # ------------------------------------------------------------------

    def toggle_ebl1(self, checked):
        self.ppi_display.set_ebl1(self.ppi_display.ebl1_bearing, checked)
        self._update_ebl_vrm_status()
        self.log_message(f"EBL1 {'ON' if checked else 'OFF'}: {self.ppi_display.ebl1_bearing:.1f}\u00b0")

    def toggle_ebl2(self, checked):
        self.ppi_display.set_ebl2(self.ppi_display.ebl2_bearing, checked)
        self._update_ebl_vrm_status()
        self.log_message(f"EBL2 {'ON' if checked else 'OFF'}: {self.ppi_display.ebl2_bearing:.1f}\u00b0")

    def toggle_vrm1(self, checked):
        self.ppi_display.set_vrm1(self.ppi_display.vrm1_range, checked)
        self._update_ebl_vrm_status()
        self.log_message(f"VRM1 {'ON' if checked else 'OFF'}: {self.ppi_display.vrm1_range:.2f} NM")

    def toggle_vrm2(self, checked):
        self.ppi_display.set_vrm2(self.ppi_display.vrm2_range, checked)
        self._update_ebl_vrm_status()
        self.log_message(f"VRM2 {'ON' if checked else 'OFF'}: {self.ppi_display.vrm2_range:.2f} NM")

    def show_set_ebl_dialog(self, index):
        """Show dialog to manually enter an EBL bearing."""
        current = (self.ppi_display.ebl1_bearing if index == 1
                   else self.ppi_display.ebl2_bearing)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Set EBL{index} Bearing")
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        layout = QGridLayout(dialog)
        layout.addWidget(QLabel(f"EBL{index} Bearing (\u00b0T):"), 0, 0)
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 359.9)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setWrapping(True)
        spin.setValue(current)
        layout.addWidget(spin, 0, 1)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Set")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout, 1, 0, 1, 2)
        if dialog.exec():
            brg = spin.value()
            if index == 1:
                self.ppi_display.set_ebl1(brg, True)
                self.ebl1_action.blockSignals(True)
                self.ebl1_action.setChecked(True)
                self.ebl1_action.blockSignals(False)
            else:
                self.ppi_display.set_ebl2(brg, True)
                self.ebl2_action.blockSignals(True)
                self.ebl2_action.setChecked(True)
                self.ebl2_action.blockSignals(False)
            self._update_ebl_vrm_status()
            self.log_message(f"EBL{index} set to {brg:.1f}\u00b0")

    def show_set_vrm_dialog(self, index):
        """Show dialog to manually enter a VRM range."""
        current = (self.ppi_display.vrm1_range if index == 1
                   else self.ppi_display.vrm2_range)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Set VRM{index} Range")
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        layout = QGridLayout(dialog)
        layout.addWidget(QLabel(f"VRM{index} Range (NM):"), 0, 0)
        spin = QDoubleSpinBox()
        spin.setRange(0.01, 96.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.25)
        spin.setValue(current)
        layout.addWidget(spin, 0, 1)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Set")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout, 1, 0, 1, 2)
        if dialog.exec():
            rng = spin.value()
            if index == 1:
                self.ppi_display.set_vrm1(rng, True)
                self.vrm1_action.blockSignals(True)
                self.vrm1_action.setChecked(True)
                self.vrm1_action.blockSignals(False)
            else:
                self.ppi_display.set_vrm2(rng, True)
                self.vrm2_action.blockSignals(True)
                self.vrm2_action.setChecked(True)
                self.vrm2_action.blockSignals(False)
            self._update_ebl_vrm_status()
            self.log_message(f"VRM{index} set to {rng:.2f} NM")

    def show_set_ring_distances_dialog(self):
        """Show dialog to manually set individual range ring distances."""
        dists = self.ppi_display.get_range_ring_distances()
        if not dists:
            dists = [3.0, 6.0, 9.0, 12.0]

        dialog = QDialog(self)
        dialog.setWindowTitle("Set Range Ring Distances")
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Enter distance (NM) for each ring:"))

        grid = QGridLayout()
        spins = []
        for i, d in enumerate(dists):
            grid.addWidget(QLabel(f"Ring {i + 1}:"), i, 0)
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 96.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.5)
            spin.setValue(d)
            grid.addWidget(spin, i, 1)
            spins.append(spin)
        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        if dialog.exec():
            new_dists = sorted(spin.value() for spin in spins)
            self.ppi_display.set_range_ring_distances(new_dists)
            self.ppi_display.set_show_range_rings(True)
            self.show_rings_action.blockSignals(True)
            self.show_rings_action.setChecked(True)
            self.show_rings_action.blockSignals(False)
            self.log_message(
                f"Range rings set: {', '.join(f'{d:.2f}' for d in new_dists)} NM"
            )

    def toggle_alarm_silence(self, checked):
        if checked:
            self.alarm_manager.silence()
            self.log_message("ALARMS SILENCED")
        else:
            self.alarm_manager.unsilence()
            self.log_message("ALARMS ACTIVE")

    def _update_ebl_vrm_status(self):
        """Update status bar EBL/VRM readout."""
        parts = []
        if self.ppi_display.ebl1_visible:
            parts.append(f"EBL1:{self.ppi_display.ebl1_bearing:05.1f}\u00b0")
        if self.ppi_display.ebl2_visible:
            parts.append(f"EBL2:{self.ppi_display.ebl2_bearing:05.1f}\u00b0")
        if self.ppi_display.vrm1_visible:
            parts.append(f"VRM1:{self.ppi_display.vrm1_range:.2f}NM")
        if self.ppi_display.vrm2_visible:
            parts.append(f"VRM2:{self.ppi_display.vrm2_range:.2f}NM")
        self.ebl_vrm_label.setText("  ".join(parts))

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def setup_ui(self):
        """Setup user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Top controls
        controls = self.create_controls()
        layout.addWidget(controls)

        # PPI Display (main radar screen)
        self.ppi_display = PPIDisplayWidget()
        layout.addWidget(self.ppi_display, stretch=1)

        # Alarm widget (strip below PPI)
        self.alarm_widget = AlarmWidget(self.alarm_manager)
        layout.addWidget(self.alarm_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Radar System Ready")

        # Cursor position label in status bar (permanent)
        self.cursor_label = QLabel("BRG: ---   RNG: ---")
        self.cursor_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 10px;")
        self.status_bar.addPermanentWidget(self.cursor_label)

        # EBL/VRM readout in status bar
        self.ebl_vrm_label = QLabel("")
        self.ebl_vrm_label.setStyleSheet("color: #FFB400; font-family: Consolas; font-size: 10px;")
        self.status_bar.addPermanentWidget(self.ebl_vrm_label)

        # Alarm status in status bar
        self.alarm_label = QLabel("")
        self.alarm_label.setStyleSheet("color: #FF0000; font-family: Consolas; font-size: 10px; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.alarm_label)

        # Right side panel for information
        self.create_info_panel()

        # Left side panel with 3 target displays
        self.create_target_dock()

        # Add dock toggle actions to View menu (docks must exist first)
        first_action = self._view_menu.actions()[0]
        nav_toggle = self.nav_dock.toggleViewAction()
        nav_toggle.setText("&Navigation Panel")
        self._view_menu.insertAction(first_action, nav_toggle)

        tgt_toggle = self.target_dock.toggleViewAction()
        tgt_toggle.setText("Target &Data Panels")
        self._view_menu.insertAction(first_action, tgt_toggle)

        self._view_menu.insertSeparator(first_action)

    def _make_control_label(self, text):
        """Create a control bar label and track it for theme updates."""
        label = QLabel(text)
        self._control_labels.append(label)
        return label

    def create_controls(self):
        """Create top control panel"""
        self._control_labels = []
        self.controls_group = QGroupBox("Radar Controls")
        layout = QHBoxLayout()

        # Standby / Transmit toggle — placed first for immediate visibility
        self.transmit_btn = QPushButton("STBY")
        self.transmit_btn.setCheckable(True)
        self.transmit_btn.setChecked(False)
        self.transmit_btn.setFixedWidth(70)
        self.transmit_btn.setToolTip(
            "Toggle radar between Standby and Transmit.\n"
            "STBY = radar powered but not transmitting.\n"
            "TX   = radar transmitting."
        )
        self.transmit_btn.toggled.connect(self.on_transmit_toggled)
        layout.addWidget(self.transmit_btn)

        layout.addSpacing(10)

        # Radar selection
        layout.addWidget(self._make_control_label("Radar:"))
        self.radar_combo = QComboBox()
        self._populate_radar_combo()
        self.radar_combo.currentTextChanged.connect(self.on_radar_selected)
        layout.addWidget(self.radar_combo)

        layout.addSpacing(15)

        # Range control
        layout.addWidget(self._make_control_label("Range:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["0.5 NM", "1.5 NM", "3 NM", "6 NM",
                                   "12 NM", "24 NM", "48 NM", "96 NM"])
        self.range_combo.setCurrentText("12 NM")
        self.range_combo.currentTextChanged.connect(self.on_range_changed)
        layout.addWidget(self.range_combo)

        layout.addSpacing(15)

        # Display mode
        layout.addWidget(self._make_control_label("Display:"))
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(list(self._DISPLAY_MODES.keys()))
        self.display_mode_combo.currentTextChanged.connect(self.on_display_mode_changed)
        layout.addWidget(self.display_mode_combo)

        layout.addSpacing(15)

        # Orientation mode
        layout.addWidget(self._make_control_label("Orient:"))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(list(self._ORIENTATION_MODES.keys()))
        self.orientation_combo.currentTextChanged.connect(self.on_orientation_changed)
        layout.addWidget(self.orientation_combo)

        layout.addSpacing(15)

        # Video mode
        layout.addWidget(self._make_control_label("Video:"))
        self.video_mode_combo = QComboBox()
        self.video_mode_combo.addItems(["Processed", "Raw"])
        self.video_mode_combo.currentTextChanged.connect(self.on_video_mode_changed)
        layout.addWidget(self.video_mode_combo)

        layout.addSpacing(15)

        # Gain slider
        layout.addWidget(self._make_control_label("Gain:"))
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(0, 100)
        self.gain_slider.setValue(50)
        self.gain_slider.setFixedWidth(100)
        self.gain_value_label = QLabel("50%")
        self.gain_value_label.setFixedWidth(35)
        self._control_labels.append(self.gain_value_label)
        self.gain_slider.valueChanged.connect(self.on_gain_changed)
        layout.addWidget(self.gain_slider)
        layout.addWidget(self.gain_value_label)

        layout.addSpacing(10)

        # Sea Clutter slider
        layout.addWidget(self._make_control_label("Sea:"))
        self.sea_clutter_slider = QSlider(Qt.Orientation.Horizontal)
        self.sea_clutter_slider.setRange(0, 100)
        self.sea_clutter_slider.setValue(0)
        self.sea_clutter_slider.setFixedWidth(100)
        self.sea_clutter_value_label = QLabel("0%")
        self.sea_clutter_value_label.setFixedWidth(35)
        self._control_labels.append(self.sea_clutter_value_label)
        self.sea_clutter_slider.valueChanged.connect(self.on_sea_clutter_changed)
        layout.addWidget(self.sea_clutter_slider)
        layout.addWidget(self.sea_clutter_value_label)

        layout.addSpacing(10)

        # Rain Clutter slider
        layout.addWidget(self._make_control_label("Rain:"))
        self.rain_clutter_slider = QSlider(Qt.Orientation.Horizontal)
        self.rain_clutter_slider.setRange(0, 100)
        self.rain_clutter_slider.setValue(0)
        self.rain_clutter_slider.setFixedWidth(100)
        self.rain_clutter_value_label = QLabel("0%")
        self.rain_clutter_value_label.setFixedWidth(35)
        self._control_labels.append(self.rain_clutter_value_label)
        self.rain_clutter_slider.valueChanged.connect(self.on_rain_clutter_changed)
        layout.addWidget(self.rain_clutter_slider)
        layout.addWidget(self.rain_clutter_value_label)

        layout.addSpacing(15)

        # Display toggle buttons
        self.show_ais_btn = QPushButton("AIS")
        self.show_ais_btn.setCheckable(True)
        self.show_ais_btn.setChecked(True)
        self.show_ais_btn.toggled.connect(self.on_show_ais_toggled)
        layout.addWidget(self.show_ais_btn)

        self.show_adsb_btn = QPushButton("ADSB")
        self.show_adsb_btn.setCheckable(True)
        self.show_adsb_btn.setChecked(True)
        self.show_adsb_btn.toggled.connect(self.on_show_adsb_toggled)
        layout.addWidget(self.show_adsb_btn)

        self.show_tracks_btn = QPushButton("Tracks")
        self.show_tracks_btn.setCheckable(True)
        self.show_tracks_btn.setChecked(True)
        self.show_tracks_btn.toggled.connect(self.on_show_tracks_toggled)
        layout.addWidget(self.show_tracks_btn)

        self.show_trails_btn = QPushButton("Trails")
        self.show_trails_btn.setCheckable(True)
        self.show_trails_btn.setChecked(True)
        self.show_trails_btn.toggled.connect(self.on_show_trails_toggled)
        layout.addWidget(self.show_trails_btn)

        layout.addStretch()

        self.controls_group.setLayout(layout)
        return self.controls_group

    def create_info_panel(self):
        """Create right side information panel - Professional ARPA style"""
        self.nav_dock = QDockWidget("Navigation & System Data", self)
        self.nav_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.nav_dock.setMinimumWidth(300)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Own ship info
        own_ship_group = QGroupBox("OWN SHIP")
        own_ship_group.setStyleSheet("QGroupBox { color: #00FF00; font-weight: bold; }")
        own_ship_layout = QVBoxLayout()

        # Time / Date  (double-click opens timezone dialog)
        _time_tip = "Double-click to set time zone"
        self.date_label = _ClickableLabel("DATE: ----/--/--")
        self.date_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")
        self.date_label.setToolTip(_time_tip)
        self.date_label.double_clicked.connect(self._open_timezone_dialog)

        self.time_label = _ClickableLabel("TIME: --:--:-- UTC")
        self.time_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")
        self.time_label.setToolTip(_time_tip)
        self.time_label.double_clicked.connect(self._open_timezone_dialog)

        self.position_label = QLabel("POSN: -- / --")
        self.position_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.heading_label = QLabel("HDG:  ---\u00b0")
        self.heading_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.sog_label = QLabel("SOG:  --.- kts")
        self.sog_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.stw_label = QLabel("STW:  --.- kts")
        self.stw_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.depth_label = QLabel("DEPTH: --.- m")
        self.depth_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.water_temp_label = QLabel("WTMP: --.- \u00b0C")
        self.water_temp_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.wind_label = QLabel("WIND: ---\u00b0 / --.- kts")
        self.wind_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.spoofing_label = QLabel("")
        self.spoofing_label.setStyleSheet(
            "color: #FF0000; font-family: Consolas; font-size: 11px; font-weight: bold;"
        )
        self.spoofing_label.setVisible(False)

        own_ship_layout.addWidget(self.date_label)
        own_ship_layout.addWidget(self.time_label)
        own_ship_layout.addWidget(self.position_label)
        own_ship_layout.addWidget(self.heading_label)
        own_ship_layout.addWidget(self.sog_label)
        own_ship_layout.addWidget(self.stw_label)
        own_ship_layout.addWidget(self.depth_label)
        own_ship_layout.addWidget(self.water_temp_label)
        own_ship_layout.addWidget(self.wind_label)
        own_ship_layout.addWidget(self.spoofing_label)
        own_ship_group.setLayout(own_ship_layout)
        layout.addWidget(own_ship_group)

        # NMEA Source Status
        source_group = QGroupBox("NMEA SOURCES")
        source_group.setStyleSheet("QGroupBox { color: #00CCFF; font-weight: bold; }")
        source_layout = QVBoxLayout()

        self.gps_source_label = QLabel("GPS: --")
        self.gps_source_label.setStyleSheet("color: #00CCFF; font-family: Consolas; font-size: 10px;")

        self.heading_source_label = QLabel("HDG: --")
        self.heading_source_label.setStyleSheet("color: #00CCFF; font-family: Consolas; font-size: 10px;")

        self.depth_source_label = QLabel("DEPTH: --")
        self.depth_source_label.setStyleSheet("color: #00CCFF; font-family: Consolas; font-size: 10px;")

        source_layout.addWidget(self.gps_source_label)
        source_layout.addWidget(self.heading_source_label)
        source_layout.addWidget(self.depth_source_label)
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # Radar status
        radar_group = QGroupBox("RADAR STATUS")
        radar_group.setStyleSheet("QGroupBox { color: #00FF00; font-weight: bold; }")
        radar_layout = QVBoxLayout()

        self.radar_status_label = QLabel("Status: STANDBY")
        self.radar_status_label.setStyleSheet("color: #FFFF00; font-family: Consolas; font-size: 11px;")

        self.target_count_label = QLabel("TGT: 000")
        self.target_count_label.setStyleSheet("color: #00FF00; font-family: Consolas; font-size: 11px;")

        self.ais_count_label = QLabel("AIS: 000")
        self.ais_count_label.setStyleSheet("color: #FFDC00; font-family: Consolas; font-size: 11px;")

        radar_layout.addWidget(self.radar_status_label)
        radar_layout.addWidget(self.target_count_label)
        radar_layout.addWidget(self.ais_count_label)
        radar_group.setLayout(radar_layout)
        layout.addWidget(radar_group)

        # Selected target panel (between radar status and AIS list)
        self.target_panel = SelectedTargetPanel()
        layout.addWidget(self.target_panel)

        # AIS Targets List
        ais_list_group = QGroupBox("AIS TARGETS")
        ais_list_group.setStyleSheet("QGroupBox { color: #FFDC00; font-weight: bold; }")
        ais_list_layout = QVBoxLayout()

        self.ais_list = QTextEdit()
        self.ais_list.setReadOnly(True)
        self.ais_list.setMaximumHeight(200)
        self.ais_list.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #FFDC00;
                font-family: Consolas;
                font-size: 9px;
                border: 1px solid #00FF00;
            }
        """)
        ais_list_layout.addWidget(self.ais_list)
        ais_list_group.setLayout(ais_list_layout)
        layout.addWidget(ais_list_group)

        # System Messages
        msg_group = QGroupBox("SYSTEM MESSAGES")
        msg_group.setStyleSheet("QGroupBox { color: #00CCFF; font-weight: bold; }")
        msg_layout = QVBoxLayout()

        self.message_display = QTextEdit()
        self.message_display.setReadOnly(True)
        self.message_display.setMaximumHeight(150)
        self.message_display.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00CCFF;
                font-family: Consolas;
                font-size: 9px;
                border: 1px solid #00FF00;
            }
        """)
        msg_layout.addWidget(self.message_display)
        msg_group.setLayout(msg_layout)
        layout.addWidget(msg_group)

        # Double-click on the group box or text area opens full log popup
        msg_group.installEventFilter(self)
        self.message_display.installEventFilter(self)
        self._sysmsg_group = msg_group

        layout.addStretch()

        self.nav_dock.setWidget(widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.nav_dock)

    def create_target_dock(self):
        """Create left-side dock with 3 target detail panels."""
        self.target_dock = QDockWidget("Target Data", self)
        self.target_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.target_dock.setMinimumWidth(260)

        container = QWidget()
        layout = QVBoxLayout(container)

        self._left_target_panels = []
        self._left_target_ids = [None, None, None]  # tracked target IDs
        self._next_slot = 0  # round-robin index

        for i in range(3):
            panel = SelectedTargetPanel(title=f"TARGET {i + 1}")
            # Add a clear button inside each panel's layout
            clear_btn = QPushButton("CLR")
            clear_btn.setFixedWidth(40)
            clear_btn.setStyleSheet(
                "QPushButton { background-color: #222; color: #FF4444; "
                "border: 1px solid #AA0000; font-family: Consolas; font-size: 9px; }"
                "QPushButton:hover { background-color: #440000; }"
            )
            clear_btn.clicked.connect(lambda _, idx=i: self._clear_target_slot(idx))
            panel.layout().addWidget(clear_btn, 0, 2)

            layout.addWidget(panel)
            self._left_target_panels.append(panel)

        layout.addStretch()
        self.target_dock.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.target_dock)

    def _clear_target_slot(self, slot):
        """Clear a specific left-side target slot."""
        self._left_target_ids[slot] = None
        self._left_target_panels[slot].clear()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def connect_signals(self):
        """Connect signals between components"""
        # NMEA parser signals
        self.nmea_parser.position_updated.connect(self.on_position_updated)
        self.nmea_parser.heading_updated.connect(self.on_heading_updated)
        self.nmea_parser.depth_updated.connect(self.on_depth_updated)
        self.nmea_parser.ais_updated.connect(self.on_ais_updated)
        self.nmea_parser.base_stations_updated.connect(self.on_base_stations_updated)
        self.nmea_parser.source_status_updated.connect(self.on_source_status_updated)
        self.nmea_parser.stw_updated.connect(self.on_stw_updated)
        self.nmea_parser.water_temp_updated.connect(self.on_water_temp_updated)
        self.nmea_parser.wind_updated.connect(self.on_wind_updated)
        self.nmea_parser.time_updated.connect(self.on_time_updated)

        # GPS spoofing detection
        self.nmea_parser.spoofing_detector.spoofing_alert.connect(
            self.on_spoofing_alert
        )

        # Radar interface signals
        self.radar_interface.radar_data_updated.connect(self.on_radar_data_updated)
        self.radar_interface.transmit_state_changed.connect(self.on_transmit_state_changed)

        # PPI target interaction signals
        self.ppi_display.target_selected.connect(self.on_target_selected)
        self.ppi_display.target_deselected.connect(self.on_target_deselected)
        self.ppi_display.cursor_moved.connect(self.on_cursor_moved)
        self.ppi_display.range_rings_changed.connect(self.on_range_rings_changed)
        self.ppi_display.context_menu_requested.connect(self.show_target_context_menu)

    # ------------------------------------------------------------------
    # Theme application
    # ------------------------------------------------------------------

    def apply_ui_theme(self):
        """Restyle sidebar panels to match the current display mode theme."""
        t = self._current_theme
        primary = t.ui_text_primary.name()
        secondary = t.ui_text_secondary.name()
        border = t.ui_group_border.name()
        bg = t.ui_background.name()
        accent = t.ui_accent.name()
        warning = t.ui_warning.name()

        # Global stylesheet for main window, menus, and dock widgets
        global_style = f"""
            QMainWindow {{ background-color: {bg}; }}
            QMenuBar {{
                background-color: {bg};
                color: {primary};
                font-family: Consolas;
                font-size: 12px;
                border-bottom: 1px solid {border};
            }}
            QMenuBar::item {{
                background-color: transparent;
                padding: 4px 10px;
            }}
            QMenuBar::item:selected {{
                background-color: {border};
                color: {bg};
            }}
            QMenu {{
                background-color: {bg};
                color: {primary};
                border: 1px solid {border};
                font-family: Consolas;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {border};
                color: {bg};
            }}
            QMenu::separator {{
                height: 1px;
                background: {border};
            }}
            QDockWidget {{
                color: {primary};
                font-family: Consolas;
                font-weight: bold;
            }}
            QDockWidget::title {{
                background-color: {bg};
                color: {primary};
                padding: 4px;
                border: 1px solid {border};
            }}
        """
        self.setStyleSheet(global_style)

        # Apply background directly on each dock widget so it persists when floated
        dock_widget_style = f"background-color: {bg};"
        for dock in (self.nav_dock, self.target_dock):
            dock.setStyleSheet(
                f"QDockWidget {{ color: {primary}; font-weight: bold; }}"
                f"QDockWidget::title {{ background-color: {bg}; padding: 4px; "
                f"border: 1px solid {border}; }}"
            )
            inner = dock.widget()
            if inner:
                inner.setStyleSheet(dock_widget_style)

        # Own ship labels
        own_ship_style = f"color: {primary}; font-family: Consolas; font-size: 11px;"
        for label in (self.date_label, self.time_label,
                      self.position_label, self.heading_label,
                      self.sog_label, self.stw_label, self.depth_label,
                      self.water_temp_label, self.wind_label):
            label.setStyleSheet(own_ship_style)

        # Source labels
        source_style = f"color: {secondary}; font-family: Consolas; font-size: 10px;"
        for label in (self.gps_source_label, self.heading_source_label,
                      self.depth_source_label):
            label.setStyleSheet(source_style)

        # Radar status
        self.target_count_label.setStyleSheet(
            f"color: {primary}; font-family: Consolas; font-size: 11px;"
        )
        self.ais_count_label.setStyleSheet(
            f"color: {warning}; font-family: Consolas; font-size: 11px;"
        )

        # Text areas
        textedit_style = f"""
            QTextEdit {{
                background-color: {bg};
                color: {accent};
                font-family: Consolas;
                font-size: 9px;
                border: 1px solid {border};
            }}
        """
        self.message_display.setStyleSheet(textedit_style)
        self.ais_list.setStyleSheet(textedit_style.replace(accent, warning))

        # Cursor label
        self.cursor_label.setStyleSheet(
            f"color: {primary}; font-family: Consolas; font-size: 10px;"
        )

        # EBL/VRM readout
        self.ebl_vrm_label.setStyleSheet(
            f"color: {warning}; font-family: Consolas; font-size: 10px;"
        )

        # Alarm status
        critical = t.ui_critical.name()
        self.alarm_label.setStyleSheet(
            f"color: {critical}; font-family: Consolas; font-size: 10px; font-weight: bold;"
        )

        # Alarm widget
        self.alarm_widget.apply_theme(bg, primary, border, critical)

        # Target panels (right + 3 left)
        self.target_panel.apply_theme_colors(primary, border)
        for panel in self._left_target_panels:
            panel.apply_theme_colors(primary, border)

        # Control bar group box and labels
        self.controls_group.setStyleSheet(
            f"QGroupBox {{ color: {primary}; font-weight: bold; "
            f"font-family: Consolas; border: 1px solid {border}; "
            f"margin-top: 6px; padding-top: 6px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; "
            f"padding: 0 4px; }}"
        )
        ctrl_label_style = f"color: {primary}; font-family: Consolas; font-size: 11px;"
        for label in self._control_labels:
            label.setStyleSheet(ctrl_label_style)

        # Control bar combo boxes and sliders
        combo_style = (
            f"QComboBox {{ background-color: {bg}; color: {primary}; "
            f"border: 1px solid {border}; padding: 2px 4px; font-family: Consolas; }}"
            f"QComboBox QAbstractItemView {{ background-color: {bg}; color: {primary}; "
            f"border: 1px solid {border}; selection-background-color: {border}; "
            f"selection-color: {bg}; }}"
        )
        for combo in (self.radar_combo, self.range_combo, self.display_mode_combo,
                       self.orientation_combo, self.video_mode_combo):
            combo.setStyleSheet(combo_style)

        slider_style = (
            f"QSlider::groove:horizontal {{ background: {border}; height: 6px; "
            f"border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{ background: {primary}; width: 14px; "
            f"margin: -4px 0; border-radius: 7px; }}"
        )
        for slider in (self.gain_slider, self.sea_clutter_slider,
                        self.rain_clutter_slider):
            slider.setStyleSheet(slider_style)

        # Control bar toggle buttons
        btn_style = (
            f"QPushButton {{ background-color: {bg}; color: {primary}; "
            f"border: 1px solid {border}; padding: 4px 8px; font-family: Consolas; }}"
            f"QPushButton:checked {{ background-color: {border}; color: {bg}; }}"
            f"QPushButton:hover {{ background-color: {border}; color: {bg}; }}"
        )
        for btn in (self.show_ais_btn, self.show_adsb_btn,
                    self.show_tracks_btn, self.show_trails_btn):
            btn.setStyleSheet(btn_style)

        # Transmit button keeps its own fixed colour scheme regardless of theme
        self._apply_transmit_btn_style(self.transmit_btn.isChecked())

    # ------------------------------------------------------------------
    # 10 Hz update loop
    # ------------------------------------------------------------------

    def update_display(self):
        """Update display at 10 Hz"""
        # Get current tracks
        radar_tracks = self.track_manager.get_radar_tracks()
        ais_tracks = self.track_manager.get_ais_tracks()

        # Update PPI display
        self.ppi_display.update_tracks(radar_tracks, ais_tracks)

        # Pass guard zone data to PPI
        gzm = self.track_manager.guard_zone_manager
        self.ppi_display.update_guard_zones(gzm.zones, gzm.intrusions)

        # Update target counts
        self.target_count_label.setText(f"TGT: {len(radar_tracks):03d}")
        self.ais_count_label.setText(f"AIS: {len(ais_tracks):03d}")

        # Update EBL/VRM status bar readout (updates during drag)
        self._update_ebl_vrm_status()

        # --- Alarm checks ---
        # CPA threat alarms
        has_critical = False
        has_warning = False
        for t in radar_tracks + ais_tracks:
            risk = t.get('risk_level', 'safe')
            if risk == 'critical':
                has_critical = True
            elif risk == 'warning':
                has_warning = True

        if has_critical:
            self.alarm_manager.trigger('cpa_critical', 'Collision risk detected')
        elif has_warning:
            self.alarm_manager.trigger('cpa_warning', 'Close approach target')
        else:
            self.alarm_manager.clear('cpa_critical')
            self.alarm_manager.clear('cpa_warning')

        # Guard zone intrusion alarm
        intruded = [z for z, tgts in gzm.intrusions.items() if tgts]
        if intruded:
            self.alarm_manager.trigger('guard_zone',
                                       f"Intrusion: {', '.join(intruded[:3])}")
        else:
            self.alarm_manager.clear('guard_zone')

        # Sensor loss alarm — check for stale navigation sources
        gps_src = self.nmea_parser.active_gps_source
        hdg_src = self.nmea_parser.active_heading_source
        dep_src = self.nmea_parser.active_depth_source
        gps_active = gps_src is not None and gps_src.is_active()
        hdg_active = hdg_src is not None and hdg_src.is_active()
        dep_active = dep_src is not None and dep_src.is_active()
        lost = []
        if not gps_active:
            lost.append('GPS')
        if not hdg_active:
            lost.append('Heading')
        if not dep_active:
            lost.append('Depth')
        if lost:
            self.alarm_manager.trigger('sensor_loss',
                                       f"{', '.join(lost)} data offline")
        else:
            self.alarm_manager.clear('sensor_loss')

        # Alarm status label
        active = self.alarm_manager.active_alarms
        if self.alarm_manager.is_silenced:
            self.alarm_label.setText("ALARM SILENCED")
        elif active:
            self.alarm_label.setText("ALARM: " + " | ".join(
                a.upper().replace('_', ' ') for a in sorted(active)))
        else:
            self.alarm_label.setText("")

        # Color NMEA data labels red when data is stale / unavailable
        self._update_nmea_label_staleness(gps_active, hdg_active, dep_active)

        # Tick the time display
        self._refresh_time_label()

        # Auto-refresh selected target data (right panel)
        if self._selected_target_data is not None:
            target_id = self._selected_target_data.get('id')
            refreshed = self._find_target(target_id, radar_tracks, ais_tracks)
            if refreshed:
                self._selected_target_data = refreshed
                self.target_panel.update_target(refreshed)

        # Auto-refresh left-side target panels
        for i, tid in enumerate(self._left_target_ids):
            if tid is None:
                continue
            refreshed = self._find_target(tid, radar_tracks, ais_tracks)
            if refreshed:
                self._left_target_panels[i].update_target(refreshed)
            else:
                # Target lost - clear the slot
                self._left_target_ids[i] = None
                self._left_target_panels[i].clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_nmea_label_staleness(self, gps_active, hdg_active, dep_active):
        """Color own-ship NMEA data labels red when data is stale or unavailable."""
        now = datetime.now()
        stale_style = (
            "color: #FF2222; font-family: Consolas; font-size: 11px; font-weight: bold;"
        )
        good_style = (
            f"color: {self._current_theme.ui_text_primary.name()};"
            " font-family: Consolas; font-size: 11px;"
        )

        self.position_label.setStyleSheet(stale_style if not gps_active else good_style)
        self.sog_label.setStyleSheet(stale_style if not gps_active else good_style)
        self.heading_label.setStyleSheet(stale_style if not hdg_active else good_style)
        self.depth_label.setStyleSheet(stale_style if not dep_active else good_style)

        def _is_stale(last_time):
            if last_time is None:
                return True
            return (now - last_time).total_seconds() > self._nmea_stale_seconds

        self.stw_label.setStyleSheet(stale_style if _is_stale(self._last_stw_time) else good_style)
        self.water_temp_label.setStyleSheet(
            stale_style if _is_stale(self._last_water_temp_time) else good_style)
        self.wind_label.setStyleSheet(
            stale_style if _is_stale(self._last_wind_time) else good_style)

    def _refresh_time_label(self):
        """Update date/time labels — uses NMEA UTC if fresh, otherwise system clock."""
        now = datetime.utcnow()
        nmea_fresh = (
            self._last_nmea_time_recv is not None
            and (datetime.now() - self._last_nmea_time_recv).total_seconds() < 5
            and self._nmea_utc_time
        )

        if nmea_fresh:
            try:
                h, m, s = (int(p) for p in self._nmea_utc_time.split(':'))
                now = now.replace(hour=h, minute=m, second=s, microsecond=0)
                if self._nmea_utc_date:
                    y, mo, d = (int(p) for p in self._nmea_utc_date.split('-'))
                    now = now.replace(year=y, month=mo, day=d)
            except (ValueError, AttributeError):
                pass
            src_tag = "GPS"
        else:
            src_tag = "SYS"

        local = now + timedelta(hours=self._tz_offset_hours)

        # Build timezone label  e.g. "UTC", "UTC-5", "UTC+5.5"
        if self._tz_offset_hours == 0:
            tz_str = "UTC"
        elif self._tz_offset_hours > 0:
            tz_str = f"UTC+{self._tz_offset_hours:g}"
        else:
            tz_str = f"UTC{self._tz_offset_hours:g}"

        self.date_label.setText(f"DATE: {local.strftime('%Y/%m/%d')}  ({src_tag})")
        self.time_label.setText(f"TIME: {local.strftime('%H:%M:%S')}  {tz_str}")

    def _open_timezone_dialog(self):
        """Open dialog to set the local time zone (UTC offset)."""
        _PRESETS = [
            ("UTC  (UTC+0)",     0.0),
            ("GMT  (UTC+0)",     0.0),
            ("EST  (UTC-5)",    -5.0),
            ("EDT  (UTC-4)",    -4.0),
            ("CST  (UTC-6)",    -6.0),
            ("CDT  (UTC-5)",    -5.0),
            ("MST  (UTC-7)",    -7.0),
            ("MDT  (UTC-6)",    -6.0),
            ("PST  (UTC-8)",    -8.0),
            ("PDT  (UTC-7)",    -7.0),
            ("CET  (UTC+1)",     1.0),
            ("CEST (UTC+2)",     2.0),
            ("EET  (UTC+2)",     2.0),
            ("EEST (UTC+3)",     3.0),
            ("MSK  (UTC+3)",     3.0),
            ("IST  (UTC+5:30)",  5.5),
            ("ICT  (UTC+7)",     7.0),
            ("CST  (UTC+8)",     8.0),
            ("JST  (UTC+9)",     9.0),
            ("AEST (UTC+10)",   10.0),
            ("NZST (UTC+12)",   12.0),
        ]

        dialog = QDialog(self)
        dialog.setWindowTitle("Set Time Zone")
        dialog.setMinimumWidth(300)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Select a preset or enter a custom UTC offset:"))

        preset_combo = QComboBox()
        for label, _ in _PRESETS:
            preset_combo.addItem(label)
        layout.addWidget(preset_combo)

        layout.addWidget(QLabel("Custom UTC offset (hours, e.g. \u20125.5):"))
        offset_spin = QDoubleSpinBox()
        offset_spin.setRange(-12.0, 14.0)
        offset_spin.setSingleStep(0.5)
        offset_spin.setDecimals(1)
        offset_spin.setValue(self._tz_offset_hours)
        layout.addWidget(offset_spin)

        # Preset selection fills the spin box
        def _apply_preset(idx):
            offset_spin.setValue(_PRESETS[idx][1])
        preset_combo.currentIndexChanged.connect(_apply_preset)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        if dialog.exec():
            self._tz_offset_hours = offset_spin.value()
            self._refresh_time_label()
            sign = "+" if self._tz_offset_hours >= 0 else ""
            self.log_message(f"Time zone set to UTC{sign}{self._tz_offset_hours:g}")

    def _find_target(self, target_id, radar_tracks, ais_tracks):
        """Find a target by ID across radar and AIS track lists."""
        if target_id is None:
            return None
        for t in radar_tracks:
            if t.get('id') == target_id:
                return t
        for t in ais_tracks:
            if t.get('id') == target_id:
                return t
        return None

    # ------------------------------------------------------------------
    # Radar config helpers
    # ------------------------------------------------------------------

    def _populate_radar_combo(self):
        """Refresh the Radar dropdown from the current config list."""
        self.radar_combo.blockSignals(True)
        prev = self.radar_combo.currentText()
        self.radar_combo.clear()
        for cfg in self._radar_configs:
            if cfg.get('enabled', True):
                self.radar_combo.addItem(cfg['name'])
        # Restore previous selection if still present
        idx = self.radar_combo.findText(prev)
        if idx >= 0:
            self.radar_combo.setCurrentIndex(idx)
        self.radar_combo.blockSignals(False)
        # Update active config to match current selection
        self.on_radar_selected(self.radar_combo.currentText())

    def on_radar_selected(self, name):
        """Handle radar selection change."""
        if not name:
            return
        for cfg in self._radar_configs:
            if cfg['name'] == name:
                self._active_radar_config = cfg
                self.log_message(
                    f"Radar: {name} ({cfg.get('ip', '?')}:{cfg.get('port', '?')})"
                )
                return

    # ------------------------------------------------------------------
    # Slots: control bar
    # ------------------------------------------------------------------

    def on_range_changed(self, range_text):
        old_range = self.ppi_display.range_nm
        new_range = float(range_text.split()[0])
        # Scale ring distances proportionally
        if old_range > 0:
            scale = new_range / old_range
            new_dists = [d * scale for d in self.ppi_display.get_range_ring_distances()]
            self.ppi_display.set_range_ring_distances(new_dists)
        self.ppi_display.set_range(new_range)
        self.radar_interface.set_range(new_range)

    def on_video_mode_changed(self, mode):
        self.radar_interface.set_video_mode(mode.lower())
        self.ppi_display.set_video_mode(mode.lower())

    def on_transmit_toggled(self, checked: bool):
        """Operator pressed the STBY/TX toggle — send command to radar."""
        self.radar_interface.set_transmit(checked)
        # Button label and style update is handled by on_transmit_state_changed
        # which is called via the radar_interface.transmit_state_changed signal.
        # This keeps the GUI in sync with the actual hardware state rather than
        # the operator's intent, so if the SDK rejects the command the button
        # stays in its previous state.

    def on_transmit_state_changed(self, transmitting: bool):
        """Called when radar hardware confirms its transmit state."""
        # Block signals while updating button to avoid a feedback loop
        self.transmit_btn.blockSignals(True)
        self.transmit_btn.setChecked(transmitting)
        self.transmit_btn.blockSignals(False)
        self._apply_transmit_btn_style(transmitting)
        state_str = "TRANSMIT" if transmitting else "STANDBY"
        self.log_message(f"RADAR {state_str}")

    def _apply_transmit_btn_style(self, transmitting: bool):
        """Apply colour coding to the TX/STBY button based on current state."""
        if transmitting:
            self.transmit_btn.setText("TX")
            self.transmit_btn.setStyleSheet(
                "QPushButton {"
                "  background-color: #003300;"
                "  color: #00FF44;"
                "  border: 2px solid #00FF44;"
                "  font-family: Consolas;"
                "  font-size: 12px;"
                "  font-weight: bold;"
                "  padding: 4px 8px;"
                "}"
                "QPushButton:hover {"
                "  background-color: #005500;"
                "}"
            )
        else:
            self.transmit_btn.setText("STBY")
            self.transmit_btn.setStyleSheet(
                "QPushButton {"
                "  background-color: #1A1200;"
                "  color: #FFAA00;"
                "  border: 2px solid #FFAA00;"
                "  font-family: Consolas;"
                "  font-size: 12px;"
                "  font-weight: bold;"
                "  padding: 4px 8px;"
                "}"
                "QPushButton:hover {"
                "  background-color: #2A1E00;"
                "}"
            )

    def on_gain_changed(self, value):
        self.gain_value_label.setText(f"{value}%")
        self.radar_interface.set_gain(value)

    def on_sea_clutter_changed(self, value):
        self.sea_clutter_value_label.setText(f"{value}%")
        self.radar_interface.set_sea_clutter(value)

    def on_rain_clutter_changed(self, value):
        self.rain_clutter_value_label.setText(f"{value}%")
        self.radar_interface.set_rain_clutter(value)

    def on_display_mode_changed(self, text):
        mode = self._DISPLAY_MODES.get(text)
        if mode is None:
            return
        self._current_theme = get_theme(mode)
        self.ppi_display.set_display_mode(mode)
        self.apply_ui_theme()
        self.log_message(f"Display mode: {text}")

    def on_orientation_changed(self, text):
        mode = self._ORIENTATION_MODES.get(text)
        if mode is None:
            return
        self.ppi_display.set_orientation_mode(mode)
        self.log_message(f"Orientation: {text}")

    def on_show_ais_toggled(self, checked):
        self.ppi_display.set_show_ais(checked)

    def on_show_stationary_ais_toggled(self, checked):
        self.ppi_display.set_show_stationary_ais(checked)

    def on_show_base_stations_toggled(self, checked):
        self.ppi_display.set_show_base_stations(checked)

    def on_show_adsb_toggled(self, checked):
        self.ppi_display.set_show_adsb(checked)

    def on_adsb_targets_updated(self, tracks: list):
        self.ppi_display.set_adsb_tracks(tracks)

    def on_base_stations_updated(self, base_stations):
        self.ppi_display.base_station_tracks = base_stations
        self.ppi_display.update()

    def on_show_tracks_toggled(self, checked):
        self.ppi_display.set_show_tracks(checked)

    def on_show_trails_toggled(self, checked):
        self.ppi_display.show_trails = checked
        self.ppi_display.update()

    def on_show_guard_zones_toggled(self, checked):
        self.ppi_display.show_guard_zones = checked
        self.ppi_display.update()

    def on_show_azimuth_toggled(self, checked):
        self.ppi_display.set_show_azimuth_lines(checked)

    def set_trail_length(self, minutes):
        """Set trail length and update menu check marks."""
        for action in self._trail_length_actions:
            action.setChecked(action.text() == f"{minutes} min")
        self.track_manager.set_trail_length(minutes)
        self.log_message(f"Trail length: {minutes} min")

    def on_show_range_rings_toggled(self, checked):
        """Toggle range ring visibility from menu."""
        self.ppi_display.set_show_range_rings(checked)
        self.log_message(f"Range rings: {'ON' if checked else 'OFF'}")

    def set_ring_count(self, count):
        """Set ring count and update menu check marks."""
        for action in self._ring_count_actions:
            expected = 0 if action.text() == "Off" else int(action.text().split()[0])
            action.setChecked(expected == count)

        # Sync the Show toggle
        self.show_rings_action.blockSignals(True)
        self.show_rings_action.setChecked(count > 0)
        self.show_rings_action.blockSignals(False)

        self.ppi_display.set_show_range_rings(count > 0)
        self.ppi_display.set_range_ring_count(count)

        if count == 0:
            self.log_message("Range rings: OFF")
        else:
            interval = self.ppi_display.range_nm / count
            self.log_message(f"Range rings: {count} rings ({interval:.2f} NM interval)")

    def on_range_rings_changed(self):
        """Handle range ring drag completion."""
        dists = self.ppi_display.get_range_ring_distances()
        self.log_message(
            f"Range rings adjusted: {', '.join(f'{d:.1f}' for d in dists)} NM"
        )

    def reset_range_rings(self):
        """Reset rings to equal spacing using current ring count."""
        count = len(self.ppi_display.get_range_ring_distances())
        if count > 0:
            self.ppi_display.set_range_ring_count(count)
            self.log_message(f"Range rings reset to {count} equal intervals")

    # ------------------------------------------------------------------
    # Slots: target selection (from PPI)
    # ------------------------------------------------------------------

    def on_target_selected(self, target_data):
        self._selected_target_data = target_data
        self.target_panel.update_target(target_data)

        # Assign to left-side target slot
        target_id = target_data.get('id')
        # If already tracked in a slot, just update that slot
        if target_id in self._left_target_ids:
            idx = self._left_target_ids.index(target_id)
            self._left_target_panels[idx].update_target(target_data)
            return
        # Find the next empty slot, or use round-robin
        slot = None
        for i in range(3):
            if self._left_target_ids[i] is None:
                slot = i
                break
        if slot is None:
            slot = self._next_slot
            self._next_slot = (self._next_slot + 1) % 3
        self._left_target_ids[slot] = target_id
        self._left_target_panels[slot].update_target(target_data)

    def on_target_deselected(self):
        self._selected_target_data = None
        self.target_panel.clear()

    def on_cursor_moved(self, bearing, range_nm):
        self.cursor_label.setText(f"BRG: {bearing:05.1f}\u00b0   RNG: {range_nm:.2f} NM")

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------

    def show_target_context_menu(self, target_data, screen_pos):
        """Build and show context menu for a right-clicked target."""
        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet())

        target_id = target_data.get('id')
        target_type = target_data.get('_selection_type', target_data.get('type', ''))
        is_radar = target_type == 'radar'

        # Target Info
        info_action = menu.addAction("Target Info...")
        info_action.triggered.connect(lambda: self.show_target_info_dialog(target_data))

        menu.addSeparator()

        # Acquire / Cancel Track (radar only)
        acquire_action = menu.addAction("Acquire / Track")
        acquire_action.setEnabled(is_radar)
        acquire_action.triggered.connect(lambda: self.acquire_target(target_data))

        cancel_action = menu.addAction("Cancel Track")
        cancel_action.setEnabled(is_radar)
        cancel_action.triggered.connect(lambda: self.cancel_track(target_data))

        menu.addSeparator()

        # Classification submenu
        mark_menu = menu.addMenu("Mark as")
        current_cls = self.track_manager.get_target_classification(target_id)

        for cls_name in ('friendly', 'neutral', 'hostile'):
            action = mark_menu.addAction(cls_name.capitalize())
            action.setCheckable(True)
            action.setChecked(current_cls == cls_name)
            action.triggered.connect(
                lambda checked, c=cls_name: self.set_target_classification(target_id, c)
            )

        mark_menu.addSeparator()
        clear_cls_action = mark_menu.addAction("Clear Classification")
        clear_cls_action.setEnabled(current_cls is not None)
        clear_cls_action.triggered.connect(
            lambda: self.set_target_classification(target_id, None)
        )

        menu.addSeparator()

        # CPA/TCPA Alert
        cpa_action = menu.addAction("Set CPA/TCPA Alert...")
        cpa_action.triggered.connect(lambda: self.show_cpa_alert_dialog(target_data))

        # Guard Zone
        gz_action = menu.addAction("Add to Guard Zone...")
        gz_action.triggered.connect(lambda: self.show_add_guard_zone_dialog(target_data))

        menu.addSeparator()

        # Intercept Calculator
        intercept_action = menu.addAction("Calculate Intercept...")
        intercept_action.triggered.connect(lambda: self.show_intercept_dialog(target_data))

        # Reference target
        ref_action = menu.addAction("Set as Reference Target")
        ref_action.triggered.connect(lambda: self.set_reference_target(target_data))

        menu.addSeparator()

        # Camera slew
        cam_action = menu.addAction("Slew Camera to Target")
        cam_action.setEnabled(self.camera_controller.config.get('enabled', False))
        cam_action.triggered.connect(
            lambda: self._slew_camera_to_target(target_data)
        )
        if not self.camera_controller.config.get('enabled', False):
            cam_action.setToolTip("Enable camera control in Settings → NMEA Sources → Camera")

        # Show at cursor position
        global_pos = self.ppi_display.mapToGlobal(screen_pos.toPoint())
        menu.exec(global_pos)

    def show_target_info_dialog(self, target_data):
        """Show detailed target information dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Target Information")
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))

        layout = QGridLayout(dialog)
        layout.setSpacing(4)

        fields = [
            ("Type", target_data.get('type', '--').upper()),
            ("ID", str(target_data.get('id', '--'))[:20]),
            ("Name", target_data.get('name', '--')),
            ("MMSI", str(target_data.get('mmsi', '--'))),
            ("Latitude", f"{target_data.get('lat', 0):.6f}\u00b0"),
            ("Longitude", f"{target_data.get('lon', 0):.6f}\u00b0"),
            ("Course", f"{target_data.get('course', 0):.1f}\u00b0"),
            ("Speed", f"{target_data.get('speed', 0):.1f} kts"),
            ("Bearing", f"{target_data.get('bearing', 0):.1f}\u00b0"),
            ("Range", f"{target_data.get('range', 0):.2f} NM"),
            ("CPA", f"{target_data.get('cpa', 0):.2f} NM"),
            ("TCPA", f"{target_data.get('tcpa', 0):.1f} min"),
            ("Risk Level", target_data.get('risk_level', 'safe').upper()),
            ("Classification", (target_data.get('classification') or '--').upper()),
            ("Guard Zones", ', '.join(target_data.get('guard_zones', [])) or 'CLEAR'),
        ]

        for i, (label_text, value_text) in enumerate(fields):
            label = QLabel(f"{label_text}:")
            value = QLabel(str(value_text))
            layout.addWidget(label, i, 0)
            layout.addWidget(value, i, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, len(fields), 0, 1, 2)

        dialog.exec()

    def acquire_target(self, target_data):
        """Acquire radar target for ARPA tracking."""
        target_id = target_data.get('id', '?')
        self.log_message(f"ARPA ACQUIRE: {target_id}")

    def cancel_track(self, target_data):
        """Cancel tracking of a radar target."""
        target_id = target_data.get('id')
        if target_id and target_id in self.track_manager.radar_tracks:
            del self.track_manager.radar_tracks[target_id]
            self.track_manager.track_history.pop(target_id, None)
            self.track_manager.track_filters.pop(target_id, None)
            self.track_manager.target_classifications.pop(target_id, None)
            self.log_message(f"TRACK CANCELLED: {target_id}")
            # Deselect if this was the selected target
            if self.ppi_display.selected_target_id == target_id:
                self.ppi_display.selected_target_id = None
                self.ppi_display.selected_target_type = None
                self.ppi_display.target_deselected.emit()

    def set_target_classification(self, target_id, classification):
        """Set target classification (friendly/neutral/hostile/None)."""
        self.track_manager.set_target_classification(target_id, classification)
        if classification:
            self.log_message(f"TARGET {target_id}: classified {classification.upper()}")
        else:
            self.log_message(f"TARGET {target_id}: classification cleared")

    def show_cpa_alert_dialog(self, target_data):
        """Show dialog to set per-target CPA/TCPA alert thresholds."""
        dialog = QDialog(self)
        dialog.setWindowTitle("CPA/TCPA Alert Settings")
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))

        layout = QGridLayout(dialog)

        target_id = target_data.get('id', '?')
        layout.addWidget(QLabel(f"Target: {target_id}"), 0, 0, 1, 2)

        layout.addWidget(QLabel("CPA Threshold (NM):"), 1, 0)
        cpa_spin = QDoubleSpinBox()
        cpa_spin.setRange(0.1, 10.0)
        cpa_spin.setValue(2.0)
        cpa_spin.setSingleStep(0.1)
        layout.addWidget(cpa_spin, 1, 1)

        layout.addWidget(QLabel("TCPA Threshold (min):"), 2, 0)
        tcpa_spin = QDoubleSpinBox()
        tcpa_spin.setRange(1.0, 60.0)
        tcpa_spin.setValue(12.0)
        tcpa_spin.setSingleStep(1.0)
        layout.addWidget(tcpa_spin, 2, 1)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Set Alert")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout, 3, 0, 1, 2)

        if dialog.exec():
            cpa_val = cpa_spin.value()
            tcpa_val = tcpa_spin.value()
            self.log_message(
                f"CPA ALERT SET: {target_id} — CPA < {cpa_val:.1f} NM, "
                f"TCPA < {tcpa_val:.0f} min"
            )

    def show_add_guard_zone_dialog(self, target_data):
        """Open guard zone config dialog."""
        dialog = GuardZoneDialog(self.track_manager.guard_zone_manager, self)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))
        if dialog.exec():
            self.log_message("Guard zones updated")

    def show_intercept_dialog(self, target_data):
        """Calculate and display intercept course/speed/time."""
        own_ship = self.track_manager.own_ship
        result = calculate_intercept(own_ship, target_data)

        dialog = QDialog(self)
        dialog.setWindowTitle("Intercept Calculation")
        dialog.setMinimumWidth(420)
        dialog.setStyleSheet(dialog_stylesheet(self._current_theme))

        layout = QGridLayout(dialog)
        layout.setSpacing(4)

        target_id = target_data.get('id', '?')
        target_name = target_data.get('name', '')
        header = f"TARGET: {target_id}"
        if target_name and target_name != '--':
            header += f" ({target_name})"
        layout.addWidget(QLabel(header), 0, 0, 1, 2)

        rows = [
            ("Target Course", f"{target_data.get('course', 0):.1f}\u00b0"),
            ("Target Speed", f"{target_data.get('speed', 0):.1f} kts"),
            ("Own Ship Course", f"{own_ship['course']:.1f}\u00b0"),
            ("Own Ship Speed", f"{own_ship['speed']:.1f} kts"),
            ("", ""),  # spacer
            ("Intercept Course", f"{result['intercept_course']:.1f}\u00b0"),
            ("Min Speed Required", f"{result['intercept_speed_min']:.1f} kts"),
        ]

        if result['feasible'] and result['intercept_time'] is not None:
            rows.append(("Time to Intercept", f"{result['intercept_time']:.1f} min"))
            rows.append(("Intercept Position",
                         f"{result['intercept_lat']:.5f}\u00b0 / "
                         f"{result['intercept_lon']:.5f}\u00b0"))
        else:
            rows.append(("Time to Intercept", "NOT FEASIBLE at current speed"))
            if result['intercept_speed_min'] > 0:
                rows.append(("",
                    f"Increase speed to >= {result['intercept_speed_min']:.1f} kts"))

        row_idx = 1
        for label_text, value_text in rows:
            if label_text == "" and value_text == "":
                row_idx += 1
                continue
            if label_text:
                layout.addWidget(QLabel(f"{label_text}:"), row_idx, 0)
            layout.addWidget(QLabel(value_text), row_idx, 1)
            row_idx += 1

        # COLREGS note
        note = QLabel("COLREGS Rule 8: Alterations of course and/or speed\n"
                       "shall be positive and made in ample time.")
        layout.addWidget(note, row_idx, 0, 1, 2)
        row_idx += 1

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, row_idx, 0, 1, 2)

        dialog.exec()

    def set_reference_target(self, target_data):
        """Set target as reference for relative motion."""
        target_id = target_data.get('id', '?')
        self.log_message(f"REFERENCE TARGET SET: {target_id}")

    # ------------------------------------------------------------------
    # Slots: NMEA data
    # ------------------------------------------------------------------

    def on_position_updated(self, lat, lon, speed, source_name):
        self.position_label.setText(f"POSN: {lat:.6f}\u00b0 / {lon:.6f}\u00b0")
        self.sog_label.setText(f"SOG:  {speed:.1f} kts")
        self.ppi_display.set_own_ship_position(lat, lon)

        # Propagate to track manager for CPA calculations
        self._own_speed = speed
        self.track_manager.update_own_ship(lat, lon, self._own_heading, speed)

        # Keep ADS-B receiver updated so relative positions convert correctly
        self.adsb_receiver.set_own_position(lat, lon)

    def on_heading_updated(self, heading, source_name):
        self.heading_label.setText(f"HDG:  {heading:05.1f}\u00b0")
        self.ppi_display.set_own_ship_heading(heading)

        # Use heading as course for Course-Up and CPA until separate course source exists
        self._own_heading = heading
        self.ppi_display.own_course = heading
        self.track_manager.update_own_ship(
            self.track_manager.own_ship['lat'],
            self.track_manager.own_ship['lon'],
            heading,
            self._own_speed,
        )

    def on_depth_updated(self, depth, source_name):
        self.depth_label.setText(f"DEPTH: {depth:.1f} m")

    def on_stw_updated(self, stw):
        self.stw_label.setText(f"STW:  {stw:.1f} kts")
        self._last_stw_time = datetime.now()

    def on_water_temp_updated(self, temp):
        self.water_temp_label.setText(f"WTMP: {temp:.1f} \u00b0C")
        self._last_water_temp_time = datetime.now()

    def on_wind_updated(self, angle, speed_kts, reference):
        ref_tag = "R" if reference == "R" else "T"
        self.wind_label.setText(
            f"WIND: {angle:05.1f}\u00b0{ref_tag} / {speed_kts:.1f} kts")
        self._last_wind_time = datetime.now()

    def on_time_updated(self, utc_time, utc_date):
        self._nmea_utc_time = utc_time
        self._nmea_utc_date = utc_date
        self._last_nmea_time_recv = datetime.now()
        self._refresh_time_label()

    def on_ais_updated(self, ais_targets):
        self.track_manager.update_ais_tracks(ais_targets)

        # Update AIS list display
        ais_text = ""
        for i, ais in enumerate(ais_targets[:10]):
            name = ais.get('name', 'Unknown')[:15]
            mmsi = ais.get('mmsi', '000000000')
            cog = ais.get('course', 0)
            sog = ais.get('speed', 0)
            ais_text += f"{i+1:02d}  {name:15s} {mmsi}\n"
            ais_text += f"    COG:{cog:05.1f}\u00b0 SOG:{sog:04.1f}kts\n"
        self.ais_list.setPlainText(ais_text)

    def on_source_status_updated(self, status):
        self.gps_source_label.setText(f"GPS: {status.get('active_gps', 'None')}")
        self.heading_source_label.setText(f"HDG: {status.get('active_heading', 'None')}")
        self.depth_source_label.setText(f"DEPTH: {status.get('active_depth', 'None')}")

    def on_spoofing_alert(self, description):
        """Handle GPS spoofing alert from detector."""
        self.log_message(f"*** {description} ***")
        self.spoofing_label.setText("** GPS SPOOFING ALERT **")
        self.spoofing_label.setVisible(True)
        self.status_bar.showMessage(description, 10000)
        self.alarm_manager.trigger('gps_spoofing', description)

    # ------------------------------------------------------------------
    # Slots: radar data
    # ------------------------------------------------------------------

    def on_radar_data_updated(self, radar_data):
        self.ppi_display.update_radar_data(radar_data)

        self.radar_status_label.setText("Status: OPERATING")
        self.radar_status_label.setStyleSheet(
            f"color: {self._current_theme.ui_text_primary.name()}; "
            "font-family: Consolas; font-size: 11px;"
        )

        if radar_data.get('targets'):
            self.track_manager.update_radar_tracks(radar_data['targets'])

        # Log guard zone intrusions
        for alarm in self.track_manager.guard_zone_manager.get_recent_alarms(3):
            ts, zone, tid, event = alarm
            self.log_message(f"GUARD ZONE {event.upper()}: {tid} in {zone}")

    # ------------------------------------------------------------------
    # Camera slots & helpers
    # ------------------------------------------------------------------

    def on_camera_azimuth_updated(self, azimuth: float):
        """Receive camera azimuth from CameraController and update PPI line."""
        mode = self.camera_controller.config.get('bearing_mode', 'relative')
        if mode == 'relative':
            # Camera reports relative-to-bow; convert to true for the PPI
            own_hdg = self.nmea_parser.heading or 0.0
            azimuth = (azimuth + own_hdg) % 360.0
        self.ppi_display.set_camera_azimuth(azimuth)

    def _slew_camera_to_target(self, target_data: dict):
        """Calculate bearing to target and send slew command in configured mode."""
        own_lat = self.nmea_parser.latitude
        own_lon = self.nmea_parser.longitude
        tgt_lat = target_data.get('lat', own_lat)
        tgt_lon = target_data.get('lon', own_lon)

        true_brg = bearing_between(own_lat, own_lon, tgt_lat, tgt_lon)
        mode = self.camera_controller.config.get('bearing_mode', 'relative')
        if mode == 'relative':
            own_hdg = self.nmea_parser.heading or 0.0
            send_brg = (true_brg - own_hdg + 360.0) % 360.0
            suffix = '°R'
        else:
            send_brg = true_brg
            suffix = '°T'

        name = target_data.get('name') or str(target_data.get('id', '?'))
        self.log_message(
            f"CAM SLEW → {name}  BRG {send_brg:05.1f}{suffix}"
        )
        self.camera_controller.send_slew_command(send_brg)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        import logging
        self.log_message("SYSTEM SHUTDOWN INITIATED")

        # Stop update timer to prevent further display refreshes
        self.update_timer.stop()

        # Silence alarms before shutdown
        self.alarm_manager.silence()

        # Stop radar, NMEA, camera, and ADS-B
        self.radar_interface.stop()
        self.nmea_parser.stop_listening()
        self.camera_controller.stop_listening()
        self.adsb_receiver.stop_listening()

        self.log_message("System stopped")

        # Flush all logging handlers
        for handler in logging.root.handlers:
            handler.flush()

        event.accept()
