"""
NMEA Configuration Dialog
Allows configuration of multiple NMEA-0183 input sources via UDP.
Designed for Perle IOLAN Terminal Servers that convert serial NMEA-0183
instrument data (RS-422 / RS-232) to UDP/IP.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QLabel, QLineEdit, QSpinBox,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QComboBox, QCheckBox, QMessageBox, QTabWidget,
                             QTextEdit)
from PyQt6.QtCore import Qt
import json
import os

from core.camera_controller import nmea_checksum

logger = logging.getLogger(__name__)


class NMEAConfigDialog(QDialog):
    """Dialog for configuring NMEA-0183 input sources"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NMEA-0183 Source Configuration")
        self.setModal(True)
        self.setMinimumSize(800, 600)
        
        # Load existing configuration
        self.config = self.load_config()
        
        self.setup_ui()
        self.load_sources()
        
    def setup_ui(self):
        """Setup user interface"""
        layout = QVBoxLayout(self)
        
        # Tabs for different source types
        tabs = QTabWidget()
        
        # GPS Sources Tab
        self.gps_table = self.create_source_table("GPS")
        tabs.addTab(self.create_source_tab(self.gps_table, "GPS"), "GPS Sources")
        
        # Heading Sources Tab
        self.heading_table = self.create_source_table("Heading")
        tabs.addTab(self.create_source_tab(self.heading_table, "Heading"), "Heading Sources")
        
        # Depth Sources Tab
        self.depth_table = self.create_source_table("Depth")
        tabs.addTab(self.create_source_tab(self.depth_table, "Depth"), "Depth Sources")
        
        # AIS Sources Tab
        self.ais_table = self.create_source_table("AIS")
        tabs.addTab(self.create_source_tab(self.ais_table, "AIS"), "AIS Sources")

        # ADS-B Sources Tab
        self.adsb_table = self.create_source_table("ADS-B")
        tabs.addTab(self.create_adsb_source_tab(), "ADS-B Sources")

        # Camera Control Tab
        tabs.addTab(self.create_camera_tab(), "Camera Control")

        layout.addWidget(tabs)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        test_btn = QPushButton("Test Connections")
        test_btn.clicked.connect(self.test_connections)
        button_layout.addWidget(test_btn)
        
        button_layout.addStretch()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_config_and_close)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
    def create_source_table(self, source_type):
        """Create table for source configuration"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Name", "Listen Address", "UDP Port", "Priority", "Enabled", "Actions"
        ])
        
        # Set column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        
        return table
        
    def create_source_tab(self, table, source_type):
        """Create tab widget for a source type"""
        widget = QGroupBox()
        layout = QVBoxLayout(widget)
        
        # Info label
        info = QLabel(
            f"Configure {source_type} NMEA-0183 sources received via UDP "
            f"from Perle IOLAN Terminal Servers or compatible serial-to-IP converters."
        )
        info.setWordWrap(True)
        info.setObjectName("info_label")
        layout.addWidget(info)

        # Priority / address info
        priority_info = QLabel(
            "Listen Address: 0.0.0.0 = accept from any network interface (recommended). "
            "Priority: 1 = Highest. System auto-selects the highest-priority active source."
        )
        priority_info.setWordWrap(True)
        priority_info.setObjectName("info_label")
        layout.addWidget(priority_info)
        
        # Table
        layout.addWidget(table)
        
        # Add source button
        add_btn = QPushButton(f"Add {source_type} Source")
        add_btn.clicked.connect(lambda: self.add_source(table, source_type))
        layout.addWidget(add_btn)
        
        return widget
        
    # ------------------------------------------------------------------
    # ADS-B Source tab
    # ------------------------------------------------------------------

    def create_adsb_source_tab(self):
        """Build the ADS-B Sources configuration tab with protocol reference."""
        widget = QGroupBox()
        outer = QVBoxLayout(widget)

        # ── Connection info ──────────────────────────────────────────────
        conn_info = QLabel(
            "Configure UDP ports to receive ADS-B / FLARM NMEA sentences directly "
            "from your ADS-B receiver (e.g. Stratux, dump1090, OpenSky feeder, or "
            "any FLARM-compatible device).  Each source binds a local UDP port — "
            "point your receiver's output stream at this machine's IP on the "
            "configured port."
        )
        conn_info.setWordWrap(True)
        conn_info.setObjectName("info_label")
        outer.addWidget(conn_info)

        addr_info = QLabel(
            "Listen Address: 0.0.0.0 = accept from any network interface (recommended).  "
            "Priority: 1 = Highest.  System auto-selects the highest-priority active source."
        )
        addr_info.setWordWrap(True)
        addr_info.setObjectName("info_label")
        outer.addWidget(addr_info)

        # ── Source table ─────────────────────────────────────────────────
        outer.addWidget(self.adsb_table)

        add_btn = QPushButton("Add ADS-B Source")
        add_btn.clicked.connect(lambda: self.add_source(self.adsb_table, "ADS-B"))
        outer.addWidget(add_btn)

        # ── Protocol reference ───────────────────────────────────────────
        ref_group = QGroupBox("FLARM / ADS-B NMEA Message Reference")
        ref_layout = QVBoxLayout(ref_group)

        ref_text = QTextEdit()
        ref_text.setReadOnly(True)
        ref_text.setFont(__import__('PyQt6.QtGui', fromlist=['QFont']).QFont('Consolas', 9))
        ref_text.setMinimumHeight(220)
        ref_text.setPlainText(
            "$PFLAA — Traffic Position Report  (one sentence per detected aircraft)\n"
            "─────────────────────────────────────────────────────────────────────\n"
            "Syntax:  $PFLAA,<Alarm>,<RelN>,<RelE>,<RelV>,<IDType>,<ID>,<Track>,"
            "<TurnRate>,<GndSpd>,<ClimbRate>,<AcType>*<CS>\n"
            "\n"
            "Field       Description\n"
            "──────────  ──────────────────────────────────────────────────────────\n"
            "Alarm       Alarm level:  0=No alarm  1=Low  2=Important  3=Urgent\n"
            "RelN        Relative position North  (metres, + = north of receiver)\n"
            "RelE        Relative position East   (metres, + = east  of receiver)\n"
            "RelV        Relative altitude        (metres, + = above receiver)\n"
            "IDType      ID type:  1=ICAO 24-bit  2=FLARM  3=OGN\n"
            "ID          6-character hex address  (e.g. 4B1F3A)\n"
            "Track       True track / heading     (degrees, 0-359)\n"
            "TurnRate    Turn rate                (degrees/sec, may be empty)\n"
            "GndSpd      Ground speed             (m/s)\n"
            "ClimbRate   Climb / descent rate     (m/s, + = climbing, may be empty)\n"
            "AcType      Aircraft type code       (see table below)\n"
            "CS          NMEA XOR checksum        (2 hex digits)\n"
            "\n"
            "Example:  $PFLAA,0,1234,-456,+180,1,4B1F3A,274,,52,0,8*1E\n"
            "          Aircraft ~1.2 km N, 456 m W, 180 m above; heading 274°; 101 kt; jet\n"
            "\n"
            "AircraftType codes\n"
            "──────────────────\n"
            "0=Unknown      1=Glider/motor-glider   2=Tow/tug plane   3=Helicopter\n"
            "4=Parachute    5=Drop plane             6=Hang-glider     7=Paraglider\n"
            "8=Piston a/c   9=Jet/turboprop a/c     10=Unknown        11=Balloon\n"
            "12=Airship     13=UAV/drone             14=Reserved       15=Static obstacle\n"
            "\n"
            "\n"
            "$PFLAU — Receiver Status  (sent by receiver, no aircraft plotted)\n"
            "─────────────────────────────────────────────────────────────────\n"
            "Syntax:  $PFLAU,<RX>,<TX>,<GPS>,<Power>,<Alarm>,<RelBrg>,<AlarmType>,"
            "<RelV>,<RelDist>,<ID>*<CS>\n"
            "\n"
            "Field       Description\n"
            "──────────  ──────────────────────────────────────────────────────────\n"
            "RX          Number of devices currently received\n"
            "TX          Transmission status:  0=No Tx  1=OK\n"
            "GPS         GPS status:  0=No GPS  1=OK no fix  2=2D fix  3=3D fix\n"
            "Power       Power status:  0=Under-voltage  1=OK\n"
            "Alarm       Current alarm level (same codes as PFLAA)\n"
            "RelBrg      Relative bearing to alarm target (degrees, may be empty)\n"
            "AlarmType   0=No alarm  1=Traffic  2=Obstacle  3=Traffic advisory\n"
            "RelV        Relative vertical of alarm target (metres, may be empty)\n"
            "RelDist     Relative distance of alarm target (metres, may be empty)\n"
            "ID          ID of alarm target (may be empty)\n"
            "\n"
            "Example:  $PFLAU,3,1,3,1,0,,0,,,,*CS\n"
            "          3 aircraft in range; GPS 3D fix; no alarm active\n"
            "\n"
            "\n"
            "Position Conversion\n"
            "───────────────────\n"
            "PFLAA positions are receiver-relative (metres).  This application\n"
            "automatically converts them to absolute lat/lon using own ship's GPS:\n"
            "  target_lat = own_lat + RelN / 111320\n"
            "  target_lon = own_lon + RelE / (111320 × cos(own_lat))\n"
            "Own ship GPS must be active for ADS-B tracks to appear correctly.\n"
        )
        ref_layout.addWidget(ref_text)
        outer.addWidget(ref_group)

        return widget

    # ------------------------------------------------------------------
    # Camera tab
    # ------------------------------------------------------------------

    def create_camera_tab(self):
        """Build the Camera Control configuration tab."""
        cam = self.config.get('camera', {})

        widget = QGroupBox()
        outer = QVBoxLayout(widget)

        # ── Enable / Connection ──────────────────────────────────────────
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout(conn_group)

        self._cam_enabled = QCheckBox("Enable camera control")
        self._cam_enabled.setChecked(cam.get('enabled', False))
        conn_layout.addWidget(self._cam_enabled)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Camera Host / IP:"))
        self._cam_host = QLineEdit(cam.get('host', '192.168.1.100'))
        self._cam_host.setMaximumWidth(180)
        row1.addWidget(self._cam_host)
        row1.addSpacing(20)
        row1.addWidget(QLabel("Send Port:"))
        self._cam_send_port = QSpinBox()
        self._cam_send_port.setRange(1, 65535)
        self._cam_send_port.setValue(int(cam.get('send_port', 10120)))
        row1.addWidget(self._cam_send_port)
        row1.addSpacing(20)
        row1.addWidget(QLabel("Listen Port:"))
        self._cam_listen_port = QSpinBox()
        self._cam_listen_port.setRange(1, 65535)
        self._cam_listen_port.setValue(int(cam.get('listen_port', 10121)))
        row1.addWidget(self._cam_listen_port)
        row1.addStretch()
        conn_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Bearing Mode:"))
        self._cam_bearing_mode = QComboBox()
        self._cam_bearing_mode.addItem("Relative to ship heading °R", "relative")
        self._cam_bearing_mode.addItem("True bearing °T", "true")
        saved_mode = cam.get('bearing_mode', 'relative')
        idx = self._cam_bearing_mode.findData(saved_mode)
        if idx >= 0:
            self._cam_bearing_mode.setCurrentIndex(idx)
        self._cam_bearing_mode.setToolTip(
            "Relative: bearing sent is degrees from ship's bow (use for cameras without a gyro).\n"
            "True: bearing sent is geographic true north reference."
        )
        row2.addWidget(self._cam_bearing_mode)
        row2.addStretch()
        conn_layout.addLayout(row2)
        outer.addWidget(conn_group)

        # ── Command Message Builder ──────────────────────────────────────
        cmd_group = QGroupBox("Command Message  (sent TO camera)")
        cmd_layout = QVBoxLayout(cmd_group)

        info_lbl = QLabel(
            "Available template variables:  "
            "<b>[HDR]</b> = command header &nbsp; "
            "<b>[BRG]</b> = bearing degrees (ddd.dd) &nbsp; "
            "<b>[CHK]</b> = NMEA XOR checksum"
        )
        info_lbl.setWordWrap(True)
        cmd_layout.addWidget(info_lbl)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(QLabel("Command Header:"))
        self._cam_cmd_header = QLineEdit(cam.get('cmd_header', 'PCAM'))
        self._cam_cmd_header.setMaximumWidth(120)
        self._cam_cmd_header.setToolTip(
            "The identifier placed at [HDR] in the template, e.g. PCAM"
        )
        hdr_row.addWidget(self._cam_cmd_header)
        hdr_row.addStretch()
        cmd_layout.addLayout(hdr_row)

        tmpl_row = QHBoxLayout()
        tmpl_row.addWidget(QLabel("Message Template:"))
        self._cam_cmd_template = QLineEdit(
            cam.get('cmd_template', '$[HDR],[BRG]*[CHK]')
        )
        self._cam_cmd_template.setToolTip(
            "Full NMEA-style sentence template.  Example: $[HDR],[BRG]*[CHK]"
        )
        tmpl_row.addWidget(self._cam_cmd_template)
        cmd_layout.addLayout(tmpl_row)

        prev_row = QHBoxLayout()
        prev_row.addWidget(QLabel("Preview (bearing 045.30°):"))
        self._cam_preview = QLabel("")
        self._cam_preview.setStyleSheet(
            "color: #00FF00; font-family: Consolas; font-size: 11px;"
        )
        prev_row.addWidget(self._cam_preview)
        prev_row.addStretch()
        preview_btn = QPushButton("Refresh Preview")
        preview_btn.clicked.connect(self._refresh_camera_preview)
        prev_row.addWidget(preview_btn)
        cmd_layout.addLayout(prev_row)
        outer.addWidget(cmd_group)
        self._refresh_camera_preview()   # initial render

        # ── Response Message Decoder ─────────────────────────────────────
        resp_group = QGroupBox("Response Message  (received FROM camera)")
        resp_layout = QVBoxLayout(resp_group)

        resp_info = QLabel(
            "The camera responds with a NMEA-style sentence containing its "
            "current azimuth.  Configure the response header and which "
            "comma-separated field (1-based, after the header) holds the azimuth."
        )
        resp_info.setWordWrap(True)
        resp_layout.addWidget(resp_info)

        resp_row = QHBoxLayout()
        resp_row.addWidget(QLabel("Response Header:"))
        self._cam_resp_header = QLineEdit(cam.get('response_header', 'PCAMR'))
        self._cam_resp_header.setMaximumWidth(120)
        resp_row.addWidget(self._cam_resp_header)
        resp_row.addSpacing(20)
        resp_row.addWidget(QLabel("Azimuth Field Index (1-based):"))
        self._cam_resp_field = QSpinBox()
        self._cam_resp_field.setRange(1, 20)
        self._cam_resp_field.setValue(int(cam.get('response_bearing_field', 1)))
        self._cam_resp_field.setToolTip(
            "Field position (1 = first field after header) that contains the "
            "camera azimuth value.  Example: $PCAMR,045.30*XX → field 1 = 045.30"
        )
        resp_row.addWidget(self._cam_resp_field)
        resp_row.addStretch()
        resp_layout.addLayout(resp_row)

        # Example sentence display (updates live)
        ex_row = QHBoxLayout()
        ex_row.addWidget(QLabel("Example response:"))
        self._cam_resp_example = QLabel("")
        self._cam_resp_example.setStyleSheet(
            "color: #00CCFF; font-family: Consolas; font-size: 11px;"
        )
        ex_row.addWidget(self._cam_resp_example)
        ex_row.addStretch()
        resp_layout.addLayout(ex_row)
        outer.addWidget(resp_group)
        self._refresh_camera_resp_example()  # initial render

        # Keep examples fresh when fields change
        self._cam_cmd_header.textChanged.connect(self._refresh_camera_preview)
        self._cam_cmd_template.textChanged.connect(self._refresh_camera_preview)
        self._cam_resp_header.textChanged.connect(self._refresh_camera_resp_example)
        self._cam_resp_field.valueChanged.connect(self._refresh_camera_resp_example)

        # ── Manual Test ──────────────────────────────────────────────────
        test_group = QGroupBox("Manual Slew Test")
        test_layout = QHBoxLayout(test_group)
        test_layout.addWidget(QLabel("Test bearing:"))
        self._cam_test_brg = QSpinBox()
        self._cam_test_brg.setRange(0, 359)
        self._cam_test_brg.setValue(45)
        self._cam_test_brg.setSuffix("°")
        test_layout.addWidget(self._cam_test_brg)
        send_test_btn = QPushButton("Send Test Command")
        send_test_btn.clicked.connect(self._send_camera_test)
        test_layout.addWidget(send_test_btn)
        self._cam_test_status = QLabel("")
        self._cam_test_status.setStyleSheet(
            "color: #FFAA00; font-family: Consolas; font-size: 10px;"
        )
        test_layout.addWidget(self._cam_test_status)
        test_layout.addStretch()
        outer.addWidget(test_group)

        outer.addStretch()
        return widget

    def _refresh_camera_preview(self):
        """Rebuild the command preview label from current template fields."""
        header   = self._cam_cmd_header.text().strip() or 'PCAM'
        template = self._cam_cmd_template.text().strip() or '$[HDR],[BRG]*[CHK]'
        brg_str  = "045.30"
        msg = template.replace('[HDR]', header).replace('[BRG]', brg_str)
        if '$' in msg and '*' in msg:
            body = msg[msg.index('$') + 1: msg.index('*')]
            msg  = msg.replace('[CHK]', nmea_checksum(body))
        else:
            msg = msg.replace('[CHK]', '')
        self._cam_preview.setText(msg.strip())

    def _refresh_camera_resp_example(self):
        """Rebuild the example response label."""
        hdr   = self._cam_resp_header.text().strip() or 'PCAMR'
        field = self._cam_resp_field.value()
        # Build a generic example sentence
        fields = ['---'] * max(field, 1)
        fields[field - 1] = '045.30'
        body = hdr + ',' + ','.join(fields)
        chk  = nmea_checksum(body)
        self._cam_resp_example.setText(
            f"${body}*{chk}   "
            f"→ azimuth read from field {field}"
        )

    def _send_camera_test(self):
        """Send a one-off test command using the current dialog settings."""
        from core.camera_controller import CameraController
        tmp = CameraController()
        tmp.config.update(self._collect_camera_config())
        tmp.config['enabled'] = True
        bearing = float(self._cam_test_brg.value())
        msg = tmp.build_command(bearing)
        self._cam_test_status.setText(f"Sent: {msg.strip()}")

        host = tmp.config['host']
        port = int(tmp.config['send_port'])
        import socket as _socket
        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            sock.sendto(msg.encode('ascii', errors='replace'), (host, port))
            sock.close()
            self._cam_test_status.setText(
                f"Sent to {host}:{port} → {msg.strip()}"
            )
        except Exception as exc:
            self._cam_test_status.setText(f"Error: {exc}")

    def _collect_camera_config(self) -> dict:
        """Read all camera UI fields into a config dict."""
        return {
            'enabled':                self._cam_enabled.isChecked(),
            'host':                   self._cam_host.text().strip(),
            'send_port':              self._cam_send_port.value(),
            'listen_port':            self._cam_listen_port.value(),
            'bearing_mode':           self._cam_bearing_mode.currentData(),
            'cmd_header':             self._cam_cmd_header.text().strip(),
            'cmd_template':           self._cam_cmd_template.text().strip(),
            'response_header':        self._cam_resp_header.text().strip(),
            'response_bearing_field': self._cam_resp_field.value(),
        }

    def add_source(self, table, source_type):
        """Add a new source to the table"""
        row = table.rowCount()
        table.insertRow(row)
        
        # Name
        name = QLineEdit(f"{source_type} {row + 1}")
        table.setCellWidget(row, 0, name)
        
        # Listen Address
        ip = QLineEdit("0.0.0.0")
        table.setCellWidget(row, 1, ip)
        
        # Port
        port = QSpinBox()
        port.setRange(1, 65535)
        port.setValue(10110 + row)
        table.setCellWidget(row, 2, port)
        
        # Priority
        priority = QSpinBox()
        priority.setRange(1, 10)
        priority.setValue(row + 1)
        table.setCellWidget(row, 3, priority)
        
        # Enabled checkbox
        enabled = QCheckBox()
        enabled.setChecked(True)
        table.setCellWidget(row, 4, enabled)
        
        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(lambda: self.delete_source(table, row))
        table.setCellWidget(row, 5, delete_btn)
        
    def delete_source(self, table, row):
        """Delete a source from the table"""
        table.removeRow(row)
        
    def load_sources(self):
        """Load sources from configuration"""
        for source_type, table in [
            ('gps', self.gps_table),
            ('heading', self.heading_table),
            ('depth', self.depth_table),
            ('ais', self.ais_table),
            ('adsb', self.adsb_table),
        ]:
            if source_type in self.config:
                for source in self.config[source_type]:
                    row = table.rowCount()
                    table.insertRow(row)
                    
                    # Name
                    name = QLineEdit(source.get('name', ''))
                    table.setCellWidget(row, 0, name)
                    
                    # Listen Address (support legacy 'ip' key)
                    addr = source.get('listen_address', source.get('ip', '0.0.0.0'))
                    ip = QLineEdit(addr)
                    table.setCellWidget(row, 1, ip)
                    
                    # Port
                    port = QSpinBox()
                    port.setRange(1, 65535)
                    port.setValue(source.get('port', 10110))
                    table.setCellWidget(row, 2, port)
                    
                    # Priority
                    priority = QSpinBox()
                    priority.setRange(1, 10)
                    priority.setValue(source.get('priority', 1))
                    table.setCellWidget(row, 3, priority)
                    
                    # Enabled
                    enabled = QCheckBox()
                    enabled.setChecked(source.get('enabled', True))
                    table.setCellWidget(row, 4, enabled)
                    
                    # Delete button
                    delete_btn = QPushButton("Delete")
                    delete_btn.clicked.connect(lambda r=row, t=table: self.delete_source(t, r))
                    table.setCellWidget(row, 5, delete_btn)
                    
    def get_table_data(self, table):
        """Extract data from table"""
        sources = []
        for row in range(table.rowCount()):
            addr = table.cellWidget(row, 1).text().strip()
            source = {
                'name': table.cellWidget(row, 0).text(),
                'listen_address': addr,
                'ip': addr,  # backward-compat alias
                'port': table.cellWidget(row, 2).value(),
                'priority': table.cellWidget(row, 3).value(),
                'enabled': table.cellWidget(row, 4).isChecked()
            }
            sources.append(source)
        return sources
        
    def save_config_and_close(self):
        """Save configuration and close dialog"""
        self.config = {
            'gps':     self.get_table_data(self.gps_table),
            'heading': self.get_table_data(self.heading_table),
            'depth':   self.get_table_data(self.depth_table),
            'ais':     self.get_table_data(self.ais_table),
            'adsb':    self.get_table_data(self.adsb_table),
            'camera':  self._collect_camera_config(),
        }
        
        self.save_config()
        
        QMessageBox.information(self, "Configuration Saved",
                               "NMEA source configuration has been saved.\n\n"
                               "Restart the application for changes to take effect.")
        self.accept()
        
    def load_config(self):
        """Load configuration from file"""
        config_file = 'nmea_config.json'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Error loading config: %s", e)
        
        # Default configuration for Perle IOLAN terminal servers
        return {
            'gps': [
                {'name': 'GPS 1', 'listen_address': '0.0.0.0', 'ip': '0.0.0.0',
                 'port': 10110, 'priority': 1, 'enabled': True}
            ],
            'heading': [
                {'name': 'Gyro 1', 'listen_address': '0.0.0.0', 'ip': '0.0.0.0',
                 'port': 10111, 'priority': 1, 'enabled': True}
            ],
            'depth': [
                {'name': 'Depth 1', 'listen_address': '0.0.0.0', 'ip': '0.0.0.0',
                 'port': 10112, 'priority': 1, 'enabled': True}
            ],
            'ais': [
                {'name': 'AIS 1', 'listen_address': '0.0.0.0', 'ip': '0.0.0.0',
                 'port': 10113, 'priority': 1, 'enabled': True}
            ],
            'adsb': [
                {'name': 'ADS-B 1', 'listen_address': '0.0.0.0', 'ip': '0.0.0.0',
                 'port': 10117, 'priority': 1, 'enabled': True}
            ]
        }
        
    def save_config(self):
        """Save configuration to file"""
        config_file = 'nmea_config.json'
        try:
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")
            
    def test_connections(self):
        """Test all configured connections"""
        # This would actually try to connect to each source
        QMessageBox.information(self, "Connection Test",
                               "Connection test feature would check each configured source.\n\n"
                               "This is a placeholder for production implementation.")
        
    def get_config(self):
        """Get current configuration"""
        return self.config
