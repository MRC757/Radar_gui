"""
Built-In Test (BIT) Window
Displays radar system fault status: transmitter, motor, temperature, etc.
Typical of marine radar BIT panels per IEC 62388.

Software self-tests (functional without radar SDK):
  - CONFIG FILES  — verifies nmea_config.json and ais_encrypt_config.json are
                    present and contain valid JSON
  - ALARM LOG     — verifies the alarm log file is writable
  - GPS INPUT     — live NMEA parser source status
  - HEADING INPUT — live NMEA parser source status
  - GPS SPOOFING  — live spoofing detector state
"""

import json
from datetime import datetime
from pathlib import Path

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
        ("radar_link",     "RADAR LINK"),
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
        ("config_files",   "CONFIG FILES"),
        ("alarm_log",      "ALARM LOG"),
    ]

    # Config files required for normal operation
    _CONFIG_FILES = [
        Path("config/nmea_config.json"),
        Path("config/ais_encrypt_config.json"),
    ]

    def __init__(self, radar_interface=None, nmea_parser=None,
                 alarm_manager=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Built-In Test (BIT)")
        self.setMinimumSize(520, 600)

        self._radar = radar_interface
        self._nmea = nmea_parser
        self._alarm_manager = alarm_manager

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

        audio_btn = QPushButton("Test Alarm Audio")
        audio_btn.clicked.connect(self._test_alarm_audio)
        btn_layout.addWidget(audio_btn)

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
        status = {}
        if self._radar is None:
            self.set_fault("radar_link", True)
        else:
            radar_status = self._radar.get_status()      # core.radar.RadarStatus
            status = radar_status.fault_dict()
            self.set_fault("radar_link", not radar_status.connected)
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

        # Software self-tests (no radar SDK required)
        self.set_fault("config_files", not self._check_config_files())
        self.set_fault("alarm_log",    not self._check_alarm_log())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _run_full_test(self):
        """Run a full built-in test sequence."""
        self._log("--- FULL BIT INITIATED ---")

        # Radar hardware details (from the SDK driver)
        if self._radar is not None:
            st = self._radar.get_status()
            caps = self._radar.get_capabilities()
            self._log(f"  RADAR: {caps.model}  link={'UP' if st.connected else 'DOWN'}  "
                      f"{'TX' if st.transmitting else 'STBY'}")
            if st.firmware_version or st.serial_number:
                self._log(f"  FW {st.firmware_version or '?'}  S/N {st.serial_number or '?'}")
            if st.operating_hours is not None:
                self._log(f"  Hours: operating {st.operating_hours:.0f}  "
                          f"transmit {st.transmit_hours or 0:.0f}")
            if st.temperature_c is not None:
                self._log(f"  Temperature: {st.temperature_c:.1f} C")
        else:
            self._log("  FAIL: No radar driver active")

        # Software self-tests with detail
        cfg_ok = self._check_config_files()
        if cfg_ok:
            self._log("  PASS: Config files present and valid JSON")
        else:
            self._log("  FAIL: One or more config files missing or invalid")

        log_ok = self._check_alarm_log()
        if log_ok:
            self._log("  PASS: Alarm log is writable")
        else:
            self._log("  FAIL: Alarm log directory/file not writable")

        if self._nmea is not None and hasattr(self._nmea, 'get_source_status'):
            nmea_status = self._nmea.get_source_status()
            gps_src = nmea_status.get("active_gps", "")
            hdg_src = nmea_status.get("active_heading", "")
            if gps_src and gps_src not in ("None", ""):
                self._log(f"  PASS: GPS source active ({gps_src})")
            else:
                self._log("  FAIL: No active GPS source")
            if hdg_src and hdg_src not in ("None", ""):
                self._log(f"  PASS: Heading source active ({hdg_src})")
            else:
                self._log("  FAIL: No active heading source")

        # Update all indicators
        self._poll_status()

        active = [dict(self._FAULT_DEFS)[k] for k, v in self._faults.items() if v]
        if active:
            for name in active:
                self._log(f"  FAULT: {name}")
            self._log(f"BIT RESULT: {len(active)} FAULT(S)")
        else:
            self._log("BIT RESULT: ALL TESTS PASSED")

    def _check_config_files(self) -> bool:
        """Return True if all required config files exist and contain valid JSON."""
        for path in self._CONFIG_FILES:
            if not path.exists():
                return False
            try:
                with open(path, encoding='utf-8') as f:
                    json.load(f)
            except Exception:
                return False
        return True

    def _check_alarm_log(self) -> bool:
        """Return True if the alarm log file/directory is writable."""
        log_path = Path("logs") / "alarm_log.txt"
        try:
            log_path.parent.mkdir(exist_ok=True)
            with open(log_path, 'a', encoding='utf-8'):
                pass
            return True
        except Exception:
            return False

    def _test_alarm_audio(self):
        """Play a test tone to verify audio output (bypasses silence/cooldown)."""
        self._log("Testing alarm audio...")
        if self._alarm_manager is not None:
            self._alarm_manager.play_test_tone('sensor_loss')
            self._log("  Test tone played. If no sound, check system audio output.")
        else:
            self._log("  No alarm manager available — audio test skipped.")

    def _clear_faults(self):
        """Clear all latched fault indicators."""
        for key in self._faults:
            self.set_fault(key, False)
        self._log("All faults cleared by operator")

    def closeEvent(self, event):
        self._poll_timer.stop()
        super().closeEvent(event)
