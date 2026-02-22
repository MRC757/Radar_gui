"""
IMO ARPA Display Color Theme System
Per SN.1/Circ.243/Rev.2 and IEC 62388

Four modes:
  DAY       - High contrast, bright colors for daylight operation
  DUSK      - Medium contrast for twilight conditions
  NIGHT     - Low intensity green phosphor style
  RED_NIGHT - Red-only for dark adaptation preservation
"""

from dataclasses import dataclass
from PyQt6.QtGui import QColor
from enum import Enum, auto


class DisplayMode(Enum):
    DAY = auto()
    DUSK = auto()
    NIGHT = auto()
    RED_NIGHT = auto()


@dataclass
class RadarColorTheme:
    """Complete color theme for the radar display"""
    # PPI Background and grid
    ppi_background: QColor
    grid_lines: QColor
    grid_lines_major: QColor
    range_ring_labels: QColor
    compass_text: QColor

    # Radar video (IMO: green)
    radar_echo_weak: QColor
    radar_echo_strong: QColor
    sweep_line: QColor
    sweep_fade: QColor

    # ARPA tracked targets (IMO: yellow normal, red dangerous)
    arpa_target_normal: QColor
    arpa_target_caution: QColor
    arpa_target_dangerous: QColor
    arpa_vector: QColor
    arpa_past_position: QColor

    # AIS targets (IMO: distinct from ARPA - blue)
    ais_target_normal: QColor
    ais_target_activated: QColor
    ais_target_dangerous: QColor
    ais_target_selected: QColor
    ais_info_text: QColor

    # Own ship
    own_ship_symbol: QColor
    heading_line: QColor

    # Guard zones
    guard_zone_boundary: QColor
    guard_zone_fill: QColor
    guard_zone_alarm: QColor

    # EBL / VRM
    ebl_line: QColor
    vrm_circle: QColor

    # Selection
    selection_highlight: QColor
    selection_ring: QColor

    # UI panels (sidebar, controls)
    ui_background: QColor
    ui_text_primary: QColor
    ui_text_secondary: QColor
    ui_group_border: QColor
    ui_accent: QColor
    ui_warning: QColor
    ui_critical: QColor

    # Misc
    text_overlay: QColor


# ============================================================
# Theme Definitions
# ============================================================

DAY_THEME = RadarColorTheme(
    ppi_background=QColor(0, 10, 0),
    grid_lines=QColor(0, 100, 0),
    grid_lines_major=QColor(0, 140, 0),
    range_ring_labels=QColor(0, 200, 0),
    compass_text=QColor(220, 220, 220),

    radar_echo_weak=QColor(0, 200, 0),
    radar_echo_strong=QColor(0, 255, 0),
    sweep_line=QColor(0, 255, 0, 120),
    sweep_fade=QColor(0, 255, 0, 40),

    arpa_target_normal=QColor(255, 220, 0),
    arpa_target_caution=QColor(255, 165, 0),
    arpa_target_dangerous=QColor(255, 0, 0),
    arpa_vector=QColor(255, 220, 0),
    arpa_past_position=QColor(255, 220, 0, 150),

    ais_target_normal=QColor(0, 180, 255),
    ais_target_activated=QColor(0, 220, 255),
    ais_target_dangerous=QColor(255, 0, 0),
    ais_target_selected=QColor(255, 255, 255),
    ais_info_text=QColor(0, 200, 255),

    own_ship_symbol=QColor(255, 255, 255),
    heading_line=QColor(255, 255, 255),

    guard_zone_boundary=QColor(255, 0, 0, 180),
    guard_zone_fill=QColor(255, 0, 0, 30),
    guard_zone_alarm=QColor(255, 0, 0, 100),

    ebl_line=QColor(255, 180, 0),
    vrm_circle=QColor(255, 180, 0),

    selection_highlight=QColor(255, 255, 255),
    selection_ring=QColor(255, 255, 255, 200),

    ui_background=QColor(20, 20, 20),
    ui_text_primary=QColor(0, 255, 0),
    ui_text_secondary=QColor(0, 200, 255),
    ui_group_border=QColor(0, 255, 0),
    ui_accent=QColor(0, 200, 255),
    ui_warning=QColor(255, 165, 0),
    ui_critical=QColor(255, 0, 0),

    text_overlay=QColor(0, 255, 0),
)

DUSK_THEME = RadarColorTheme(
    ppi_background=QColor(0, 5, 0),
    grid_lines=QColor(0, 70, 0),
    grid_lines_major=QColor(0, 100, 0),
    range_ring_labels=QColor(0, 140, 0),
    compass_text=QColor(150, 150, 150),

    radar_echo_weak=QColor(0, 140, 0),
    radar_echo_strong=QColor(0, 190, 0),
    sweep_line=QColor(0, 180, 0, 100),
    sweep_fade=QColor(0, 180, 0, 30),

    arpa_target_normal=QColor(200, 170, 0),
    arpa_target_caution=QColor(200, 120, 0),
    arpa_target_dangerous=QColor(200, 0, 0),
    arpa_vector=QColor(200, 170, 0),
    arpa_past_position=QColor(200, 170, 0, 120),

    ais_target_normal=QColor(0, 130, 200),
    ais_target_activated=QColor(0, 160, 200),
    ais_target_dangerous=QColor(200, 0, 0),
    ais_target_selected=QColor(200, 200, 200),
    ais_info_text=QColor(0, 150, 200),

    own_ship_symbol=QColor(200, 200, 200),
    heading_line=QColor(200, 200, 200),

    guard_zone_boundary=QColor(200, 0, 0, 150),
    guard_zone_fill=QColor(200, 0, 0, 20),
    guard_zone_alarm=QColor(200, 0, 0, 80),

    ebl_line=QColor(200, 140, 0),
    vrm_circle=QColor(200, 140, 0),

    selection_highlight=QColor(200, 200, 200),
    selection_ring=QColor(200, 200, 200, 180),

    ui_background=QColor(15, 15, 15),
    ui_text_primary=QColor(0, 180, 0),
    ui_text_secondary=QColor(0, 150, 180),
    ui_group_border=QColor(0, 140, 0),
    ui_accent=QColor(0, 150, 180),
    ui_warning=QColor(200, 120, 0),
    ui_critical=QColor(200, 0, 0),

    text_overlay=QColor(0, 180, 0),
)

NIGHT_THEME = RadarColorTheme(
    ppi_background=QColor(0, 2, 0),
    grid_lines=QColor(0, 40, 0),
    grid_lines_major=QColor(0, 60, 0),
    range_ring_labels=QColor(0, 80, 0),
    compass_text=QColor(80, 80, 80),

    radar_echo_weak=QColor(0, 80, 0),
    radar_echo_strong=QColor(0, 130, 0),
    sweep_line=QColor(0, 100, 0, 80),
    sweep_fade=QColor(0, 100, 0, 20),

    arpa_target_normal=QColor(130, 110, 0),
    arpa_target_caution=QColor(130, 80, 0),
    arpa_target_dangerous=QColor(130, 0, 0),
    arpa_vector=QColor(130, 110, 0),
    arpa_past_position=QColor(130, 110, 0, 80),

    ais_target_normal=QColor(0, 80, 130),
    ais_target_activated=QColor(0, 100, 130),
    ais_target_dangerous=QColor(130, 0, 0),
    ais_target_selected=QColor(130, 130, 130),
    ais_info_text=QColor(0, 80, 130),

    own_ship_symbol=QColor(120, 120, 120),
    heading_line=QColor(120, 120, 120),

    guard_zone_boundary=QColor(130, 0, 0, 120),
    guard_zone_fill=QColor(130, 0, 0, 15),
    guard_zone_alarm=QColor(130, 0, 0, 60),

    ebl_line=QColor(130, 90, 0),
    vrm_circle=QColor(130, 90, 0),

    selection_highlight=QColor(130, 130, 130),
    selection_ring=QColor(130, 130, 130, 150),

    ui_background=QColor(5, 5, 5),
    ui_text_primary=QColor(0, 100, 0),
    ui_text_secondary=QColor(0, 80, 100),
    ui_group_border=QColor(0, 80, 0),
    ui_accent=QColor(0, 80, 100),
    ui_warning=QColor(130, 80, 0),
    ui_critical=QColor(130, 0, 0),

    text_overlay=QColor(0, 100, 0),
)

RED_NIGHT_THEME = RadarColorTheme(
    ppi_background=QColor(2, 0, 0),
    grid_lines=QColor(40, 0, 0),
    grid_lines_major=QColor(60, 0, 0),
    range_ring_labels=QColor(90, 0, 0),
    compass_text=QColor(80, 0, 0),

    radar_echo_weak=QColor(80, 0, 0),
    radar_echo_strong=QColor(140, 0, 0),
    sweep_line=QColor(120, 0, 0, 80),
    sweep_fade=QColor(100, 0, 0, 20),

    arpa_target_normal=QColor(140, 70, 0),
    arpa_target_caution=QColor(160, 50, 0),
    arpa_target_dangerous=QColor(180, 0, 0),
    arpa_vector=QColor(140, 70, 0),
    arpa_past_position=QColor(140, 70, 0, 80),

    ais_target_normal=QColor(100, 30, 0),
    ais_target_activated=QColor(120, 40, 0),
    ais_target_dangerous=QColor(180, 0, 0),
    ais_target_selected=QColor(160, 80, 0),
    ais_info_text=QColor(120, 40, 0),

    own_ship_symbol=QColor(140, 40, 0),
    heading_line=QColor(140, 40, 0),

    guard_zone_boundary=QColor(160, 0, 0, 120),
    guard_zone_fill=QColor(140, 0, 0, 15),
    guard_zone_alarm=QColor(180, 0, 0, 60),

    ebl_line=QColor(140, 50, 0),
    vrm_circle=QColor(140, 50, 0),

    selection_highlight=QColor(160, 80, 0),
    selection_ring=QColor(160, 80, 0, 150),

    ui_background=QColor(5, 0, 0),
    ui_text_primary=QColor(120, 0, 0),
    ui_text_secondary=QColor(100, 30, 0),
    ui_group_border=QColor(80, 0, 0),
    ui_accent=QColor(100, 30, 0),
    ui_warning=QColor(140, 50, 0),
    ui_critical=QColor(180, 0, 0),

    text_overlay=QColor(120, 0, 0),
)

THEMES = {
    DisplayMode.DAY: DAY_THEME,
    DisplayMode.DUSK: DUSK_THEME,
    DisplayMode.NIGHT: NIGHT_THEME,
    DisplayMode.RED_NIGHT: RED_NIGHT_THEME,
}


def get_theme(mode: DisplayMode) -> RadarColorTheme:
    """Get the color theme for a display mode"""
    return THEMES[mode]


def dialog_stylesheet(theme: RadarColorTheme) -> str:
    """Generate a stylesheet for QDialog popups that matches the given theme."""
    bg = theme.ui_background.name()
    primary = theme.ui_text_primary.name()
    secondary = theme.ui_text_secondary.name()
    border = theme.ui_group_border.name()
    accent = theme.ui_accent.name()
    warning = theme.ui_warning.name()
    critical = theme.ui_critical.name()

    return f"""
        QDialog {{
            background-color: {bg};
            color: {primary};
            font-family: Consolas;
        }}
        QLabel {{
            color: {primary};
            font-family: Consolas;
        }}
        QGroupBox {{
            color: {primary};
            font-weight: bold;
            font-family: Consolas;
            border: 1px solid {border};
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid {border};
            background-color: {bg};
        }}
        QTabBar::tab {{
            background-color: {bg};
            color: {secondary};
            border: 1px solid {border};
            padding: 6px 14px;
            font-family: Consolas;
        }}
        QTabBar::tab:selected {{
            background-color: {border};
            color: {bg};
        }}
        QTabBar::tab:hover {{
            background-color: {border};
            color: {bg};
        }}
        QTableWidget {{
            background-color: {bg};
            color: {primary};
            gridline-color: {border};
            font-family: Consolas;
            border: 1px solid {border};
        }}
        QTableWidget::item {{
            padding: 4px;
        }}
        QHeaderView::section {{
            background-color: {bg};
            color: {accent};
            border: 1px solid {border};
            padding: 4px;
            font-family: Consolas;
            font-weight: bold;
        }}
        QPushButton {{
            background-color: {bg};
            color: {primary};
            border: 1px solid {border};
            padding: 6px 14px;
            font-family: Consolas;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: {border};
            color: {bg};
        }}
        QLineEdit {{
            background-color: {bg};
            color: {primary};
            border: 1px solid {border};
            padding: 3px;
            font-family: Consolas;
        }}
        QSpinBox {{
            background-color: {bg};
            color: {primary};
            border: 1px solid {border};
            padding: 3px;
            font-family: Consolas;
        }}
        QDoubleSpinBox {{
            background-color: {bg};
            color: {primary};
            border: 1px solid {border};
            padding: 3px;
            font-family: Consolas;
        }}
        QCheckBox {{
            color: {primary};
            font-family: Consolas;
        }}
        QCheckBox::indicator {{
            border: 1px solid {border};
            background-color: {bg};
            width: 14px;
            height: 14px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {primary};
        }}
        QComboBox {{
            background-color: {bg};
            color: {primary};
            border: 1px solid {border};
            padding: 3px;
            font-family: Consolas;
        }}
        QComboBox QAbstractItemView {{
            background-color: {bg};
            color: {primary};
            border: 1px solid {border};
            selection-background-color: {border};
            selection-color: {bg};
        }}
        QTextEdit {{
            background-color: {bg};
            color: {accent};
            font-family: Consolas;
            font-size: 10px;
            border: 1px solid {border};
        }}
        QMessageBox {{
            background-color: {bg};
            color: {primary};
            font-family: Consolas;
        }}
        QLabel#info_label {{
            color: {secondary};
            font-style: italic;
            font-size: 10px;
        }}
        QGroupBox#log_group {{
            color: {warning};
        }}
        QTextEdit#fault_log {{
            color: {warning};
        }}
    """
