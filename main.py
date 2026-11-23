#!/usr/bin/env python3
"""
NextGen Radar GUI Application
Main application entry point
"""

import sys
import signal
import importlib


# ---------------------------------------------------------------------------
# Dependency check — report missing packages; never install automatically.
# (Installing packages at start-up on a bridge system is a supply-chain risk
# and changes the software without the operator's knowledge.)
# ---------------------------------------------------------------------------

REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),       # (import_name, pip_name)
    ("numpy", "numpy"),
]
OPTIONAL_PACKAGES = [
    ("cryptography", "cryptography", "encrypted AIS decryption"),
]


def check_dependencies():
    """Return True if all required packages are importable."""
    missing = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)

    for import_name, pip_name, feature in OPTIONAL_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            print(f"[startup] Optional package '{pip_name}' not installed — "
                  f"{feature} disabled.")

    if not missing:
        return True

    print(f"[startup] Missing required packages: {', '.join(missing)}")
    print("[startup] Install the tested versions with:")
    print(f"[startup]     {sys.executable} -m pip install -r requirements.txt")
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
