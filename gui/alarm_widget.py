"""
Alarm Widget for Marine Radar GUI.

Displays the 5 most recent alarms in a compact strip below the PPI.
Each alarm row shows:
  - Flashing indicator dot (active + unacknowledged)
  - Timestamp
  - Short description
  - Individual ACK (silence) button

New alarms sound and flash until the operator presses ACK on that row.
If a condition clears and later re-occurs, a new alarm entry is created
so it sounds and flashes again.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton)
from PyQt6.QtCore import Qt, QTimer
from core.alarm_manager import AlarmManager, ALARM_DEFS

# Per-type indicator colors
_ALARM_COLORS = {
    'cpa_critical': '#FF0000',
    'cpa_warning':  '#FF8C00',
    'guard_zone':   '#FFD700',
    'gps_spoofing': '#FF00FF',
    'sensor_loss':  '#00BFFF',
    'radar_link':   '#00BFFF',
    'radar_video':  '#00BFFF',
}


class _AlarmRow(QWidget):
    """Single alarm row inside the alarm widget."""

    def __init__(self, alarm_manager: AlarmManager, parent=None):
        super().__init__(parent)
        self._alarm_manager = alarm_manager
        self._alarm_type = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)

        # Indicator dot
        self._indicator = QLabel("\u25cf")  # filled circle
        self._indicator.setFixedWidth(14)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._indicator.setStyleSheet("font-size: 12px; color: #FF0000;")
        layout.addWidget(self._indicator)

        # Timestamp
        self._time_label = QLabel("")
        self._time_label.setFixedWidth(56)
        self._time_label.setStyleSheet(
            "color: #AAAAAA; font-family: Consolas; font-size: 9px;"
        )
        layout.addWidget(self._time_label)

        # Description
        self._desc_label = QLabel("")
        self._desc_label.setStyleSheet(
            "color: #FFFFFF; font-family: Consolas; font-size: 9px;"
        )
        layout.addWidget(self._desc_label, stretch=1)

        # ACK (silence) button
        self._ack_btn = QPushButton("ACK")
        self._ack_btn.setFixedSize(38, 18)
        self._ack_btn.setStyleSheet(
            "QPushButton { background-color: #440000; color: #FF4444; "
            "border: 1px solid #AA0000; font-family: Consolas; font-size: 8px; }"
            "QPushButton:hover { background-color: #660000; }"
            "QPushButton:disabled { background-color: #222222; color: #555555; "
            "border: 1px solid #444444; }"
        )
        self._ack_btn.clicked.connect(self._on_ack)
        layout.addWidget(self._ack_btn)

        self.setVisible(False)

    # ---- public ----

    def update_from_entry(self, entry):
        """Populate this row from an AlarmEntry."""
        self._alarm_type = entry.alarm_type
        color = _ALARM_COLORS.get(entry.alarm_type, '#FFFFFF')
        label = ALARM_DEFS.get(entry.alarm_type, {}).get(
            'label', entry.alarm_type.upper())

        self._time_label.setText(entry.time_str)

        if entry.active and not entry.silenced:
            # Active, unacknowledged — bold, colored
            self._desc_label.setText(f"{label} \u2014 {entry.description}")
            self._desc_label.setStyleSheet(
                f"color: {color}; font-family: Consolas; "
                "font-size: 9px; font-weight: bold;"
            )
            self._indicator.setStyleSheet(
                f"font-size: 12px; color: {color};"
            )
            self._ack_btn.setText("ACK")
            self._ack_btn.setEnabled(True)

        elif entry.active and entry.silenced:
            # Active but acknowledged — dimmed
            self._desc_label.setText(f"{label} \u2014 {entry.description}")
            self._desc_label.setStyleSheet(
                "color: #888888; font-family: Consolas; font-size: 9px;"
            )
            self._indicator.setStyleSheet(
                "font-size: 12px; color: #888888;"
            )
            self._ack_btn.setText("\u2713")   # check mark
            self._ack_btn.setEnabled(False)

        else:
            # Inactive (condition cleared)
            self._desc_label.setText(f"{label} \u2014 cleared")
            self._desc_label.setStyleSheet(
                "color: #555555; font-family: Consolas; font-size: 9px;"
            )
            self._indicator.setStyleSheet(
                "font-size: 12px; color: #555555;"
            )
            self._ack_btn.setText("\u2014")   # em-dash
            self._ack_btn.setEnabled(False)

        self.setVisible(True)

    def set_flash_visible(self, visible: bool):
        """Toggle indicator visibility for flash animation."""
        self._indicator.setVisible(visible)

    # ---- private ----

    def _on_ack(self):
        """Silence this specific alarm type."""
        if self._alarm_type:
            self._alarm_manager.silence_type(self._alarm_type)


class AlarmWidget(QWidget):
    """Compact alarm display strip showing the 5 most recent alarms.

    Placed just below the PPI display in the main window.
    """

    def __init__(self, alarm_manager: AlarmManager, parent=None):
        super().__init__(parent)
        self._alarm_manager = alarm_manager
        self._flash_on = True
        self.setMaximumHeight(130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(0)

        # Header
        self._header = QLabel("ALARMS")
        self._header.setStyleSheet(
            "color: #FF4444; font-family: Consolas; font-size: 10px; "
            "font-weight: bold;"
        )
        layout.addWidget(self._header)

        # 5 alarm rows
        self._rows: list[_AlarmRow] = []
        for _ in range(5):
            row = _AlarmRow(alarm_manager)
            layout.addWidget(row)
            self._rows.append(row)

        layout.addStretch()

        # Flash timer — 500 ms blink for active unacknowledged alarms
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._on_flash_tick)
        self._flash_timer.start(500)

        # Refresh timer — poll alarm manager state
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(250)

    # ---- theme ----

    def apply_theme(self, bg: str, text: str, border: str, critical: str):
        """Apply current theme colours."""
        self.setStyleSheet(
            f"QWidget {{ background-color: {bg}; "
            f"border-top: 1px solid {border}; }}"
        )
        self._header.setStyleSheet(
            f"color: {critical}; font-family: Consolas; font-size: 10px; "
            "font-weight: bold; border: none;"
        )

    # ---- internal ----

    def _refresh(self):
        """Pull latest entries from alarm manager and update rows."""
        entries = self._alarm_manager.get_recent_entries(5)
        for i, row in enumerate(self._rows):
            if i < len(entries):
                row.update_from_entry(entries[i])
            else:
                row.setVisible(False)

    def _on_flash_tick(self):
        """Toggle indicator dot for active unacknowledged alarms."""
        self._flash_on = not self._flash_on
        entries = self._alarm_manager.get_recent_entries(5)
        for i, row in enumerate(self._rows):
            if i < len(entries):
                entry = entries[i]
                if entry.active and not entry.silenced:
                    row.set_flash_visible(self._flash_on)
                else:
                    row.set_flash_visible(True)
