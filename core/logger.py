"""
Centralized logging configuration for the Radar GUI application.
Call setup_logging() once at startup before other imports.

Logs go to the console and to a rotating file (logs/radar_gui.log, 5 MB x 5)
so events can be reviewed after an incident.  Alarm events are additionally
written to logs/alarm_log.txt by the alarm manager.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "radar_gui.log"


def setup_logging(level=logging.INFO, log_file=LOG_FILE):
    """Configure root logger with a consistent format."""
    fmt = "[%(asctime)s] %(name)s %(levelname)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024,
                                           backupCount=5, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S"))
        handlers.append(file_handler)
    except OSError as exc:   # read-only install dir etc. — keep console logging
        print(f"[logging] File logging disabled: {exc}", file=sys.stderr)
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S", handlers=handlers)
