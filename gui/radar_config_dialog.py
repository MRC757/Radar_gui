"""
Radar Configuration Dialog
Allows adding, editing, and removing radar units.
Each radar has a name, IP address, and port for radar SDK connectivity.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QSpinBox,
                             QTableWidget, QHeaderView, QCheckBox,
                             QMessageBox, QWidget)
from PyQt6.QtCore import Qt
import json
import os

logger = logging.getLogger(__name__)

CONFIG_FILE = 'radar_config.json'


def load_radar_config():
    """Load radar configuration from file, returning list of radar dicts."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            return config.get('radars', [])
        except Exception as e:
            logger.error("Error loading radar config: %s", e)
    # Default: one simulator entry
    return [{'name': 'Simulator', 'ip': '127.0.0.1', 'port': 10001, 'enabled': True}]


class RadarConfigDialog(QDialog):
    """Dialog for configuring radar units"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Radar Configuration")
        self.setModal(True)
        self.setMinimumSize(650, 400)

        self._setup_ui()
        self._load_radars()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info
        info = QLabel(
            "Configure radar units. Each radar requires a name and network "
            "address for radar SDK connectivity. The active radar is selected "
            "from the Radar dropdown on the main window."
        )
        info.setWordWrap(True)
        info.setObjectName("info_label")
        layout.addWidget(info)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Name", "IP Address", "Port", "Enabled", "Actions"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        # Add button
        add_btn = QPushButton("Add Radar")
        add_btn.clicked.connect(self._add_empty_radar)
        layout.addWidget(add_btn)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _insert_row(self, name, ip, port, enabled):
        row = self.table.rowCount()
        self.table.insertRow(row)

        name_edit = QLineEdit(name)
        self.table.setCellWidget(row, 0, name_edit)

        ip_edit = QLineEdit(ip)
        self.table.setCellWidget(row, 1, ip_edit)

        port_spin = QSpinBox()
        port_spin.setRange(1, 65535)
        port_spin.setValue(port)
        self.table.setCellWidget(row, 2, port_spin)

        enabled_cb = QCheckBox()
        enabled_cb.setChecked(enabled)
        cb_container = QWidget()
        cb_layout = QHBoxLayout(cb_container)
        cb_layout.addWidget(enabled_cb)
        cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 3, cb_container)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(lambda _, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 4, delete_btn)

    def _add_empty_radar(self):
        count = self.table.rowCount() + 1
        self._insert_row(f"Radar {count}", "192.168.1.100", 10001, True)

    def _delete_row(self, row):
        if row < self.table.rowCount():
            self.table.removeRow(row)
            # Rebind delete buttons after row shift
            for r in range(self.table.rowCount()):
                btn = QPushButton("Delete")
                btn.clicked.connect(lambda _, r2=r: self._delete_row(r2))
                self.table.setCellWidget(r, 4, btn)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_radars(self):
        """Populate table from config file."""
        self.table.setRowCount(0)
        for radar in load_radar_config():
            self._insert_row(
                radar.get('name', ''),
                radar.get('ip', '192.168.1.100'),
                radar.get('port', 10001),
                radar.get('enabled', True),
            )

    def _save_and_close(self):
        """Validate, save config, and close."""
        radars = []
        for row in range(self.table.rowCount()):
            name = self.table.cellWidget(row, 0).text().strip()
            if not name:
                QMessageBox.warning(self, "Validation",
                                    f"Row {row + 1}: Name cannot be empty.")
                return

            ip = self.table.cellWidget(row, 1).text().strip()
            if not ip:
                QMessageBox.warning(self, "Validation",
                                    f"Row {row + 1}: IP address cannot be empty.")
                return

            port = self.table.cellWidget(row, 2).value()

            cb_container = self.table.cellWidget(row, 3)
            enabled = cb_container.findChild(QCheckBox).isChecked()

            radars.append({
                'name': name,
                'ip': ip,
                'port': port,
                'enabled': enabled,
            })

        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({'radars': radars}, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save configuration: {e}")
            return

        self.accept()
