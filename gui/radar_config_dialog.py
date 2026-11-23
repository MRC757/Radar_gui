"""
Radar Configuration Dialog
Allows adding, editing, and removing radar units.

Each radar entry selects a driver (see core/radar/factory.py):
  - "mock"    built-in simulator
  - "furuno"  Furuno Sensor SDK (needs the SDK DLL — see README)

Advanced keys that have no column here (dll_dirs, calling_convention,
symbol_map, bearing_is_true ...) can be edited directly in
radar_config.json and are preserved when this dialog saves.
"""

import json
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSpinBox, QTableWidget,
                             QVBoxLayout, QWidget)

from core.radar.factory import available_drivers
from core.radar.furuno.models import SUPPORTED_MODELS as FURUNO_MODELS

logger = logging.getLogger(__name__)

CONFIG_FILE = 'radar_config.json'

DEFAULT_RADARS = [
    {'name': 'Simulator', 'driver': 'mock', 'ip': '127.0.0.1', 'port': 10001,
     'enabled': True},
]

# Columns
COL_NAME, COL_DRIVER, COL_MODEL, COL_IP, COL_PORT, COL_DLL, COL_ENABLED, COL_ACTIONS = range(8)
MODELS_BY_DRIVER = {'mock': ['Simulator'], 'furuno': FURUNO_MODELS}


def load_radar_config():
    """Load radar configuration from file, returning list of radar dicts."""
    radars = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                radars = json.load(f).get('radars', [])
        except Exception as e:
            logger.error("Error loading radar config: %s", e)
    if not radars:
        radars = [dict(r) for r in DEFAULT_RADARS]
    for r in radars:
        r.setdefault('driver', 'mock')   # pre-driver config files were all simulator
    return radars


class RadarConfigDialog(QDialog):
    """Dialog for configuring radar units"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Radar Configuration")
        self.setModal(True)
        self.setMinimumSize(1000, 420)
        self._row_extras = []     # per-row dict of keys not shown in the table

        self._setup_ui()
        self._load_radars()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Configure radar units. 'Driver' selects the radar SDK integration "
            "(mock = simulator, furuno = Furuno Sensor SDK). SDK drivers need the "
            "path to the vendor DLL — see README 'Furuno SDK DLLs'. The active "
            "radar is selected from the Radar dropdown on the main window."
        )
        info.setWordWrap(True)
        info.setObjectName("info_label")
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Name", "Driver", "Model", "IP Address", "Port", "SDK DLL Path",
            "Enabled", "Actions"
        ])
        header = self.table.horizontalHeader()
        for col in range(8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_DLL, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        add_btn = QPushButton("Add Radar")
        add_btn.clicked.connect(self._add_empty_radar)
        layout.addWidget(add_btn)

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

    def _insert_row(self, radar):
        row = self.table.rowCount()
        self.table.insertRow(row)

        shown = {'name', 'driver', 'model', 'ip', 'port', 'dll_path', 'enabled'}
        self._row_extras.append({k: v for k, v in radar.items() if k not in shown})

        self.table.setCellWidget(row, COL_NAME, QLineEdit(radar.get('name', '')))

        driver_combo = QComboBox()
        driver_combo.addItems(available_drivers())
        driver_combo.setCurrentText(radar.get('driver', 'mock'))
        self.table.setCellWidget(row, COL_DRIVER, driver_combo)

        model_combo = QComboBox()
        model_combo.setEditable(True)
        self.table.setCellWidget(row, COL_MODEL, model_combo)
        self._fill_models(model_combo, driver_combo.currentText(), radar.get('model', ''))

        self.table.setCellWidget(row, COL_IP, QLineEdit(radar.get('ip', '192.168.1.100')))

        port_spin = QSpinBox()
        port_spin.setRange(1, 65535)
        port_spin.setValue(int(radar.get('port', 10001)))
        self.table.setCellWidget(row, COL_PORT, port_spin)

        dll_widget = QWidget()
        dll_layout = QHBoxLayout(dll_widget)
        dll_layout.setContentsMargins(0, 0, 0, 0)
        dll_edit = QLineEdit(radar.get('dll_path', ''))
        dll_edit.setObjectName('dll_edit')
        dll_edit.setPlaceholderText("not needed for mock")
        browse = QPushButton("...")
        browse.setFixedWidth(28)
        browse.clicked.connect(lambda _, e=dll_edit: self._browse_dll(e))
        dll_layout.addWidget(dll_edit)
        dll_layout.addWidget(browse)
        self.table.setCellWidget(row, COL_DLL, dll_widget)

        driver_combo.currentTextChanged.connect(
            lambda d, m=model_combo, w=dll_widget: self._on_driver_changed(d, m, w))
        dll_widget.setEnabled(driver_combo.currentText() != 'mock')

        enabled_cb = QCheckBox()
        enabled_cb.setChecked(bool(radar.get('enabled', True)))
        cb_container = QWidget()
        cb_layout = QHBoxLayout(cb_container)
        cb_layout.addWidget(enabled_cb)
        cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, COL_ENABLED, cb_container)

        self._set_delete_button(row)

    def _set_delete_button(self, row):
        btn = QPushButton("Delete")
        btn.clicked.connect(lambda _, r=row: self._delete_row(r))
        self.table.setCellWidget(row, COL_ACTIONS, btn)

    @staticmethod
    def _fill_models(combo, driver, current):
        combo.clear()
        combo.addItems(MODELS_BY_DRIVER.get(driver, []))
        if current:
            combo.setCurrentText(current)

    def _on_driver_changed(self, driver, model_combo, dll_widget):
        self._fill_models(model_combo, driver, '')
        dll_widget.setEnabled(driver != 'mock')

    def _browse_dll(self, edit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select radar SDK DLL", os.path.dirname(edit.text()) or '',
            "DLL files (*.dll);;Shared libraries (*.so *.dylib);;All files (*)")
        if path:
            edit.setText(path)

    def _add_empty_radar(self):
        count = self.table.rowCount() + 1
        self._insert_row({'name': f"Radar {count}", 'driver': 'furuno',
                          'model': 'DRS4D-NXT', 'ip': '192.168.1.100',
                          'port': 10001, 'enabled': True})

    def _delete_row(self, row):
        if row < self.table.rowCount():
            self.table.removeRow(row)
            del self._row_extras[row]
            for r in range(self.table.rowCount()):
                self._set_delete_button(r)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_radars(self):
        self.table.setRowCount(0)
        self._row_extras = []
        for radar in load_radar_config():
            self._insert_row(radar)

    def _save_and_close(self):
        radars = []
        for row in range(self.table.rowCount()):
            name = self.table.cellWidget(row, COL_NAME).text().strip()
            if not name:
                QMessageBox.warning(self, "Validation", f"Row {row + 1}: Name cannot be empty.")
                return
            driver = self.table.cellWidget(row, COL_DRIVER).currentText()
            ip = self.table.cellWidget(row, COL_IP).text().strip()
            if not ip:
                QMessageBox.warning(self, "Validation",
                                    f"Row {row + 1}: IP address cannot be empty.")
                return
            dll_path = self.table.cellWidget(row, COL_DLL).findChild(QLineEdit, 'dll_edit').text().strip()
            if driver != 'mock' and not dll_path:
                QMessageBox.warning(self, "Validation",
                                    f"Row {row + 1}: driver '{driver}' needs the SDK DLL path.")
                return
            if dll_path and not os.path.isfile(dll_path):
                reply = QMessageBox.question(
                    self, "DLL not found",
                    f"Row {row + 1}: '{dll_path}' does not exist on this computer.\n"
                    "Save anyway?")
                if reply != QMessageBox.StandardButton.Yes:
                    return

            entry = dict(self._row_extras[row])
            entry.update({
                'name': name,
                'driver': driver,
                'model': self.table.cellWidget(row, COL_MODEL).currentText().strip(),
                'ip': ip,
                'port': self.table.cellWidget(row, COL_PORT).value(),
                'enabled': self.table.cellWidget(row, COL_ENABLED).findChild(QCheckBox).isChecked(),
            })
            if dll_path:
                entry['dll_path'] = dll_path
            radars.append(entry)

        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({'radars': radars}, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")
            return

        self.accept()
