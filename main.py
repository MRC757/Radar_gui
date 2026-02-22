#!/usr/bin/env python3
"""
NextGen Radar GUI Application
Main application entry point
"""

import sys
import signal
import subprocess
import importlib


# ---------------------------------------------------------------------------
# Dependency check — install missing packages from requirements.txt
# ---------------------------------------------------------------------------

REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),       # (import_name, pip_name)
    ("numpy", "numpy"),
]


def check_dependencies():
    """Check for required packages and install any that are missing."""
    missing = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append((import_name, pip_name))

    if not missing:
        return True

    names = ", ".join(pip for _, pip in missing)
    print(f"[startup] Missing dependencies: {names}")
    print("[startup] Installing missing packages...")

    pip_args = [sys.executable, "-m", "pip", "install"]
    for _, pip_name in missing:
        pip_args.append(pip_name)

    try:
        subprocess.check_call(pip_args)
        print("[startup] Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[startup] Failed to install dependencies: {exc}")
        print("[startup] Please install manually:  pip install " + " ".join(
            pip for _, pip in missing
        ))
        return False


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def main():
    """Main application entry point"""
    from core.logger import setup_logging
    setup_logging()

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from gui.main_window import RadarMainWindow

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("NextGen Radar GUI")
    app.setOrganizationName("RadarSystems")

    # Allow Ctrl+C in the terminal to close the application gracefully
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # Create and show main window
    window = RadarMainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    if check_dependencies():
        main()
    else:
        sys.exit(1)
