# Quick Start Guide

## Installation (5 minutes)

### Windows 11

1. **Install Python** (if not already installed)
   - Download from https://python.org (Python 3.9 or later)
   - During installation, check "Add Python to PATH"

2. **Open Command Prompt** and navigate to the project folder:
   ```
   cd C:\path\to\radar_gui
   ```

3. **Install dependencies**:
   ```
   python -m pip install -r requirements.txt
   ```

### Red Hat Enterprise Linux

1. **Install Python and build tools**:
   ```bash
   sudo dnf install python3 python3-pip python3-devel gcc-c++
   ```

2. **Navigate to the project folder**:
   ```bash
   cd /path/to/radar_gui
   ```

3. **Install Python packages**:
   ```bash
   python3 -m pip install -r requirements.txt
   ```

---

## Running the Application

### Option 1: Test with Simulated Data (Recommended First Time)

**Terminal 1 — Start the application:**
```bash
# Windows
python main.py

# Linux
python3 main.py
```

**Terminal 2 — Send test NMEA data:**
```bash
# Windows
python test_nmea_sender.py

# Linux
python3 test_nmea_sender.py
```

You should see:
- Radar display with green sweep and rotating range rings
- Simulated ARPA targets (green circles) and AIS targets (green/blue triangles)
- Navigation data updating in the right panel (position, heading, SOG, STW, depth, water temp, wind)
- CPA threat summary in the top-left data readout area
- 5 standard AIS targets (green triangles) + 2 encrypted SA-AIS targets (blue triangles with "F" tag)

### Option 2: Connect to Real NMEA Sources

1. Go to **Settings > NMEA Sources** and configure your UDP input sources
2. Start the application — navigation data will populate as sentences arrive

---

## What You'll See

### Main Display (PPI)
- Green circular radar display with rotating sweep
- Range rings at 25%, 50%, 75%, 100% of selected range
- Compass directions with true bearing labels
- Own ship symbol at center (or moving in True Motion mode)
- **ARPA targets** — green circles (orange/red at increasing threat levels)
- **Unencrypted AIS targets** — green triangles
- **Encrypted SA-AIS targets** — blue triangles with "F" (friendly) tag
- **ADS-B aircraft** — cyan directional triangles rotated to face the aircraft's track
- **Camera bearing line** — bright cyan line showing PTZ camera azimuth (if enabled)
- Guard zone boundaries (dashed arcs, red when violated)
- Past-position trail dots behind moving targets

### Data Readout Area (Top-Left of PPI)
| Display | Example | Description |
|---------|---------|-------------|
| **N-UP** | `N-UP` | Current orientation mode |
| **RNG** | `12.0 NM` | Display range |
| **RI** | `3.00 NM` | Range ring interval |
| **BRG / RNG** | `045.0° / 3.2 NM` | Cursor bearing and range |
| **Lat / Lon** | `37.0012° / -76.3024°` | Cursor geographic position |
| **CLOSEST CPA** | 3 rows | Top 3 tracks by CPA, color-coded by risk |

### Top Control Bar
| Control | What It Does |
|---------|-------------|
| **STBY / TX** | Command radar to standby (amber) or transmit (green) |
| **Radar** | Select active radar unit |
| **Range** | Change display range (0.5 – 96 NM) |
| **Display** | Switch Day / Dusk / Night / Red Night mode |
| **Orient** | Switch N-Up / H-Up / C-Up / True Motion |
| **Video** | Switch Processed / Raw radar video |
| **Gain** | Adjust radar sensitivity (0–100%) |
| **Sea** | Sea clutter rejection (0–100%) |
| **Rain** | Rain clutter rejection (0–100%) |
| **AIS** | Toggle AIS surface target display |
| **ADSB** | Toggle ADS-B aircraft display |
| **Tracks** | Toggle ARPA track display |
| **Trails** | Toggle past-position trails |

### Right Panel
| Section | Contents |
|---------|----------|
| **OWN SHIP** | Date/time (double-click to set timezone), POSN, HDG, SOG, STW, DEPTH, WTMP, WIND — stale labels shown in red |
| **NMEA SOURCES** | Active GPS, heading, depth source names |
| **RADAR STATUS** | Operating status, ARPA and AIS target counts |
| **SELECTED TARGET** | Full detail when a target is clicked (CPA, TCPA, BRG, RNG, risk) |
| **AIS TARGETS** | List of nearby AIS vessels |
| **SYSTEM MESSAGES** | Timestamped system log (double-click for full popup) |
| **ALARMS** | Active and recent alarms with per-alarm ACK buttons |

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| **+** / **−** | Zoom in / out (increase / decrease range) |
| **Z** | Range in (one step) |
| **X** | Range out (one step) |
| **S** | Acknowledge active alarm |
| **D** | Cycle display mode |
| **O** | Cycle orientation mode |
| **A** | Toggle AIS targets |
| **B** | Toggle ADS-B targets |
| **T** | Toggle ARPA tracks |
| **L** | Toggle past-position trails |
| **G** | Toggle guard zones |
| **R** | Toggle range rings |
| **F1 – F4** | Toggle EBL1 / EBL2 / VRM1 / VRM2 |
| **F12** | Silence / un-silence all alarms |
| **Ctrl+Q** | Exit application |

### Settings Menu
| Menu Item | Description |
|-----------|-------------|
| **Radar** | Radar unit configuration |
| **NMEA Sources** | Configure UDP sources — GPS, Heading, Depth, AIS, ADS-B, Camera Control |
| **Guard Zones** | Configure guard zone boundaries |
| **Encrypted AIS Keys** | Add/edit AES keys for SA-AIS decryption |
| **CPA/TCPA Thresholds** | Configure CPA/TCPA alarm thresholds and risk tiers |

### Tools Menu
| Menu Item | Description |
|-----------|-------------|
| **Built-In Test** | Radar subsystem fault status panel |
| **NMEA Monitor** | Live raw NMEA-0183 sentence viewer — select source, Play/Stop, scroll |

### View Menu
- Show / hide AIS targets, ARPA tracks, guard zones, range rings
- **Show Moored / Stationary AIS** — uncheck to hide anchored/moored vessels (speed < 0.5 kts)
- **Show AIS Base Stations** — toggle teal hollow squares for VTS/USCG transmitters (Type 4)
- **Show ADS-B Targets** — toggle ADS-B aircraft display
- **Anchor Watch...** — own-ship swing-radius position monitoring
- Set trail length (1, 3, 6, 15, or 30 minutes)
- EBL/VRM toggles; Silence Alarms

### Help Menu
- **PPI Symbols & Keyboard Shortcuts...** — symbol legend and full keyboard reference

---

## Testing the Application

1. **Start the application** — should open without errors
2. **Start NMEA sender** — Own Ship panel should update (position, heading, SOG, STW, depth, water temp, wind)
3. **Check sensor labels** — all labels should be normal color; stop the sender and verify they turn red after ~10 seconds
4. **Check date/time** — date and local time should display in the Own Ship panel; double-click time to change timezone
5. **Check AIS targets** — green triangles should appear on the PPI; 2 encrypted targets appear as blue triangles with "F"
6. **Check CPA summary** — top-left data readout should show closest CPA tracks
7. **Switch display modes** — try Day, Dusk, Night, Red Night (key **D**)
8. **Change orientation** — try North-Up, Head-Up, Course-Up, True Motion (key **O**)
9. **Change range** — use **+/−** or **Z/X** keys; display should rescale
10. **Toggle displays** — press **A** (AIS), **B** (ADS-B), **T** (tracks), **L** (trails)
11. **Test STBY/TX toggle** — click the button at the left of the control bar; should switch from amber STBY to green TX and log "RADAR TRANSMIT"
12. **Click targets** — selected target detail panel should populate with CPA, TCPA, BRG, RNG, risk
13. **Try EBL/VRM** — press **F1** for EBL1, drag to set bearing; **F3** for VRM1
14. **Right-click a target** — context menu with classify, intercept, CPA alert, and Slew Camera options
15. **Double-click system messages** — full-size popup should open
16. **Listen for alarms** — guard zone intrusions and CPA threats trigger audible tones; press **S** to ACK
17. **Press F12** — should silence / un-silence alarms
18. **Configure CPA thresholds** — Settings > CPA/TCPA Thresholds; adjust values and verify alarm behavior
19. **Open NMEA Monitor** — Tools > NMEA Monitor; select a source, confirm live sentences scroll; press Stop to freeze
20. **Hide stationary AIS** — View > Show Moored / Stationary AIS (uncheck); slow-moving triangles should disappear
21. **Check base stations** — if receiving real AIS data, teal hollow squares should appear at VTS/USCG positions
22. **Test Anchor Watch** — View > Anchor Watch...; click Refresh Targets, set swing radius to 0.05 NM, click Activate Watch; dashed gold circle should appear on PPI
23. **Open Help** — Help > PPI Symbols & Keyboard Shortcuts; symbol legend and shortcut table should appear

---

## Default UDP Port Reference

| Source | Port |
|--------|------|
| GPS | 10110 |
| Heading / Gyro | 10111 |
| Depth | 10112 |
| AIS | 10113 |
| ADS-B / FLARM | 10117 |
| Camera Command (send) | 10120 |
| Camera Response (listen) | 10121 |

---

## Troubleshooting

**Application won't start:**
```bash
python --version    # Must be 3.9+
pip install --force-reinstall -r requirements.txt
```

**No NMEA data / labels staying red:**
- Check firewall — UDP ports must be open
- Verify NMEA sender is running (`python test_nmea_sender.py`)
- Check Settings > NMEA Sources configuration

**ADS-B targets not appearing:**
- Confirm receiver is sending $PFLAA sentences to port 10117
- Own ship GPS must be active for position conversion
- Check Settings > NMEA Sources > ADS-B Sources tab

**No alarm sounds:**
- Ensure default audio output is configured in Windows Sound settings
- Check View > Silence Alarms is not checked

**Display issues:**
- Update graphics drivers
- Try a different display mode

---

## File Overview

```
main.py                          — Start the application
test_nmea_sender.py              — Simulated NMEA + AIS data generator

gui/main_window.py               — Main window, controls, panels, keyboard shortcuts
gui/ppi_display.py               — PPI radar display (ARPA, AIS, ADS-B, camera, EBL/VRM)
gui/color_themes.py              — Day / Dusk / Night / Red Night color themes
gui/target_panel.py              — Selected target detail panel
gui/alarm_widget.py              — Alarm history with per-alarm ACK buttons
gui/nmea_config_dialog.py        — NMEA source configuration (all types + camera)
gui/radar_config_dialog.py       — Radar unit configuration
gui/guard_zone_dialog.py         — Guard zone configuration
gui/ais_encrypt_dialog.py        — Encrypted AIS key management
gui/cpa_settings_dialog.py       — CPA/TCPA threshold configuration
gui/bit_window.py                — Built-In Test diagnostics
gui/nmea_monitor_dialog.py       — Live NMEA-0183 sentence monitor
gui/anchor_watch_dialog.py       — Anchor Watch popup

core/multi_source_nmea_parser.py — Multi-source NMEA-0183 parser + AIS decoder
core/adsb_receiver.py            — ADS-B / FLARM receiver ($PFLAA / $PFLAU)
core/camera_controller.py        — PTZ camera NMEA slew commands + azimuth parsing
core/radar_interface.py          — Abstract radar API + mock (SDK integration point)
core/ais_decrypt.py              — AES-CBC decryption for Secure AIS
core/alarm_manager.py            — Audible alarm controller (WAV synthesis)
core/track_manager.py            — Track correlation, CPA/TCPA, classification, trails
core/cpa_calculator.py           — CPA/TCPA calculations
core/track_filter.py             — Kalman and Alpha-Beta filters
core/guard_zone.py               — Guard zone definitions and intrusion detection
core/gps_spoofing_detector.py    — GPS spoofing detection
core/performance_monitor.py      — System performance metrics (FPS, CPU, memory)
core/radar_logger.py             — Radar/NMEA event logger for replay and diagnostics
core/radar_performance.py        — Radar RF performance analyser (SNR, interference)
core/system_watchdog.py          — System health monitor with alarm integration
core/logger.py                   — Centralized logging configuration
core/plugin_system.py            — Plugin architecture for extensibility
```

---

## Next Steps

Once the application works with simulated data:

1. **Connect real NMEA sources** — Settings > NMEA Sources
2. **Connect ADS-B receiver** — Settings > NMEA Sources > ADS-B Sources; point receiver output at port 10117
3. **Configure PTZ camera** — Settings > NMEA Sources > Camera Control; set host, ports, bearing mode, and message template
4. **Add SA-AIS encryption keys** — Settings > Encrypted AIS Keys (if using Secure AIS)
5. **Integrate Radar SDK** — See README.md; implement `RadarInterface` subclass and connect `set_transmit()` / `transmit_state_changed`
6. **Customize guard zones** — Settings > Guard Zones
7. **Adjust CPA/TCPA thresholds** — Settings > CPA/TCPA Thresholds
