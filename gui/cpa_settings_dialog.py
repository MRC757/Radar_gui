"""
CPA/TCPA Threshold Configuration Dialog
Allows the operator to configure global CPA/TCPA alarm thresholds
and risk-tier boundaries (critical / warning / caution).
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QDoubleSpinBox, QPushButton, QGroupBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class CPASettingsDialog(QDialog):
    """Dialog for configuring CPA/TCPA alarm thresholds."""

    def __init__(self, cpa_calculator, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CPA / TCPA Alarm Settings")
        self.setMinimumWidth(380)
        self._calc = cpa_calculator
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Threat detection gate ---
        gate_group = QGroupBox("Threat Detection Gate")
        gate_layout = QGridLayout()

        gate_layout.addWidget(QLabel("CPA threshold (NM):"), 0, 0)
        self._gate_cpa = QDoubleSpinBox()
        self._gate_cpa.setRange(0.1, 20.0)
        self._gate_cpa.setSingleStep(0.1)
        self._gate_cpa.setDecimals(1)
        self._gate_cpa.setValue(self._calc.cpa_threshold)
        gate_layout.addWidget(self._gate_cpa, 0, 1)

        gate_layout.addWidget(QLabel("TCPA threshold (min):"), 1, 0)
        self._gate_tcpa = QDoubleSpinBox()
        self._gate_tcpa.setRange(1.0, 120.0)
        self._gate_tcpa.setSingleStep(1.0)
        self._gate_tcpa.setDecimals(0)
        self._gate_tcpa.setValue(self._calc.tcpa_threshold)
        gate_layout.addWidget(self._gate_tcpa, 1, 1)

        hint = QLabel("Targets outside these limits are classified as safe.")
        hint.setWordWrap(True)
        hint.setFont(QFont("Consolas", 8))
        gate_layout.addWidget(hint, 2, 0, 1, 2)

        gate_group.setLayout(gate_layout)
        layout.addWidget(gate_group)

        # --- Risk tiers ---
        tier_group = QGroupBox("Risk Tier Boundaries")
        tier_layout = QGridLayout()

        header_cpa = QLabel("CPA (NM)")
        header_cpa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_tcpa = QLabel("TCPA (min)")
        header_tcpa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tier_layout.addWidget(QLabel(""), 0, 0)
        tier_layout.addWidget(header_cpa, 0, 1)
        tier_layout.addWidget(header_tcpa, 0, 2)

        # Critical
        tier_layout.addWidget(QLabel("CRITICAL  (alarm):"), 1, 0)
        self._crit_cpa = self._make_spin(0.1, 10.0, 0.1, self._calc.critical_cpa)
        self._crit_tcpa = self._make_spin(1.0, 60.0, 1.0, self._calc.critical_tcpa, decimals=0)
        tier_layout.addWidget(self._crit_cpa, 1, 1)
        tier_layout.addWidget(self._crit_tcpa, 1, 2)

        # Warning
        tier_layout.addWidget(QLabel("WARNING  (alarm):"), 2, 0)
        self._warn_cpa = self._make_spin(0.1, 10.0, 0.1, self._calc.warning_cpa)
        self._warn_tcpa = self._make_spin(1.0, 60.0, 1.0, self._calc.warning_tcpa, decimals=0)
        tier_layout.addWidget(self._warn_cpa, 2, 1)
        tier_layout.addWidget(self._warn_tcpa, 2, 2)

        # Caution
        tier_layout.addWidget(QLabel("CAUTION  (visual only):"), 3, 0)
        self._caut_cpa = self._make_spin(0.1, 20.0, 0.1, self._calc.caution_cpa)
        self._caut_tcpa = self._make_spin(1.0, 120.0, 1.0, self._calc.caution_tcpa, decimals=0)
        tier_layout.addWidget(self._caut_cpa, 3, 1)
        tier_layout.addWidget(self._caut_tcpa, 3, 2)

        tier_group.setLayout(tier_layout)
        layout.addWidget(tier_group)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        defaults_btn = QPushButton("Restore Defaults")
        defaults_btn.clicked.connect(self._restore_defaults)
        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(defaults_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_spin(lo, hi, step, value, decimals=1):
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setDecimals(int(decimals))
        spin.setValue(value)
        return spin

    # ------------------------------------------------------------------
    def _restore_defaults(self):
        self._gate_cpa.setValue(2.0)
        self._gate_tcpa.setValue(12.0)
        self._crit_cpa.setValue(0.5)
        self._crit_tcpa.setValue(6.0)
        self._warn_cpa.setValue(1.0)
        self._warn_tcpa.setValue(12.0)
        self._caut_cpa.setValue(2.0)
        self._caut_tcpa.setValue(20.0)

    # ------------------------------------------------------------------
    def get_values(self):
        """Return all threshold values as a dict."""
        return {
            'cpa_threshold': self._gate_cpa.value(),
            'tcpa_threshold': self._gate_tcpa.value(),
            'critical_cpa': self._crit_cpa.value(),
            'critical_tcpa': self._crit_tcpa.value(),
            'warning_cpa': self._warn_cpa.value(),
            'warning_tcpa': self._warn_tcpa.value(),
            'caution_cpa': self._caut_cpa.value(),
            'caution_tcpa': self._caut_tcpa.value(),
        }
