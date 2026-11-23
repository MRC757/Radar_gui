"""
Audible Alarm Manager for Marine Radar GUI.

Provides distinct alarm tones for different threat conditions:
  - CPA critical  : high-frequency rapid beep (collision imminent)
  - CPA warning   : medium-frequency beep (close approach)
  - Guard zone    : medium-frequency double beep (intrusion detected)
  - GPS spoofing  : alternating high/low warble
  - Sensor loss   : low-frequency slow beep (navigation sensor offline)

Each alarm type is tracked as an individual entry with:
  - Per-alarm silence (ACK) buttons
  - Flash animation until acknowledged
  - Automatic re-alarm if condition clears then re-occurs

Synthesises tones as in-memory WAV data and plays them via
winsound.PlaySound(SND_MEMORY) so audio comes through the default
sound-card output (speakers / headphones) rather than the legacy
PC-speaker driver that winsound.Beep() targets.
"""

import io
import logging
import math
import os
import struct
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False


# ------------------------------------------------------------------
# WAV tone synthesis (plays through speakers, not PC-speaker)
# ------------------------------------------------------------------

_SAMPLE_RATE = 22050   # 22 kHz is plenty for alarm beeps
_VOLUME = 0.7          # 0.0 – 1.0


def _make_tone(freq_hz: int, duration_ms: int) -> bytes:
    """Return a 16-bit mono WAV (in memory) for a pure sine tone."""
    n = int(_SAMPLE_RATE * duration_ms / 1000)
    data_size = n * 2
    buf = io.BytesIO()
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVEfmt ')
    buf.write(struct.pack('<IHHIIHH', 16, 1, 1,
                          _SAMPLE_RATE, _SAMPLE_RATE * 2, 2, 16))
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    two_pi_f = 2.0 * math.pi * freq_hz
    for i in range(n):
        sample = _VOLUME * math.sin(two_pi_f * i / _SAMPLE_RATE)
        buf.write(struct.pack('<h', int(sample * 32767)))
    return buf.getvalue()


def _make_warble(freq_hi: int, freq_lo: int, duration_ms: int) -> bytes:
    """Return a WAV that alternates between two frequencies (warble)."""
    n = int(_SAMPLE_RATE * duration_ms / 1000)
    data_size = n * 2
    buf = io.BytesIO()
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVEfmt ')
    buf.write(struct.pack('<IHHIIHH', 16, 1, 1,
                          _SAMPLE_RATE, _SAMPLE_RATE * 2, 2, 16))
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    half = n // 2
    two_pi_hi = 2.0 * math.pi * freq_hi
    two_pi_lo = 2.0 * math.pi * freq_lo
    for i in range(half):
        sample = _VOLUME * math.sin(two_pi_hi * i / _SAMPLE_RATE)
        buf.write(struct.pack('<h', int(sample * 32767)))
    for i in range(half, n):
        sample = _VOLUME * math.sin(two_pi_lo * i / _SAMPLE_RATE)
        buf.write(struct.pack('<h', int(sample * 32767)))
    return buf.getvalue()


def _make_double_beep(freq_hz: int, beep_ms: int, gap_ms: int = 80) -> bytes:
    """Return a WAV with two short beeps separated by silence."""
    n_beep = int(_SAMPLE_RATE * beep_ms / 1000)
    n_gap = int(_SAMPLE_RATE * gap_ms / 1000)
    n_total = n_beep * 2 + n_gap
    data_size = n_total * 2
    buf = io.BytesIO()
    buf.write(b'RIFF')
    buf.write(struct.pack('<I', 36 + data_size))
    buf.write(b'WAVEfmt ')
    buf.write(struct.pack('<IHHIIHH', 16, 1, 1,
                          _SAMPLE_RATE, _SAMPLE_RATE * 2, 2, 16))
    buf.write(b'data')
    buf.write(struct.pack('<I', data_size))
    two_pi_f = 2.0 * math.pi * freq_hz
    # First beep
    for i in range(n_beep):
        sample = _VOLUME * math.sin(two_pi_f * i / _SAMPLE_RATE)
        buf.write(struct.pack('<h', int(sample * 32767)))
    # Gap (silence)
    for _ in range(n_gap):
        buf.write(struct.pack('<h', 0))
    # Second beep
    for i in range(n_beep):
        sample = _VOLUME * math.sin(two_pi_f * i / _SAMPLE_RATE)
        buf.write(struct.pack('<h', int(sample * 32767)))
    return buf.getvalue()


# Pre-build WAV data at import time so playback has zero latency
_ALARM_WAVS: dict[str, bytes] = {}

def _build_alarm_wavs():
    """Pre-generate WAV bytes for every alarm type."""
    defs = {
        'cpa_critical': lambda d: _make_tone(d['freq'], d['dur']),
        'cpa_warning':  lambda d: _make_tone(d['freq'], d['dur']),
        'guard_zone':   lambda d: _make_double_beep(d['freq'], d['dur']),
        'gps_spoofing': lambda d: _make_warble(2200, 1400, d['dur']),
        'sensor_loss':  lambda d: _make_tone(d['freq'], d['dur']),
        'anchor_drag':  lambda d: _make_double_beep(d['freq'], d['dur']),
        'radar_link':   lambda d: _make_warble(1300, 900, d['dur']),
        'radar_video':  lambda d: _make_tone(d['freq'], d['dur']),
    }
    for atype, defn in ALARM_DEFS.items():
        builder = defs.get(atype)
        if builder:
            _ALARM_WAVS[atype] = builder(defn)


# Alarm definitions: frequency_hz, duration_ms, repeat_interval_s, display_label
ALARM_DEFS = {
    'cpa_critical': {'freq': 2400, 'dur': 200, 'interval': 0.6,
                     'label': 'CPA CRITICAL'},
    'cpa_warning':  {'freq': 1800, 'dur': 300, 'interval': 1.5,
                     'label': 'CPA WARNING'},
    'guard_zone':   {'freq': 1500, 'dur': 150, 'interval': 1.0,
                     'label': 'GUARD ZONE'},
    'gps_spoofing': {'freq': 2000, 'dur': 250, 'interval': 0.8,
                     'label': 'GPS SPOOFING'},
    'sensor_loss':  {'freq': 1200, 'dur': 400, 'interval': 2.0,
                     'label': 'SENSOR LOSS'},
    'anchor_drag':  {'freq': 1000, 'dur': 400, 'interval': 3.0,
                     'label': 'ANCHOR DRAG'},
    'radar_link':   {'freq': 1100, 'dur': 400, 'interval': 2.0,
                     'label': 'RADAR LINK'},
    'radar_video':  {'freq': 1100, 'dur': 300, 'interval': 2.0,
                     'label': 'NO RADAR VIDEO'},
}

# Default descriptions when none is provided
_DEFAULT_DESCRIPTIONS = {
    'cpa_critical': 'Collision risk detected',
    'cpa_warning':  'Close approach target',
    'guard_zone':   'Target intrusion detected',
    'gps_spoofing': 'Position anomaly detected',
    'sensor_loss':  'Navigation data offline',
    'anchor_drag':  'Ship dragging anchor — outside swing radius',
    'radar_link':   'Radar connection lost',
    'radar_video':  'Transmitting but no radar video received',
}

# Pre-build WAV audio at module load
_build_alarm_wavs()


class AlarmEntry:
    """Represents one alarm instance in the alarm list."""
    __slots__ = ('alarm_type', 'description', 'timestamp', 'time_str',
                 'silenced', 'active')

    def __init__(self, alarm_type: str, description: str):
        self.alarm_type = alarm_type
        self.description = description
        self.timestamp = time.monotonic()
        self.time_str = datetime.now().strftime("%H:%M:%S")
        self.silenced = False
        self.active = True   # True while the condition persists


_LOG_DIR = Path("logs")


class AlarmManager:
    """Manages audible alarms with per-alarm silence and history.

    Each alarm *type* has at most one active entry at a time.  When the
    condition clears (``clear()``) the entry becomes inactive.  If the
    condition re-occurs a **new** entry is created so it sounds and
    flashes again until the user acknowledges it.

    All alarm events are appended to ``logs/alarm_log.txt`` for post-incident
    review and IMO compliance.
    """

    MAX_ENTRIES = 20   # keep recent history

    def __init__(self):
        self._entries: list[AlarmEntry] = []
        self._silenced_global = False
        self._enabled = True
        self._lock = threading.Lock()
        self._cooldowns: dict[str, float] = {}   # alarm_type -> cooldown_end

        # Persistent alarm log
        try:
            _LOG_DIR.mkdir(exist_ok=True)
            self._log_path = _LOG_DIR / "alarm_log.txt"
        except Exception:
            self._log_path = None
        self._write_log("STARTUP", "---", "Alarm manager initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trigger(self, alarm_type: str, description: str = ""):
        """Trigger an alarm.

        If an active entry already exists for *alarm_type* its
        description is updated but no new entry is created (so a
        silenced alarm stays silenced until the condition clears and
        returns).  If no active entry exists a new one is created and
        sound + flash begin.
        """
        if not self._enabled:
            return
        if alarm_type not in ALARM_DEFS:
            logger.warning("Unknown alarm type: %s", alarm_type)
            return

        if not description:
            description = _DEFAULT_DESCRIPTIONS.get(alarm_type, alarm_type)

        now = time.monotonic()
        with self._lock:
            existing = self._find_active_entry(alarm_type)
            if existing is None:
                # --- New alarm condition ---
                entry = AlarmEntry(alarm_type, description)
                self._entries.insert(0, entry)
                self._trim_entries()
                logger.info("Alarm raised: %s — %s", alarm_type, description)
                self._write_log("TRIGGERED", alarm_type, description)
            else:
                existing.description = description
                entry = existing

            # Cooldown — prevents rapid beeping
            cooldown_end = self._cooldowns.get(alarm_type, 0)
            if now < cooldown_end:
                return
            defn = ALARM_DEFS[alarm_type]
            self._cooldowns[alarm_type] = now + defn['interval']

        # Play sound only if this entry is not silenced (individually or globally)
        if not entry.silenced and not self._silenced_global:
            threading.Thread(
                target=self._play, args=(alarm_type,), daemon=True
            ).start()

    def silence_type(self, alarm_type: str):
        """Silence the active entry for a specific alarm type."""
        with self._lock:
            entry = self._find_active_entry(alarm_type)
            if entry:
                entry.silenced = True
                logger.info("Alarm acknowledged: %s", alarm_type)
                self._write_log("ACKNOWLEDGED", alarm_type, entry.description)

    def unsilence_type(self, alarm_type: str):
        """Un-silence the active entry for a specific alarm type."""
        with self._lock:
            entry = self._find_active_entry(alarm_type)
            if entry:
                entry.silenced = False

    def silence(self):
        """Silence all alarms globally."""
        self._silenced_global = True
        logger.info("All alarms silenced")
        self._write_log("SILENCED_ALL", "---", "Operator globally silenced all alarms")

    def unsilence(self):
        """Un-silence all alarms globally."""
        self._silenced_global = False
        logger.info("All alarms un-silenced")
        self._write_log("UNSILENCED", "---", "Alarms globally un-silenced")

    @property
    def is_silenced(self):
        return self._silenced_global

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    @property
    def active_alarms(self):
        """Return set of currently active alarm types."""
        with self._lock:
            return {e.alarm_type for e in self._entries if e.active}

    def get_recent_entries(self, count: int = 5) -> list:
        """Return the *count* most recent alarm entries for the widget."""
        with self._lock:
            return list(self._entries[:count])

    def clear(self, alarm_type: str):
        """Clear an alarm (condition resolved)."""
        with self._lock:
            entry = self._find_active_entry(alarm_type)
            if entry:
                entry.active = False
                self._write_log("CLEARED", alarm_type, entry.description)

    def clear_all(self):
        """Clear all active alarms."""
        with self._lock:
            for entry in self._entries:
                entry.active = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_log(self, event: str, alarm_type: str, description: str):
        """Append a single alarm event line to the persistent log file."""
        if self._log_path is None:
            return
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{ts}  {event:<14}  {alarm_type:<16}  {description}\n"
            with open(self._log_path, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as exc:
            logger.debug("Alarm log write failed: %s", exc)

    def _trim_entries(self):
        """Keep at most MAX_ENTRIES, dropping the oldest INACTIVE entries
        first.  Active entries are never dropped — losing one would make the
        next trigger() create a fresh, un-silenced duplicate."""
        excess = len(self._entries) - self.MAX_ENTRIES
        if excess <= 0:
            return
        for i in range(len(self._entries) - 1, -1, -1):
            if excess == 0:
                break
            if not self._entries[i].active:
                del self._entries[i]
                excess -= 1

    def _find_active_entry(self, alarm_type: str):
        """Find the currently active entry for *alarm_type*, if any."""
        for entry in self._entries:
            if entry.alarm_type == alarm_type and entry.active:
                return entry
        return None

    def play_test_tone(self, alarm_type: str = 'sensor_loss'):
        """Play an alarm tone directly for BIT audio testing.

        Bypasses all silence, cooldown, and entry state — always plays
        immediately so the operator can confirm audio output.
        """
        threading.Thread(
            target=self._play, args=(alarm_type,), daemon=True
        ).start()

    def _play(self, alarm_type: str):
        """Play the alarm tone through the default audio device."""
        wav = _ALARM_WAVS.get(alarm_type)
        if wav and _HAS_WINSOUND:
            try:
                winsound.PlaySound(wav, winsound.SND_MEMORY)
            except Exception as exc:
                logger.debug("PlaySound failed: %s", exc)
        else:
            logger.debug("No winsound; alarm %s would play", alarm_type)
