# Marine Radar GUI Application

Professional ARPA-compliant radar display and control application for maritime radar systems. Follows IMO Resolution A.823(19), IEC 62388, and SN.1/Circ.243/Rev.2 display conventions.

## Features

### Display Modes (IMO Compliant)
- **Day** — High contrast, bright colors for daylight operation
- **Dusk** — Medium contrast for twilight conditions
- **Night** — Low intensity green phosphor style
- **Red Night** — Red-only for dark adaptation preservation

### Orientation Modes
- **North-Up** — North always at top (default)
- **Head-Up** — Own ship heading at top
- **Course-Up** — Own ship course at top
- **True Motion** — Own ship moves, chart stationary; auto-resets at 75% of range

### Target Tracking (ARPA / AIS / ADS-B)

#### ARPA Radar Targets
- Displayed as **green circles**
- Orange caution and red dangerous at CPA/TCPA threshold crossings
- 500 ms blink for critical and warning targets

#### AIS Targets
- **Unencrypted AIS** — green triangles (standard surface traffic)
- **Encrypted SA-AIS** — blue triangles (friendly / secure; decrypted using configured AES key)
- **Dangerous / hostile** — red flashing triangles regardless of encryption status
- AIS Base Stations (Type 4) — teal hollow squares; not forwarded to track manager

#### ADS-B Aircraft Targets
- Displayed as **cyan directional triangles** rotated to face the aircraft's track
- Alarm level coloring: cyan (normal) → yellow (caution) → red flashing (urgent)
- ICAO hex address label above symbol; relative altitude (±m) below
- Speed vector indicating track and ground speed
- 15-second stale-target pruning

#### Tracking Features
- **CPA/TCPA** calculations for all surface targets
- **Threat assessment** — safe / caution / warning / critical risk tiers
- **Click-to-select** — click any target for the full detail panel
- **Kalman filtering** for smooth radar track positions
- **Hide stationary / moored AIS** — operator toggle to suppress anchored and moored vessels (speed < 0.5 kts); threats and selected targets always remain visible
- **Anchor Watch** — Monitor own-ship position against a fixed anchor point with configurable swing radius

### Priority-Tiered Track Correlation
Radar/AIS correlation uses a spatial grid index and proximity-based priority scheduling:
- **Spatial grid index** — AIS targets bucketed into 0.3 NM cells; radar tracks search only their 3×3 cell neighbourhood (O(n×m) → O(n×k))
- **CRITICAL tier (< 1.5 NM)** — correlated every update cycle
- **NEAR tier (1.5–3 NM)** — correlated every 2nd cycle (~5 Hz)
- **FAR tier (> 3 NM)** — correlated every 5th cycle (~2 Hz); previous result carried forward on skipped cycles

### Navigation Data (NMEA-0183)
- **Multi-source UDP input** with priority-based failover
- Rate-agnostic parser — handles mixed rates (e.g. 10 Hz position, 2 Hz depth, 1 Hz time)
- AIS target ingestion (AIVDM / AIVDO) with full ITU-R M.1371 decoding
- **NMEA data staleness indicators** — labels in the Own Ship panel turn **red** when a sensor has not sent data for more than 10 seconds, giving the operator immediate visibility of any offline instrument
- **NMEA Monitor** (Tools > NMEA Monitor) — live raw sentence viewer with source selector, Play/Stop, scroll, and Clear

#### Supported NMEA-0183 Sentences

| Sentence | Description | Typical Rate |
|----------|-------------|--------------|
| **GGA** | GPS Fix — latitude, longitude, quality, satellites | 1–10 Hz |
| **GLL** | Geographic Position — latitude, longitude | 1–10 Hz |
| **RMC** | Recommended Minimum — position, SOG, COG, UTC time/date | 1 Hz |
| **VTG** | Course Over Ground and Ground Speed | 1–10 Hz |
| **HDT** | True Heading | 1–10 Hz |
| **HDG** | Heading with magnetic deviation/variation (auto-corrected to true) | 1–10 Hz |
| **DBT** | Depth Below Transducer (feet, meters, fathoms) | 1–2 Hz |
| **DPT** | Depth of Water | 1–2 Hz |
| **ZDA** | UTC Time & Date (year, month, day, timezone) | 1 Hz |
| **ROT** | Rate of Turn (deg/min) | 1–2 Hz |
| **VHW** | Water Speed and Heading through water (STW) | 1–2 Hz |
| **MWV** | Wind Speed and Angle (relative or true, auto-converts units) | 1 Hz |
| **MTW** | Water Temperature (Celsius, auto-converts from Fahrenheit) | 0.1–1 Hz |
| **RSA** | Rudder Sensor Angle (logged) | 1 Hz |
| **XTE** | Cross Track Error (logged) | 1 Hz |
| **GSA** | GPS DOP and Active Satellites (accepted, no action) | 1 Hz |
| **GSV** | Satellites in View (accepted, no action) | 1 Hz |
| **AIVDM** | AIS VHF Data-link Message (Class A/B targets) | varies |
| **AIVDO** | AIS Own-vessel Report | varies |

All talker IDs accepted (GP, GN, GL, GA, HE, HC, SD, WI, YX, AG, etc.). Checksum verification performed on all sentences.

#### AIS Message Types Decoded

| Type | Description |
|------|-------------|
| **1, 2, 3** | Class A Position Report (MMSI, SOG, COG, heading, lat/lon, nav status) |
| **4** | Base Station Report (MMSI, lat/lon) — teal hollow squares; not forwarded to track manager |
| **5** | Class A Static/Voyage Data (name, call sign, ship type, destination) |
| **18** | Class B Position Report |
| **24** | Class B Static Data (parts A and B) |

### ADS-B / FLARM Aircraft Tracking
Receives FLARM-standard NMEA sentences over UDP from any compatible ADS-B receiver (Stratux, dump1090, OpenSky feeder, or FLARM device):

| Sentence | Description |
|----------|-------------|
| **$PFLAA** | Traffic position record — relative N/E/vertical offset, ICAO ID, track, speed, alarm level, aircraft type |
| **$PFLAU** | Receiver status — GPS fix, receive count, alarm level |

**Position conversion:** `$PFLAA` positions are receiver-relative (metres). The application converts to absolute lat/lon using own ship's GPS: `tgt_lat = own_lat + RelN / 111320`. Own ship GPS must be active.

**Aircraft type codes:** Unknown (0), Glider (1), Tow (2), Helicopter (3), Parachute (4), Drop plane (5), Hang-glider (6), Paraglider (7), Piston (8), Jet (9), Balloon (11), Airship (12), UAV (13), Static obstacle (15).

Configure sources via **Settings > NMEA Sources > ADS-B Sources** tab. Default UDP port: **10117**.

### Encrypted AIS (SA-AIS)
- AES-128-CBC and AES-256-CBC decryption of Secure AIS payloads
- Uses the `cryptography` library backed by OpenSSL 3.x (FIPS 140-3 capable)
- Key management dialog (Settings > Encrypted AIS Keys)
- Keys entered in HEX or ASCII with live bidirectional conversion
- Auto-detection of cipher from key length (32 hex = AES-128, 64 hex = AES-256)
- Decrypted SA-AIS targets displayed as **blue triangles** with "F" tag
- Keys persisted to `ais_encrypt_config.json`

### PTZ Camera Control
Slew a Pan/Tilt/Zoom camera to any AIS or ARPA target via NMEA-style UDP commands:

- **Bearing Mode:** True °T (for cameras with a built-in gyro/compass) or Relative to ship heading °R (for cameras without a gyro)
- **Configurable NMEA template:** `$[HDR],[BRG]*[CHK]` with custom message header, standard XOR checksum
- **Camera response parser:** configurable response header and field index for the returned azimuth value
- **PPI line of bearing:** camera's current azimuth displayed as a bright cyan line extending 12 NM from own ship
- **"Slew Camera to Target"** in the right-click context menu for any AIS or ARPA contact
- Configure via **Settings > NMEA Sources > Camera Control** tab

### Radar Standby / Transmit Control
A prominent **STBY / TX** toggle at the left end of the Radar Controls bar lets the operator command the radar between standby and transmit states:

- **STBY** (amber) — radar powered but not transmitting
- **TX** (bright green) — radar actively transmitting
- The button updates only when the radar hardware confirms the state change via `transmit_state_changed` signal, so it accurately reflects actual hardware state rather than operator intent
- Connects to `RadarInterface.set_transmit(bool)` — see [Radar SDK Integration](#radar-sdk-integration)

### Own Ship Data Panel
- **DATE / TIME** — UTC date and local time derived from NMEA ZDA; **double-click the time** to set the timezone offset (21 presets from UTC−12 to UTC+12, or custom entry)
- **POSN** — Latitude / Longitude (from GGA, RMC, GLL)
- **HDG** — True heading (from HDT, HDG, VHW)
- **SOG** — Speed Over Ground in knots (from RMC, VTG)
- **STW** — Speed Through Water in knots (from VHW)
- **DEPTH** — Depth below transducer (from DBT, DPT)
- **WTMP** — Water temperature in Celsius (from MTW)
- **WIND** — Wind angle and speed with R (relative) / T (true) indicator (from MWV)

Stale or offline labels are highlighted **red** for immediate fault visibility.

### Data Readout Area (PPI Overlay)
Fixed-position display in the top-left of the PPI showing:
- Orientation mode (N-UP, H-UP, C-UP, TM)
- Range scale (e.g. RNG: 12.0 NM) and ring interval (RI: 3.00 NM)
- Cursor bearing, range, latitude, and longitude
- **Closest CPA summary** — Top 3 tracks sorted by CPA distance with name, track ID, CPA, TCPA, speed, and course, color-coded by risk level

### EBL / VRM (Electronic Bearing Line / Variable Range Marker)
- **EBL1 / EBL2** — Dashed bearing lines from center, draggable to any angle
- **VRM1 / VRM2** — Dashed range circles, draggable to any radius
- Toggle via View > EBL/VRM menu or keyboard shortcuts
- Live bearing/range readout in status bar

### Audible Alarms
- **CPA Critical** — Rapid high-frequency beep for collision-imminent targets
- **CPA Warning** — Medium beep for close-approach targets
- **Guard Zone Intrusion** — Double beep when a target enters a guard zone
- **GPS Spoofing** — Alternating warble when spoofing is detected
- **Sensor Loss** — Low-frequency slow beep when GPS, heading, or depth source goes offline
- **Anchor Drag** — Slow double-beep when own ship drifts outside the configured swing radius
- Per-alarm acknowledge buttons with flash animation — **each press of S (or clicking ACK) acknowledges exactly one alarm**; subsequent alarms require separate acknowledgment to ensure operators are alerted to every condition
- New alarms that arrive after all existing ones are acknowledged will sound and flash until explicitly acknowledged — the S key never pre-silences future alarms
- Alarm history panel with timestamps
- Audio via in-memory WAV synthesis through the default sound card
- Global silence / un-silence via View menu or **F12** — automatically re-enables after **5 minutes** with a countdown shown in the status bar; ensures a silenced console cannot miss a new threat indefinitely
- All alarm events (triggered, acknowledged, silenced, cleared) are appended to **`logs/alarm_log.txt`** with timestamps for post-incident review and compliance records

### Right-Click Context Menu
- Target Info dialog with full detail
- Acquire/Track and Cancel Track (radar targets)
- Mark as Friendly / Neutral / Hostile with visual classification tags
- Set per-target CPA/TCPA alert thresholds
- Add to Guard Zone
- Calculate Intercept course/speed/time (COLREGS Rule 8 note)
- Set as Reference Target
- **Slew Camera to Target** — sends PTZ slew command (greyed out if camera control is disabled)

### Help Menu
**Help > PPI Symbols & Keyboard Shortcuts...** opens a reference dialog showing:
- Symbol legend: ARPA circle, unencrypted AIS triangle, encrypted SA-AIS triangle, ADS-B triangle, base station square, own ship, heading line, EBL, VRM, guard zone, camera bearing line
- Full keyboard shortcut reference table

### System Messages
- Accessible via **View > Panels > System Messages...** — opens a non-modal popup with the full timestamped log
- Non-modal popup allows continued radar operation while reviewing messages

---

## Installation

### Prerequisites

**Windows 11:**
```bash
python --version    # 3.9 or later required
```

**Red Hat Enterprise Linux:**
```bash
sudo dnf install python3 python3-pip python3-devel gcc-c++
```

### Install Application

```bash
git clone https://github.com/<your-org>/radar-gui.git
cd radar-gui

# Windows
python -m pip install -r requirements.txt

# Linux
python3 -m pip install -r requirements.txt
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | ≥ 6.4.0 | GUI framework |
| numpy | ≥ 1.24.0 | Numerical processing |
| cryptography | ≥ 42.0.0 | AES decryption for Secure AIS (OpenSSL 3.x backend) |

---

## Running the Application

### With Mock Radar Data (Testing)

```bash
# Windows
python main.py

# Linux
python3 main.py
```

### Sending Test NMEA Data

In a second terminal:
```bash
python test_nmea_sender.py
```

Sends simulated multi-rate NMEA data:
- **10 Hz** — GGA, VTG, HDT (position, speed over ground, heading)
- **2 Hz** — DBT, ROT, VHW (depth, rate of turn, speed through water)
- **1 Hz** — RMC, ZDA, MWV, GLL (recommended minimum, time/date, wind, position)
- **0.2 Hz** — MTW (water temperature)
- **0.33 Hz** — AIVDM position reports (5 normal AIS + 2 encrypted SA-AIS targets)
- **Startup** — AIS static/voyage data (vessel names, ship types, call signs)

### Testing ADS-B Input

Send a test $PFLAA sentence to UDP port 10117 using any UDP sender:
```
$PFLAA,0,1000,500,180,1,ABCDEF,045,,52,0,8*<checksum>
```
A cyan directional triangle should appear approximately 1 km NNE of own ship.

---

## Configuration

### NMEA Sources
**Settings > NMEA Sources** — Configure multiple UDP input sources for GPS, Heading, Depth, AIS, and ADS-B data with priority-based failover.

Default UDP ports:

| Source | Default Port |
|--------|-------------|
| GPS | 10110 |
| Heading / Gyro | 10111 |
| Depth | 10112 |
| AIS | 10113 |
| ADS-B / FLARM | 10117 |
| Camera Command (send) | 10120 |
| Camera Response (listen) | 10121 |

### PTZ Camera
**Settings > NMEA Sources > Camera Control** tab:
- Enable camera control
- Camera host IP, send port (command), listen port (response)
- **Bearing Mode:** Relative °R (no gyro) or True °T (gyro-stabilised)
- NMEA message template (`$[HDR],[BRG]*[CHK]`) with live preview
- Response header and azimuth field index
- Manual slew test

### Encrypted AIS Keys
**Settings > Encrypted AIS Keys** — Add, edit, or remove AES keys. Keys persisted to `ais_encrypt_config.json`.

### CPA/TCPA Thresholds
**Settings > CPA/TCPA Thresholds**:
- **Threat detection gate** — outer boundary (default: 2.0 NM / 12 min)
- **Critical** — triggers fast audible alarm (default: 0.5 NM / 6 min)
- **Warning** — triggers audible alarm (default: 1.0 NM / 12 min)
- **Caution** — visual color change only (default: 2.0 NM / 20 min)

---

## Controls

### Window Management (Frameless Mode)
The main window runs without an OS title bar for a clean full-screen radar presentation:

| Action | How |
|--------|-----|
| **Move window** | Click and drag on any empty area of the menu bar (between menu labels and the ─ ⬜ ✕ buttons) |
| **Maximize / Restore** | Double-click the empty menu bar area, or click **⬜** |
| **Minimize** | Click **─** in the top-right corner of the menu bar |
| **Close** | Click **✕** (turns red on hover) or use **Ctrl+Q** |
| **Resize** | Drag the grip in the bottom-right corner of the status bar; or use Windows snap (Win+Arrow) |

### Top Control Bar

| Control | Options / Range | Description |
|---------|-----------------|-------------|
| **STBY / TX** | Toggle | Radar standby / transmit command |
| **Radar** | Configured units | Active radar selection |
| **Range** | 0.5 – 96 NM | Display range |
| **Display** | Day / Dusk / Night / Red Night | IMO display mode |
| **Orient** | N-Up / H-Up / C-Up / True Motion | Orientation mode |
| **Video** | Processed / Raw | Radar video mode |
| **Gain** | 0 – 100% | Receiver gain |
| **Sea** | 0 – 100% | Sea clutter (STC) rejection |
| **Rain** | 0 – 100% | Rain clutter (FTC) rejection |
| **AIS** | Toggle | Show / hide AIS surface targets |
| **ADSB** | Toggle | Show / hide ADS-B aircraft targets |
| **Tracks** | Toggle | Show / hide ARPA tracks |
| **Trails** | Toggle | Show / hide past-position trails |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **+** / **=** | Increase display range |
| **−** | Decrease display range |
| **Z** | Range in (zoom in one step) |
| **X** | Range out (zoom out one step) |
| **S** | Acknowledge next unacknowledged alarm (one at a time, in display order) |
| **D** | Cycle display mode (Day › Dusk › Night › Red Night) |
| **O** | Cycle orientation (N-Up › H-Up › C-Up › True Motion) |
| **A** | Toggle AIS targets |
| **B** | Toggle ADS-B targets |
| **T** | Toggle ARPA tracks |
| **L** | Toggle past-position trails |
| **G** | Toggle guard zones |
| **R** | Toggle range rings |
| **F1** | Toggle EBL1 |
| **F2** | Toggle EBL2 |
| **F3** | Toggle VRM1 |
| **F4** | Toggle VRM2 |
| **F12** | Silence / un-silence all alarms (auto-re-enables after 5 minutes) |
| **Ctrl+Q** | Exit application |

### Settings Menu
- **Radar** — Radar unit configuration
- **NMEA Sources** — Multi-source UDP input (GPS, Heading, Depth, AIS, ADS-B, Camera Control)
- **Guard Zones** — Guard zone boundary configuration
- **Encrypted AIS Keys** — AES key management for SA-AIS decryption
- **CPA/TCPA Thresholds** — Threat detection gate and risk-tier boundaries

### Tools Menu
- **Built-In Test (BIT)** — Radar subsystem fault status panel with 1 Hz auto-polling and a fault log. Hardware indicators (transmitter, motor, temperature, receiver, power supply) require a real radar SDK. The following **software self-tests run immediately without any hardware**:
  - **CONFIG FILES** — verifies `config/nmea_config.json` and `config/ais_encrypt_config.json` are present and contain valid JSON
  - **ALARM LOG** — verifies the `logs/` directory and alarm log file are writable
  - **GPS INPUT / HEADING INPUT** — live NMEA parser source status (green = source active)
  - **GPS SPOOFING** — live spoofing detector state
  - **Run Full Test** — executes all checks and prints per-item PASS/FAIL detail to the fault log
  - **Test Alarm Audio** — plays a tone through the default audio device immediately, bypassing any silenced or acknowledged alarm state; use to verify audio output before a voyage
- **NMEA Monitor** — Live raw NMEA-0183 sentence viewer with source selector, Play/Stop, scroll, and Clear

### View Menu
- Show AIS Targets
- **Show Moored / Stationary AIS** — Hide anchored/moored vessels (speed < 0.5 kts); threats always shown
- **Show AIS Base Stations** — Teal hollow squares for AIS Type 4 shore-based transmitters
- **Show ADS-B Targets** — Toggle ADS-B aircraft display
- **Anchor Watch...** — Own-ship swing-radius position monitoring
- Show Tracks / Show Guard Zones
- Range Rings (show/hide, count, reset)
- Trail Length (1 / 3 / 6 / 15 / 30 min)
- EBL/VRM (EBL1, EBL2, VRM1, VRM2)
- **Panels** submenu — floating popup windows for secondary data:
  - **AIS Targets...** — Live list of first 10 AIS vessels (name, MMSI, COG, SOG); updates automatically while open
  - **System Messages...** — Full timestamped system event log
- Silence Alarms (F12 global toggle)

### Help Menu
- **PPI Symbols & Keyboard Shortcuts...** — Symbol legend and keyboard reference

### Right Panel (Navigation & System Data)
- **OWN SHIP** — Date/time (double-click to set timezone), Position, HDG, SOG, STW, DEPTH, WTMP, WIND; stale labels shown in red
- **NMEA SOURCES** — Active GPS, heading, depth sources
- **RADAR STATUS** — Operating status, target and AIS counts
- **SELECTED TARGET** — Full detail for the clicked target
- **ALARMS** — Active and recent alarms with per-alarm ACK buttons

> AIS Targets and System Messages are available as floating popups via **View > Panels** to keep the main display uncluttered.

---

## Anchor Watch

**View > Anchor Watch...** monitors own-ship position against a fixed anchor point.

1. Click **Refresh Targets** — combo boxes populate with stationary radar tracks (speed < 1.0 kts)
2. Optionally select 1–3 stationary reference targets (landmarks, buoys, fixed structures)
3. Set **Swing Radius** (0.01–2.00 NM, default 0.10 NM ≈ 185 m)
4. Click **Activate Watch** — own-ship GPS position is recorded; 1 Hz monitoring begins
5. A dashed **gold circle** appears on the PPI centred on the anchor with an anchor cross symbol

**While active:**
- Drift label colour: green (< 50% radius), amber (50–100%), red (dragging)
- **Anchor Drag** audible alarm fires (slow double-beep, 1000 Hz) when drift exceeds the swing radius

Click **Deactivate** or close the dialog to stop monitoring.

---

## Known Limitations

The following features are present in the codebase but are stubs, placeholders, or limited by the mock radar interface:

### Mock Radar Interface (Primary Limitation)
All radar data — sweep video, ARPA targets, and radar control responses — is **simulated** by `MockRadarInterface`. The three simulated vessels are hardcoded; range, gain, and clutter controls are accepted and logged but have no effect on the data. Replace with a real SDK implementation when hardware is available (see [Radar SDK Integration](#radar-sdk-integration)).

### Built-In Test (BIT) Window
Hardware indicators (transmitter, motor, temperature, receiver, power supply, signal processor, display) will always report OK when running with the mock radar — the mock interface does not supply fault status. Five software self-tests (config file integrity, alarm log writability, GPS source, heading source, GPS spoofing) are fully functional without any hardware and update at 1 Hz. Full hardware fault detection requires a real SDK that implements `get_status()`.

### Plugin System (`core/plugin_system.py`)
Three example plugin classes are included as development scaffolding but contain no real implementation:
- **RecordingPlugin** — File handles open and close correctly, but no radar data is ever written to disk (`pass` in the write loop)
- **TargetClassificationPlugin** — ML classification hook; returns data unchanged
- **WeatherOverlayPlugin** — Weather data merge hook; no data source connected

Plugins are not exposed through the application UI.

### Test Scenarios (`core/test_scenarios.py`)
An automated CPA/TCPA validation test runner is included but has no UI entry point and is not reachable from the running application. It can be executed directly from a Python prompt for development validation.

### Satellite Quality Sentences
GSA (GPS DOP / fix mode) and GSV (satellites in view) sentences are received and verified but their content is discarded. Satellite count and dilution-of-precision data are not currently displayed or used for position confidence assessment.

---

## Radar SDK Integration

The application is **ready for radar SDK integration**. A mock radar interface is used until the SDK is connected.

### Integration Point

**File:** `core/radar_interface.py`

Contains:
1. `RadarInterface` — Abstract base class defining the full radar API
2. `MockRadarInterface` — Current mock implementation for testing

### Abstract Methods to Implement

| Method | Description |
|--------|-------------|
| `start()` | Initialize SDK, connect to radar, start acquisition |
| `stop()` | Stop acquisition, disconnect, cleanup SDK |
| `set_range(range_nm)` | Set display range in nautical miles |
| `set_gain(gain_percent)` | Set receiver gain 0–100% |
| `set_sea_clutter(value)` | Set STC (Sensitivity Time Control) 0–100% |
| `set_rain_clutter(value)` | Set FTC (Fast Time Constant) 0–100% |
| `set_video_mode(mode)` | Set `'raw'` or `'processed'` video mode |
| `set_transmit(transmitting)` | Command radar to transmit (`True`) or standby (`False`) |
| `get_radar_data()` | Return dict with `video`, `targets`, `sweep_angle` |

### Signals

| Signal | Type | Description |
|--------|------|-------------|
| `radar_data_updated` | `dict` | Emitted when new radar video data is available |
| `transmit_state_changed` | `bool` | Emit from the SDK callback when hardware confirms state change — the STBY/TX GUI button updates from this signal, not from the command |

### How to Integrate

1. Place SDK files in a `radar_sdk/` directory
2. Create `core/radar_sdk_interface.py` subclassing `RadarInterface`
3. Implement all abstract methods using SDK calls
4. For `set_transmit()`: call `sdk.radar_set_transmit()` / `sdk.radar_set_standby()`, then emit `self.transmit_state_changed.emit(transmitting)` from the SDK's hardware confirmation callback
5. In `gui/main_window.py`, replace `MockRadarInterface` with `RadarSDKInterface`

See inline documentation in `core/radar_interface.py` for the full API contract and ctypes example.

---

## Application Architecture

```
radar_gui/
├── main.py                          # Entry point with auto dependency check
├── requirements.txt                 # PyQt6, numpy, cryptography
├── test_nmea_sender.py              # Simulated NMEA + AIS data generator
├── README.md
├── QUICKSTART.md
├── gui/
│   ├── main_window.py               # Main window, menus, controls, shortcuts, alarm wiring
│   ├── ppi_display.py               # PPI display — sweep, ARPA, AIS, ADS-B, camera line, EBL/VRM
│   ├── color_themes.py              # IMO color themes (Day / Dusk / Night / Red Night)
│   ├── target_panel.py              # Selected target detail panel (CPA, TCPA, risk)
│   ├── alarm_widget.py              # Alarm history strip with per-alarm ACK buttons
│   ├── nmea_config_dialog.py        # NMEA source configuration (all source types + camera)
│   ├── radar_config_dialog.py       # Radar unit configuration dialog
│   ├── guard_zone_dialog.py         # Guard zone configuration dialog
│   ├── ais_encrypt_dialog.py        # Encrypted AIS key management (AES-128/256-CBC)
│   ├── cpa_settings_dialog.py       # CPA/TCPA threshold configuration dialog
│   ├── bit_window.py                # Built-In Test diagnostic window
│   ├── nmea_monitor_dialog.py       # Live NMEA-0183 sentence monitor (Tools menu)
│   └── anchor_watch_dialog.py       # Anchor Watch — swing-radius position monitoring
├── core/
│   ├── logger.py                    # Centralized logging configuration
│   ├── alarm_manager.py             # Audible alarm controller (6 alarm types, WAV synthesis)
│   ├── ais_decrypt.py               # AES-CBC decryption engine for Secure AIS (SA-AIS)
│   ├── multi_source_nmea_parser.py  # Multi-source NMEA-0183 parser + AIS decoder
│   ├── track_manager.py             # Track correlation, CPA/TCPA, classification, trails
│   ├── radar_interface.py           # Abstract radar API + mock (SDK integration point)
│   ├── camera_controller.py         # PTZ camera — NMEA slew commands + azimuth response
│   ├── adsb_receiver.py             # ADS-B / FLARM NMEA receiver ($PFLAA / $PFLAU)
│   ├── cpa_calculator.py            # CPA/TCPA calculations, intercept calculator
│   ├── track_filter.py              # Kalman and Alpha-Beta track filters
│   ├── guard_zone.py                # Guard zone definitions and intrusion detection
│   ├── gps_spoofing_detector.py     # GPS spoofing detection (time jumps, speed, position)
│   ├── plugin_system.py             # Plugin architecture for extensibility
│   ├── performance_monitor.py       # System performance metrics (FPS, CPU, memory, data rates)
│   ├── radar_logger.py              # Radar / NMEA / system event logger for replay/diagnostics
│   ├── radar_performance.py         # Radar RF performance analyser (SNR, interference)
│   ├── system_watchdog.py           # System component health monitor with alarm integration
│   └── test_scenarios.py            # Automated CPA/TCPA test scenarios
└── radar_sdk/                       # (Create for SDK integration)
    ├── radar_sdk.dll / .so
    └── radar_sdk.h
```

---

## Troubleshooting

### Application won't start
```bash
python --version    # Must be 3.9+
pip install --force-reinstall -r requirements.txt
```

### No NMEA data updating
- Verify the NMEA source is sending UDP to the configured port (default GPS: 10110)
- Check firewall settings — UDP ports must be open
- Test with `python test_nmea_sender.py`
- Check **Settings > NMEA Sources** configuration

### Own Ship panel labels are red
A red label means no data has been received from that sensor for more than 10 seconds. Check the corresponding NMEA source and network connection.

### ADS-B targets not appearing
- Confirm the ADS-B receiver is outputting $PFLAA sentences to the configured UDP port (default 10117)
- Own ship GPS must be active — ADS-B positions are relative and require own ship lat/lon to convert
- Check **Settings > NMEA Sources > ADS-B Sources** tab

### No alarm sounds
- Ensure the default audio output device is configured in Windows Sound settings
- Alarms use WAV synthesis through the default sound card (not the legacy PC speaker)
- Check **View > Silence Alarms** is not checked

### Camera bearing line not visible
- Enable camera control in **Settings > NMEA Sources > Camera Control**
- Confirm the camera is returning $PFLAA-style response sentences on the listen port
- Check bearing mode (True vs Relative) matches your camera hardware

### Display issues
- Update graphics drivers
- Try a different display mode (Day vs Night)

---

## Version History

**v4.2** — Frameless window and BIT / alarm hardening: OS title bar removed; window controls (─ ⬜ ✕) integrated into the right side of the menu bar; drag-to-move from the empty menu bar area; double-click to maximize/restore; resize grip in status bar corner. BIT window made partially functional without radar hardware — CONFIG FILES and ALARM LOG self-tests poll at 1 Hz, Run Full Test prints per-check PASS/FAIL detail, Test Alarm Audio button plays a tone immediately bypassing any silenced alarm state. F12 global silence now auto-re-enables after **5 minutes** with a status bar countdown. All alarm events (triggered, acknowledged, silenced, cleared) appended to `logs/alarm_log.txt` for post-incident review.

**v4.1** — UI readability and alarm safety improvements: AIS Targets and System Messages moved to floating popups under **View > Panels** submenu to keep the main display clean; **S key alarm acknowledgment** changed to sequential one-alarm-at-a-time behavior (operators must consciously confirm each alarm — new alarms always sound and flash regardless of prior acknowledgments); Navigation & System Data panel and Target Data panel text scaled up for improved at-a-glance readability; NMEA Sources dialog Delete button fixed (column width and minimum button size); non-functional "Test Connections" button removed from NMEA Sources dialog; Known Limitations section added to README documenting stub/placeholder features (mock radar, BIT window, plugin system, test scenarios).

**v4.0** — ADS-B / FLARM integration ($PFLAA/$PFLAU UDP receiver, cyan directional triangles, alarm-level color coding, stale-target pruning); PTZ camera control (NMEA-style slew commands via UDP, configurable message template, True/Relative bearing mode, 12 NM PPI bearing line, "Slew Camera to Target" right-click action); Radar Standby/Transmit toggle (STBY/TX button, amber/green color coding, `set_transmit()` SDK hook, `transmit_state_changed` hardware-confirmation signal); AIS target color coding update (unencrypted AIS = green, encrypted SA-AIS = blue); NMEA data staleness indicators (sensor labels turn red after 10 s without data); time/date display in Own Ship panel with double-click timezone configuration (21 presets); keyboard shortcuts updated (S = alarm ACK, Z = range in, X = range out, B = toggle ADS-B); Help > PPI Symbols & Keyboard Shortcuts reference dialog.

**v3.7** — Anchor Watch (View > Anchor Watch...): 1 Hz own-ship position monitoring against a fixed anchor point with configurable swing radius (0.01–2.00 NM); select up to 3 stationary radar reference targets; audible anchor drag alarm (slow double-beep, 1000 Hz) and dashed gold PPI overlay circle when ship drifts outside swing radius; auto-deactivates on dialog close.

**v3.6** — AIS Base Station display: decodes AIS Type 4 (Base Station Report) messages; renders shore-based transmitters (USCG, VTS, port authority) as teal hollow squares on the PPI; toggleable via View > Show AIS Base Stations. Base stations stored separately from vessel targets — no CPA, no Kalman, no correlation.

**v3.5** — NMEA Monitor (Tools > NMEA Monitor) for live raw sentence inspection; priority-tiered track correlation with spatial grid index (O(n×m) → O(n×k)); Show Moored / Stationary AIS toggle (View menu).

**v3.4** — IMO ARPA compliant display with EBL/VRM, audible alarms (WAV synthesis), keyboard shortcuts, right-click context menu, target classification, GPS spoofing detection, encrypted AIS decryption (AES-128/256-CBC via OpenSSL 3.x), full AIS decoder (ITU-R M.1371 Types 1/2/3/5/18/24), own-ship SOG/STW/water temp/wind display, CPA threat summary overlay, configurable CPA/TCPA alarm thresholds, thread-safe data access, graceful shutdown, system messages popup, centralized logging, expanded NMEA-0183 support (19 sentence types, multi-rate).
