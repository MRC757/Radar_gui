"""
Centralized logging configuration for the Radar GUI application.
Call setup_logging() once at startup before other imports.
"""

import logging
import sys


def setup_logging(level=logging.INFO):
    """Configure root logger with a consistent format."""
    fmt = "[%(asctime)s] %(name)s %(levelname)s: %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stdout)
