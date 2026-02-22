"""
NMEA Monitor Dialog
Displays live raw NMEA-0183 sentences from selectable sources.
Provides Play/Stop controls and scrollable message history.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPlainTextEdit, QPushButton, QLabel)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor

MAX_LINES = 5000


class NMEAMonitorDialog(QDialog):
    """Live NMEA-0183 sentence monitor with source selection."""

    def __init__(self, nmea_parser, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NMEA Monitor")
        self.setMinimumSize(720, 480)

        self._parser = nmea_parser
        self._playing = True
        self._count = 0

        self._setup_ui()
        self._populate_sources()

        # Connect to raw sentence signal
        self._parser.sentence_received.connect(self._on_sentence)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Top bar: source selector ---
        top = QHBoxLayout()
        top.addWidget(QLabel("Source:"))
        self._source_combo = QComboBox()
        self._source_combo.setMinimumWidth(280)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        top.addWidget(self._source_combo, 1)
        layout.addLayout(top)

        # --- Center: message display ---
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 10))
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setMaximumBlockCount(MAX_LINES)
        layout.addWidget(self._text, 1)

        # --- Bottom bar: controls ---
        bottom = QHBoxLayout()

        self._play_btn = QPushButton("Play")
        self._play_btn.setEnabled(False)  # already playing
        self._play_btn.clicked.connect(self._on_play)
        bottom.addWidget(self._play_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        bottom.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear)
        bottom.addWidget(self._clear_btn)

        bottom.addStretch()

        self._count_label = QLabel("0 sentences")
        bottom.addWidget(self._count_label)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    # Source population
    # ------------------------------------------------------------------

    def _populate_sources(self):
        """Fill the combo box with all configured NMEA sources."""
        self._source_combo.blockSignals(True)
        self._source_combo.clear()

        # "All Sources" option
        self._source_combo.addItem("All Sources", None)

        seen = set()
        for source in (self._parser.gps_sources +
                       self._parser.heading_sources +
                       self._parser.depth_sources +
                       self._parser.ais_sources):
            if source.name not in seen:
                label = f"{source.name}  ({source.listen_address}:{source.port})"
                self._source_combo.addItem(label, source.name)
                seen.add(source.name)

        self._source_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_sentence(self, source_name: str, sentence: str):
        """Handle incoming raw NMEA sentence."""
        if not self._playing:
            return

        selected = self._source_combo.currentData()
        if selected is not None and source_name != selected:
            return

        self._text.appendPlainText(sentence)
        self._count += 1
        self._count_label.setText(f"{self._count} sentences")

    def _on_source_changed(self, _index):
        """Clear display when source selection changes."""
        self._on_clear()

    def _on_play(self):
        self._playing = True
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def _on_stop(self):
        self._playing = False
        self._stop_btn.setEnabled(False)
        self._play_btn.setEnabled(True)

    def _on_clear(self):
        self._text.clear()
        self._count = 0
        self._count_label.setText("0 sentences")
