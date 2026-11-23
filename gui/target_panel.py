"""
Selected Target Information Panel
Displays detailed ARPA/AIS target data in the right dock panel.
IMO ARPA compliant: shows CPA, TCPA, bearing, range, course, speed, risk.
"""

from PyQt6.QtWidgets import QGroupBox, QLabel, QGridLayout
from PyQt6.QtGui import QFont


class SelectedTargetPanel(QGroupBox):
    """Panel showing full data for the currently selected target"""

    # (label_text, field_key)
    _ROWS = [
        ("TYPE", "type_label"),
        ("ID", "id_label"),
        ("NAME", "name_label"),
        ("MMSI", "mmsi_label"),
        ("LAT", "lat_label"),
        ("LON", "lon_label"),
        ("COG", "cog_label"),
        ("SOG", "sog_label"),
        ("BRG", "brg_label"),
        ("RNG", "rng_label"),
        ("CPA", "cpa_label"),
        ("TCPA", "tcpa_label"),
        ("RISK", "risk_label"),
        ("CLASS", "class_label"),
        ("GUARD", "guard_label"),
    ]

    def __init__(self, title="SELECTED TARGET", parent=None):
        super().__init__(title, parent)
        self._fields = {}
        self._setup_ui()
        self.clear()

    def _setup_ui(self):
        layout = QGridLayout()
        layout.setSpacing(3)
        self.setLayout(layout)

        label_style = "color: #AAAAAA; font-family: Consolas; font-size: 13px;"
        self._value_style = "color: #00FF00; font-family: Consolas; font-size: 13px;"

        for i, (text, key) in enumerate(self._ROWS):
            label = QLabel(f"{text}:")
            label.setStyleSheet(label_style)
            label.setFont(QFont("Consolas", 13))
            value = QLabel("--")
            value.setStyleSheet(self._value_style)
            value.setFont(QFont("Consolas", 13))
            layout.addWidget(label, i, 0)
            layout.addWidget(value, i, 1)
            self._fields[key] = value

    def update_target(self, data: dict):
        """Update panel with a target data dictionary."""
        self._fields['type_label'].setText(data.get('type', '--').upper())
        self._fields['id_label'].setText(str(data.get('id', '--'))[:12])
        self._fields['name_label'].setText(data.get('name', '--')[:20])
        self._fields['mmsi_label'].setText(str(data.get('mmsi', '--')))
        self._fields['lat_label'].setText(f"{data.get('lat', 0):.6f}")
        self._fields['lon_label'].setText(f"{data.get('lon', 0):.6f}")
        self._fields['cog_label'].setText(f"{data.get('course', 0):.1f}\u00b0")
        self._fields['sog_label'].setText(f"{data.get('speed', 0):.1f} kts")
        self._fields['brg_label'].setText(f"{data.get('bearing', 0):.1f}\u00b0")
        self._fields['rng_label'].setText(f"{data.get('range', 0):.2f} NM")
        self._fields['cpa_label'].setText(f"{data.get('cpa', 0):.2f} NM")
        self._fields['tcpa_label'].setText(f"{data.get('tcpa', 0):.1f} min")

        risk = data.get('risk_level', 'safe')
        self._fields['risk_label'].setText(risk.upper())
        risk_colors = {
            'critical': '#FF0000',
            'warning': '#FF0000',
            'caution': '#FFA500',
            'safe': '#00FF00',
        }
        self._fields['risk_label'].setStyleSheet(
            f"color: {risk_colors.get(risk, '#00FF00')}; font-family: Consolas; "
            f"font-size: 13px; font-weight: bold;"
        )

        cls = data.get('classification')
        self._fields['class_label'].setText(cls.upper() if cls else '--')
        if cls == 'hostile':
            self._fields['class_label'].setStyleSheet(
                "color: #FF0000; font-family: Consolas; font-size: 13px; font-weight: bold;"
            )
        elif cls == 'friendly':
            self._fields['class_label'].setStyleSheet(
                "color: #00CC00; font-family: Consolas; font-size: 13px; font-weight: bold;"
            )
        else:
            self._fields['class_label'].setStyleSheet(self._value_style)

        guards = data.get('guard_zones', [])
        self._fields['guard_label'].setText(', '.join(guards) if guards else 'CLEAR')
        if guards:
            self._fields['guard_label'].setStyleSheet(
                "color: #FF0000; font-family: Consolas; font-size: 13px; font-weight: bold;"
            )
        else:
            self._fields['guard_label'].setStyleSheet(self._value_style)

        self.show()

    def clear(self):
        """Reset all fields to default."""
        for field in self._fields.values():
            field.setText("--")
            field.setStyleSheet(self._value_style)

    def apply_theme_colors(self, primary_hex: str, border_hex: str):
        """Re-style with theme colors."""
        self.setStyleSheet(
            f"QGroupBox {{ color: {primary_hex}; font-weight: bold; font-size: 13px; }}"
        )
        self._value_style = f"color: {primary_hex}; font-family: Consolas; font-size: 13px;"
