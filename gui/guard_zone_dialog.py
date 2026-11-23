"""
Guard Zone Configuration Dialog
Allows adding, editing, and removing guard zones for intrusion detection.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QLabel, QLineEdit, QDoubleSpinBox,
                             QTableWidget, QHeaderView, QCheckBox, QComboBox,
                             QMessageBox, QWidget)
from PyQt6.QtCore import Qt

from core.guard_zone import GuardZone


class GuardZoneDialog(QDialog):
    """Dialog for configuring radar guard zones"""

    def __init__(self, guard_zone_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guard Zone Configuration")
        self.setModal(True)
        self.setMinimumSize(750, 500)

        self.gzm = guard_zone_manager

        self._setup_ui()
        self._load_zones()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info
        info = QLabel(
            "Configure guard zones around own ship. An alarm is triggered "
            "when a target enters or exits a zone. 'Relative' zones are measured "
            "from the bow and turn with the ship; 'True' zones are fixed to north."
        )
        info.setWordWrap(True)
        info.setObjectName("info_label")
        layout.addWidget(info)

        # Zone table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Name", "Start Angle", "End Angle",
            "Inner Range (NM)", "Outer Range (NM)", "Reference", "Enabled", "Actions"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        # Add zone button
        add_btn = QPushButton("Add Guard Zone")
        add_btn.clicked.connect(self._add_empty_zone)
        layout.addWidget(add_btn)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("Save && Apply")
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------

    def _load_zones(self):
        """Populate table from the guard zone manager."""
        self.table.setRowCount(0)
        for zone in self.gzm.zones:
            self._insert_zone_row(
                zone.name, zone.start_angle, zone.end_angle,
                zone.inner_range, zone.outer_range, zone.enabled,
                getattr(zone, 'relative', True),
            )

    def _insert_zone_row(self, name, start, end, inner, outer, enabled, relative=True):
        row = self.table.rowCount()
        self.table.insertRow(row)

        name_edit = QLineEdit(name)
        self.table.setCellWidget(row, 0, name_edit)

        start_spin = QDoubleSpinBox()
        start_spin.setRange(0, 359.9)
        start_spin.setDecimals(1)
        start_spin.setSuffix("\u00b0")
        start_spin.setValue(start)
        self.table.setCellWidget(row, 1, start_spin)

        end_spin = QDoubleSpinBox()
        end_spin.setRange(0, 359.9)
        end_spin.setDecimals(1)
        end_spin.setSuffix("\u00b0")
        end_spin.setValue(end)
        self.table.setCellWidget(row, 2, end_spin)

        inner_spin = QDoubleSpinBox()
        inner_spin.setRange(0, 96.0)
        inner_spin.setDecimals(2)
        inner_spin.setSuffix(" NM")
        inner_spin.setValue(inner)
        self.table.setCellWidget(row, 3, inner_spin)

        outer_spin = QDoubleSpinBox()
        outer_spin.setRange(0.01, 96.0)
        outer_spin.setDecimals(2)
        outer_spin.setSuffix(" NM")
        outer_spin.setValue(outer)
        self.table.setCellWidget(row, 4, outer_spin)

        ref_combo = QComboBox()
        ref_combo.addItems(["Relative (bow)", "True (north)"])
        ref_combo.setCurrentIndex(0 if relative else 1)
        self.table.setCellWidget(row, 5, ref_combo)

        enabled_cb = QCheckBox()
        enabled_cb.setChecked(enabled)
        cb_container = QWidget()
        cb_layout = QHBoxLayout(cb_container)
        cb_layout.addWidget(enabled_cb)
        cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 6, cb_container)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(lambda _, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 7, delete_btn)

    def _add_empty_zone(self):
        count = self.table.rowCount() + 1
        self._insert_zone_row(
            f"Zone {count}", 0.0, 90.0, 0.0, 3.0, True,
        )

    def _delete_row(self, row):
        if row < self.table.rowCount():
            self.table.removeRow(row)
            # Rebind delete buttons after row shift
            for r in range(self.table.rowCount()):
                btn = QPushButton("Delete")
                btn.clicked.connect(lambda _, r2=r: self._delete_row(r2))
                self.table.setCellWidget(r, 7, btn)

    # ------------------------------------------------------------------

    def _save_and_close(self):
        """Validate, rebuild guard zones, and close."""
        new_zones = []
        for row in range(self.table.rowCount()):
            name = self.table.cellWidget(row, 0).text().strip()
            if not name:
                QMessageBox.warning(self, "Validation",
                                    f"Row {row + 1}: Name cannot be empty.")
                return

            start = self.table.cellWidget(row, 1).value()
            end = self.table.cellWidget(row, 2).value()
            inner = self.table.cellWidget(row, 3).value()
            outer = self.table.cellWidget(row, 4).value()

            if outer <= inner:
                QMessageBox.warning(
                    self, "Validation",
                    f"Row {row + 1} ({name}): Outer range must be greater "
                    f"than inner range."
                )
                return

            relative = self.table.cellWidget(row, 5).currentIndex() == 0
            cb_container = self.table.cellWidget(row, 6)
            enabled = cb_container.findChild(QCheckBox).isChecked()

            new_zones.append(GuardZone(
                name=name,
                start_angle=start,
                end_angle=end,
                inner_range=inner,
                outer_range=outer,
                enabled=enabled,
                alarm_on_entry=True,
                relative=relative,
            ))

        # Replace zones in the manager
        self.gzm.zones.clear()
        self.gzm.intrusions.clear()
        for zone in new_zones:
            self.gzm.add_zone(zone)

        self.accept()
