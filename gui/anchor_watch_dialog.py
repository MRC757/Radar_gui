"""
Anchor Watch Dialog
Monitors own-ship position against a fixed anchor point while at anchor.
The operator selects up to 3 stationary radar reference targets, sets a
swing radius, and activates continuous 1 Hz position monitoring.  When the
ship drifts outside the swing radius an audible alarm is triggered.

Public attributes read by PPIDisplayWidget for the overlay circle:
    active          bool   — True while watch is running
    anchor_lat      float  — anchor latitude (degrees)
    anchor_lon      float  — anchor longitude (degrees)
    swing_radius_nm float  — swing radius (nautical miles)
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QComboBox, QDoubleSpinBox, QLineEdit,
                             QPushButton, QGroupBox, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class AnchorWatchDialog(QDialog):
    """Non-modal Anchor Watch popup window."""

    def __init__(self, nmea_parser, track_manager, alarm_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anchor Watch")
        self.setMinimumSize(560, 520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)

        self._parser = nmea_parser
        self._track_manager = track_manager
        self._alarm_manager = alarm_manager

        # Public state read by PPI overlay
        self.active = False
        self.anchor_lat: float = 0.0
        self.anchor_lon: float = 0.0
        self.swing_radius_nm: float = 0.10

        # Internal
        self._refs = [None, None, None]   # each: {id, lat, lon, brg, rng}

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._check_position)

        self._setup_ui()
        self._populate_combos()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- Reference Targets ---
        ref_group = QGroupBox("Reference Targets (select stationary radar tracks)")
        ref_layout = QGridLayout(ref_group)
        ref_layout.setColumnStretch(1, 1)

        self._ref_combos: list[QComboBox] = []
        self._ref_labels: list[QLabel] = []

        for i in range(3):
            lbl = QLabel(f"REF {i + 1}:")
            lbl.setFixedWidth(48)
            combo = QComboBox()
            combo.setMinimumWidth(260)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            status_lbl = QLabel("—")
            status_lbl.setFixedWidth(180)
            ref_layout.addWidget(lbl, i, 0)
            ref_layout.addWidget(combo, i, 1)
            ref_layout.addWidget(status_lbl, i, 2)
            self._ref_combos.append(combo)
            self._ref_labels.append(status_lbl)

        main_layout.addWidget(ref_group)

        # --- Anchor Position ---
        pos_group = QGroupBox("Anchor Position")
        pos_layout = QGridLayout(pos_group)

        pos_layout.addWidget(QLabel("Anchor Lat:"), 0, 0)
        self._anc_lat_edit = QLineEdit()
        self._anc_lat_edit.setReadOnly(True)
        self._anc_lat_edit.setPlaceholderText("(activate to set)")
        pos_layout.addWidget(self._anc_lat_edit, 0, 1)

        pos_layout.addWidget(QLabel("Anchor Lon:"), 0, 2)
        self._anc_lon_edit = QLineEdit()
        self._anc_lon_edit.setReadOnly(True)
        self._anc_lon_edit.setPlaceholderText("(activate to set)")
        pos_layout.addWidget(self._anc_lon_edit, 0, 3)

        pos_layout.addWidget(QLabel("Drift from Anchor:"), 1, 0)
        self._drift_label = QLabel("—")
        bold = QFont()
        bold.setBold(True)
        self._drift_label.setFont(bold)
        pos_layout.addWidget(self._drift_label, 1, 1, 1, 3)

        main_layout.addWidget(pos_group)

        # --- Swing Radius ---
        radius_group = QGroupBox("Swing Radius")
        radius_layout = QHBoxLayout(radius_group)
        radius_layout.addWidget(QLabel("Swing Radius (NM):"))
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(0.01, 2.00)
        self._radius_spin.setSingleStep(0.01)
        self._radius_spin.setDecimals(2)
        self._radius_spin.setValue(0.10)
        self._radius_spin.valueChanged.connect(self._on_radius_changed)
        radius_layout.addWidget(self._radius_spin)
        radius_layout.addStretch()
        main_layout.addWidget(radius_group)

        # --- Status ---
        status_group = QGroupBox("Watch Status")
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel("INACTIVE")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(18)
        status_font.setBold(True)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet("color: #888888;")
        status_layout.addWidget(self._status_label)
        main_layout.addWidget(status_group)

        # --- Buttons ---
        btn_layout = QHBoxLayout()

        self._activate_btn = QPushButton("Activate Watch")
        self._activate_btn.clicked.connect(self._activate)
        btn_layout.addWidget(self._activate_btn)

        self._deactivate_btn = QPushButton("Deactivate")
        self._deactivate_btn.setEnabled(False)
        self._deactivate_btn.clicked.connect(self._deactivate)
        btn_layout.addWidget(self._deactivate_btn)

        refresh_btn = QPushButton("Refresh Targets")
        refresh_btn.clicked.connect(self._populate_combos)
        btn_layout.addWidget(refresh_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        main_layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Target combo population
    # ------------------------------------------------------------------

    def _populate_combos(self):
        """Fill all three combo boxes with current stationary radar tracks."""
        tracks = self._track_manager.get_radar_tracks()
        # Filter to likely-stationary tracks (speed < 1.0 kts) and sort nearest first
        stationary = [t for t in tracks if t.get('speed', 0.0) < 1.0]
        stationary.sort(key=lambda t: self._track_manager.calculate_distance(
            self._parser.latitude, self._parser.longitude,
            t.get('lat', 0.0), t.get('lon', 0.0)
        ))

        # Build items list
        items = [("(none)", None)]
        for t in stationary:
            tid = t.get('id', '?')
            brg = t.get('bearing', 0.0)
            rng = t.get('range', 0.0)
            label = f"{tid}  (BRG {brg:.0f}°  {rng:.1f} NM)"
            items.append((label, tid))

        for combo in self._ref_combos:
            current_data = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            restore_idx = 0
            for i, (label, data) in enumerate(items):
                combo.addItem(label, data)
                if data is not None and data == current_data:
                    restore_idx = i
            combo.setCurrentIndex(restore_idx)
            combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Activate / Deactivate
    # ------------------------------------------------------------------

    def _activate(self):
        """Lock anchor position, lock reference targets, start monitoring."""
        lat = self._parser.latitude
        lon = self._parser.longitude
        if lat == 0.0 and lon == 0.0:
            self._set_status("NO GPS POSITION", "#ff4444")
            return

        self.anchor_lat = lat
        self.anchor_lon = lon
        self._anc_lat_edit.setText(f"{lat:.6f}")
        self._anc_lon_edit.setText(f"{lon:.6f}")

        # Lock reference targets
        tracks = {t['id']: t for t in self._track_manager.get_radar_tracks()}
        self._refs = [None, None, None]
        for i, combo in enumerate(self._ref_combos):
            tid = combo.currentData()
            if tid and tid in tracks:
                t = tracks[tid]
                brg = t.get('bearing', 0.0)
                rng = t.get('range', 0.0)
                self._refs[i] = {
                    'id': tid,
                    'lat': t.get('lat', 0.0),
                    'lon': t.get('lon', 0.0),
                    'brg': brg,
                    'rng': rng,
                }
                self._ref_labels[i].setText(f"BRG {brg:.0f}°  {rng:.2f} NM")

        self.swing_radius_nm = self._radius_spin.value()
        self.active = True
        self._activate_btn.setEnabled(False)
        self._deactivate_btn.setEnabled(True)
        self._radius_spin.setEnabled(False)
        self._set_status("WATCHING", "#00cc44")
        self._timer.start()

    def _deactivate(self):
        """Stop monitoring, clear alarm, reset state."""
        self._timer.stop()
        self.active = False
        self._alarm_manager.clear('anchor_drag')
        self._alarm_manager.silence_type('anchor_drag')
        self._anc_lat_edit.clear()
        self._anc_lon_edit.clear()
        self._drift_label.setText("—")
        for i in range(3):
            self._refs[i] = None
            self._ref_labels[i].setText("—")
        self._activate_btn.setEnabled(True)
        self._deactivate_btn.setEnabled(False)
        self._radius_spin.setEnabled(True)
        self._set_status("INACTIVE", "#888888")

    # ------------------------------------------------------------------
    # 1 Hz position check
    # ------------------------------------------------------------------

    def _check_position(self):
        """Called every second while watch is active."""
        if not self.active:
            return

        # With no live GPS the position is frozen: say so, and leave any
        # existing drag alarm as it is rather than clearing it on stale data.
        gps = getattr(self._parser, 'active_gps_source', None)
        if gps is None or not gps.is_active():
            self._set_status("\u26a0 NO GPS \u2014 NOT MONITORING", "#ffaa00")
            return

        lat = self._parser.latitude
        lon = self._parser.longitude
        drift_nm = self._track_manager.calculate_distance(
            self.anchor_lat, self.anchor_lon, lat, lon
        )

        # Colour-code drift label
        frac = drift_nm / self.swing_radius_nm if self.swing_radius_nm > 0 else 0
        if frac < 0.5:
            colour = "#00cc44"   # green
        elif frac < 1.0:
            colour = "#ffaa00"   # amber
        else:
            colour = "#ff4444"   # red
        self._drift_label.setText(f"{drift_nm:.3f} NM")
        self._drift_label.setStyleSheet(f"color: {colour};")

        # Update reference target bearings/ranges from current position
        tracks = {t['id']: t for t in self._track_manager.get_radar_tracks()}
        for i, ref in enumerate(self._refs):
            if ref is None:
                continue
            tid = ref['id']
            if tid in tracks:
                t = tracks[tid]
                brg = t.get('bearing', 0.0)
                rng = t.get('range', 0.0)
                self._ref_labels[i].setText(f"BRG {brg:.0f}°  {rng:.2f} NM")

        # Check drag condition
        if drift_nm > self.swing_radius_nm:
            self._alarm_manager.trigger(
                'anchor_drag',
                f"Ship dragged {drift_nm:.3f} NM from anchor"
            )
            self._set_status("\u26a0 ANCHOR DRAG", "#ff4444")
        else:
            self._alarm_manager.clear('anchor_drag')
            self._set_status("WATCHING", "#00cc44")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_radius_changed(self, value):
        self.swing_radius_nm = value

    def _set_status(self, text: str, colour: str):
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {colour}; font-weight: bold; font-size: 18pt;"
        )

    def closeEvent(self, event):
        """Deactivate watch when dialog is closed."""
        if self.active:
            self._deactivate()
        super().closeEvent(event)
