"""Resolve path to Chromium executable — bundled (frozen) or system."""
import os
import sys


def get_chromium_path():
    """Return path to Chromium executable.

    Frozen (PyInstaller): looks for chromium/chrome.exe next to the exe.
    Dev mode: falls back to system Chrome path.
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        bundled = os.path.join(base, "chromium", "chrome.exe")
        if os.path.exists(bundled):
            return bundled

    # Dev fallback: system Chrome
    return os.getenv(
        "CHROME_PATH",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
