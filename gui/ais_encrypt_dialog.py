"""
Encrypted AIS Key Management Dialog.

Allows the operator to add, edit, and remove AES encryption keys used
for decrypting Secure AIS (SA-AIS) traffic.  Keys can be entered in
HEX or ASCII format with live bidirectional conversion.

Keys are persisted to ``ais_encrypt_config.json``.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit,
                             QTableWidget, QHeaderView, QCheckBox,
                             QComboBox, QMessageBox, QWidget)
from PyQt6.QtCore import Qt

from core.ais_decrypt import load_encrypt_config, save_encrypt_config

logger = logging.getLogger(__name__)


class AISEncryptDialog(QDialog):
    """Dialog for managing AIS encryption/decryption keys."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Encrypted AIS Keys")
        self.setModal(True)
        self.setMinimumSize(820, 400)

        self._setup_ui()
        self._load_keys()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info banner
        info = QLabel(
            "Manage AES encryption keys for Secure AIS (SA-AIS) decryption. "
            "Enter keys in HEX (32 hex chars = AES-128, 64 hex chars = AES-256) "
            "or ASCII.  The cipher is auto-detected from key length.  "
            "Keys are stored locally in ais_encrypt_config.json."
        )
        info.setWordWrap(True)
        info.setObjectName("info_label")
        layout.addWidget(info)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Name", "Key ID", "Key (HEX)", "Key (ASCII)",
            "Cipher", "Enabled", "Actions"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        for col in (1, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(3, 140)
        layout.addWidget(self.table)

        # Add key button
        add_btn = QPushButton("Add Key")
        add_btn.clicked.connect(self._add_empty_key)
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
    # Table row management
    # ------------------------------------------------------------------

    def _insert_row(self, name: str, key_id: str, key_hex: str,
                    cipher: str, enabled: bool):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Name
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Key name")
        self.table.setCellWidget(row, 0, name_edit)

        # Key ID (1-2 hex chars)
        kid_edit = QLineEdit(key_id)
        kid_edit.setMaxLength(2)
        kid_edit.setFixedWidth(40)
        kid_edit.setPlaceholderText("ID")
        self.table.setCellWidget(row, 1, kid_edit)

        # Key HEX
        hex_edit = QLineEdit(key_hex)
        hex_edit.setPlaceholderText("Hex key (32 or 64 hex chars)")
        hex_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.table.setCellWidget(row, 2, hex_edit)

        # Key ASCII (derived from HEX)
        ascii_edit = QLineEdit(self._hex_to_ascii(key_hex))
        ascii_edit.setPlaceholderText("ASCII")
        ascii_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.table.setCellWidget(row, 3, ascii_edit)

        # Bidirectional sync: HEX <-> ASCII
        hex_edit.textChanged.connect(
            lambda text, r=row: self._on_hex_changed(r, text))
        ascii_edit.textChanged.connect(
            lambda text, r=row: self._on_ascii_changed(r, text))

        # Cipher combo (auto-detected but user can override)
        cipher_combo = QComboBox()
        cipher_combo.addItems(["AES-128-CBC", "AES-256-CBC"])
        if "256" in cipher:
            cipher_combo.setCurrentIndex(1)
        self.table.setCellWidget(row, 4, cipher_combo)

        # Enabled checkbox
        enabled_cb = QCheckBox()
        enabled_cb.setChecked(enabled)
        cb_container = QWidget()
        cb_layout = QHBoxLayout(cb_container)
        cb_layout.addWidget(enabled_cb)
        cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 5, cb_container)

        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(lambda _, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 6, delete_btn)

        # Auto-detect cipher from key length
        self._auto_detect_cipher(row, key_hex)

    def _add_empty_key(self):
        count = self.table.rowCount() + 1
        self._insert_row(f"Key {count}", "", "", "AES-128-CBC", True)

    def _delete_row(self, row):
        if row < self.table.rowCount():
            self.table.removeRow(row)
            for r in range(self.table.rowCount()):
                btn = QPushButton("Delete")
                btn.clicked.connect(lambda _, r2=r: self._delete_row(r2))
                self.table.setCellWidget(r, 6, btn)

    # ------------------------------------------------------------------
    # HEX <-> ASCII sync
    # ------------------------------------------------------------------

    def _on_hex_changed(self, row, hex_text):
        """When HEX field changes, update ASCII and auto-detect cipher."""
        ascii_edit = self.table.cellWidget(row, 3)
        if ascii_edit and not ascii_edit.hasFocus():
            ascii_edit.blockSignals(True)
            ascii_edit.setText(self._hex_to_ascii(hex_text))
            ascii_edit.blockSignals(False)
        self._auto_detect_cipher(row, hex_text)
        self._validate_hex_field(row, hex_text)

    def _on_ascii_changed(self, row, ascii_text):
        """When ASCII field changes, update HEX and auto-detect cipher."""
        hex_edit = self.table.cellWidget(row, 2)
        if hex_edit and not hex_edit.hasFocus():
            hex_text = ascii_text.encode('utf-8', errors='replace').hex().upper()
            hex_edit.blockSignals(True)
            hex_edit.setText(hex_text)
            hex_edit.blockSignals(False)
            self._auto_detect_cipher(row, hex_text)

    def _auto_detect_cipher(self, row, hex_text):
        """Set cipher combo based on hex key length."""
        combo = self.table.cellWidget(row, 4)
        if combo:
            clean = hex_text.strip().replace(' ', '')
            if len(clean) == 64:
                combo.setCurrentIndex(1)  # AES-256
            elif len(clean) == 32:
                combo.setCurrentIndex(0)  # AES-128

    def _validate_hex_field(self, row, hex_text):
        """Highlight HEX field red if invalid length."""
        hex_edit = self.table.cellWidget(row, 2)
        if not hex_edit:
            return
        clean = hex_text.strip().replace(' ', '')
        valid_chars = all(c in '0123456789abcdefABCDEF' for c in clean)
        valid_len = len(clean) in (0, 32, 64)
        if clean and (not valid_chars or not valid_len):
            hex_edit.setStyleSheet("background-color: #440000;")
        else:
            hex_edit.setStyleSheet("")

    @staticmethod
    def _hex_to_ascii(hex_str: str) -> str:
        """Convert hex string to printable ASCII (replace non-printable)."""
        try:
            raw = bytes.fromhex(hex_str.strip().replace(' ', ''))
            return ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw)
        except ValueError:
            return ''

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_keys(self):
        self.table.setRowCount(0)
        for key in load_encrypt_config():
            self._insert_row(
                key.get('name', ''),
                key.get('key_id', ''),
                key.get('key_hex', ''),
                key.get('cipher', 'AES-128-CBC'),
                key.get('enabled', True),
            )

    def _save_and_close(self):
        keys = []
        for row in range(self.table.rowCount()):
            name = self.table.cellWidget(row, 0).text().strip()
            if not name:
                QMessageBox.warning(self, "Validation",
                                    f"Row {row + 1}: Name cannot be empty.")
                return

            key_id = self.table.cellWidget(row, 1).text().strip()

            key_hex = (self.table.cellWidget(row, 2).text()
                       .strip().replace(' ', '').upper())
            if key_hex:
                if not all(c in '0123456789ABCDEF' for c in key_hex):
                    QMessageBox.warning(
                        self, "Validation",
                        f"Row {row + 1}: HEX key contains invalid characters.")
                    return
                if len(key_hex) not in (32, 64):
                    QMessageBox.warning(
                        self, "Validation",
                        f"Row {row + 1}: HEX key must be 32 chars (AES-128) "
                        f"or 64 chars (AES-256).  Got {len(key_hex)}.")
                    return

            cipher = self.table.cellWidget(row, 4).currentText()

            cb_container = self.table.cellWidget(row, 5)
            enabled = cb_container.findChild(QCheckBox).isChecked()

            keys.append({
                'name': name,
                'key_id': key_id,
                'key_hex': key_hex,
                'cipher': cipher,
                'enabled': enabled,
            })

        try:
            save_encrypt_config(keys)
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save config: {exc}")
            return

        self.accept()
