"""
Built-In Test (BIT) Window
Displays radar system fault status: transmitter, motor, temperature, etc.
Typical of marine radar BIT panels per IEC 62388.
"""

from datetime import datetime

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QLabel, QPushButton, QGridLayout, QTextEdit)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class _FaultIndicator(QLabel):
    """Single fault status indicator with OK / FAULT states."""

    def __init__(self, label_text, parent=None):
        super().__init__(parent)
        self._label = label_text
        self._fault = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.setMinimumHeight(36)
        self._refresh()

    @property
    def is_fault(self):
        return self._fault

    def set_fault(self, fault: bool):
        if fault != self._fault:
            self._fault = fault
            self._refresh()

    def _refresh(self):
        if self._fault:
            self.setText(f"{self._label}:  FAULT")
            self.setStyleSheet(
                "background-color: #880000; color: #FF4444; "
                "border: 2px solid #FF0000; padding: 4px; font-family: Consolas;"
            )
        else:
            self.setText(f"{self._label}:  OK")
            self.setStyleSheet(
                "background-color: #003300; color: #00FF00; "
                "border: 2px solid #00AA00; padding: 4px; font-family: Consolas;"
            )


class BITWindow(QDialog):
    """Built-In Test window displaying radar subsystem fault status."""

    # (internal key, display label)
    _FAULT_DEFS = [
        ("transmitter",    "TRANSMITTER"),
        ("motor",          "ANTENNA MOTOR"),
        ("over_temp",      "OVER TEMPERATURE"),
        ("receiver",       "RECEIVER"),
        ("power_supply",   "POWER SUPPLY"),
        ("signal_proc",    "SIGNAL PROCESSOR"),
        ("heading_input",  "HEADING INPUT"),
        ("gps_input",      "GPS INPUT"),
        ("gps_spoofing",   "GPS SPOOFING"),
        ("ais_input",      "AIS INPUT"),
        ("display",        "DISPLAY UNIT"),
    ]

    def __init__(self, radar_interface=None, nmea_parser=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Built-In Test (BIT)")
        self.setMinimumSize(520, 560)

        self._radar = radar_interface
        self._nmea = nmea_parser

        # Fault state dict
        self._faults = {key: False for key, _ in self._FAULT_DEFS}

        self._indicators = {}
        self._setup_ui()

        # Periodic poll (1 Hz)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start(1000)

        # Initial poll
        self._poll_status()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("RADAR SYSTEM BUILT-IN TEST")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        title.setStyleSheet("padding: 6px;")
        layout.addWidget(title)

        # Summary
        self._summary_label = QLabel("STATUS: ALL SYSTEMS OK")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self._summary_label.setMinimumHeight(32)
        layout.addWidget(self._summary_label)

        # Fault indicators grid
        fault_group = QGroupBox("Subsystem Status")
        fault_group.setObjectName("subsystem_group")
        grid = QGridLayout()
        grid.setSpacing(6)

        for i, (key, label) in enumerate(self._FAULT_DEFS):
            indicator = _FaultIndicator(label)
            row, col = divmod(i, 2)
            grid.addWidget(indicator, row, col)
            self._indicators[key] = indicator

        fault_group.setLayout(grid)
        layout.addWidget(fault_group)

        # Fault log
        log_group = QGroupBox("Fault Log")
        log_group.setObjectName("log_group")
        log_layout = QVBoxLayout()
        self._log_display = QTextEdit()
        self._log_display.setReadOnly(True)
        self._log_display.setMaximumHeight(140)
        self._log_display.setObjectName("fault_log")
        log_layout.addWidget(self._log_display)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Buttons
        btn_layout = QHBoxLayout()

        run_btn = QPushButton("Run Full Test")
        run_btn.clicked.connect(self._run_full_test)
        btn_layout.addWidget(run_btn)

        clear_btn = QPushButton("Clear Faults")
        clear_btn.clicked.connect(self._clear_faults)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        # Theme is applied externally via dialog_stylesheet()

    # ------------------------------------------------------------------
    # Fault management
    # ------------------------------------------------------------------

    def set_fault(self, key: str, fault: bool):
        """Set fault state for a subsystem by key."""
        if key not in self._faults:
            return
        prev = self._faults[key]
        self._faults[key] = fault
        self._indicators[key].set_fault(fault)

        if fault and not prev:
            label = dict(self._FAULT_DEFS).get(key, key)
            self._log(f"FAULT DETECTED: {label}")
        elif not fault and prev:
            label = dict(self._FAULT_DEFS).get(key, key)
            self._log(f"FAULT CLEARED:  {label}")

        self._update_summary()

    def _update_summary(self):
        active = [dict(self._FAULT_DEFS)[k] for k, v in self._faults.items() if v]
        if active:
            self._summary_label.setText(
                f"STATUS: {len(active)} FAULT(S) ACTIVE"
            )
            self._summary_label.setStyleSheet(
                "color: #FF0000; background-color: #440000; "
                "border: 2px solid #FF0000; padding: 4px;"
            )
        else:
            self._summary_label.setText("STATUS: ALL SYSTEMS OK")
            self._summary_label.setStyleSheet(
                "color: #00FF00; background-color: #003300; "
                "border: 2px solid #00AA00; padding: 4px;"
            )

    def _log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_display.append(f"[{ts}] {message}")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll_status(self):
        """Poll live subsystem status from radar interface and NMEA parser."""
        # Radar interface status
        if self._radar is not None:
            status = {}
            if hasattr(self._radar, 'get_status'):
                status = self._radar.get_status()
            self.set_fault("transmitter",  status.get("transmitter_fault", False))
            self.set_fault("motor",        status.get("motor_fault", False))
            self.set_fault("over_temp",    status.get("over_temp", False))
            self.set_fault("receiver",     status.get("receiver_fault", False))
            self.set_fault("power_supply", status.get("power_supply_fault", False))
            self.set_fault("signal_proc",  status.get("signal_proc_fault", False))
            self.set_fault("display",      status.get("display_fault", False))

        # NMEA input status
        if self._nmea is not None:
            if hasattr(self._nmea, 'get_source_status'):
                nmea_status = self._nmea.get_source_status()
            else:
                nmea_status = {}
            self.set_fault("heading_input",
                           nmea_status.get("active_heading") in (None, "None", ""))
            self.set_fault("gps_input",
                           nmea_status.get("active_gps") in (None, "None", ""))
            # AIS is optional, don't flag as fault unless explicitly failing
            self.set_fault("ais_input",
                           nmea_status.get("ais_fault", False))

            # GPS spoofing detection
            if hasattr(self._nmea, 'spoofing_detector'):
                self.set_fault("gps_spoofing",
                               self._nmea.spoofing_detector.is_alert)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _run_full_test(self):
        """Run a full built-in test sequence."""
        self._log("--- FULL BIT INITIATED ---")
        self._poll_status()
        active = [dict(self._FAULT_DEFS)[k] for k, v in self._faults.items() if v]
        if active:
            for name in active:
                self._log(f"  FAIL: {name}")
            self._log(f"BIT RESULT: {len(active)} FAULT(S)")
        else:
            self._log("BIT RESULT: ALL TESTS PASSED")

    def _clear_faults(self):
        """Clear all latched fault indicators."""
        for key in self._faults:
            self.set_fault(key, False)
        self._log("All faults cleared by operator")

    def closeEvent(self, event):
        self._poll_timer.stop()
        super().closeEvent(event)
