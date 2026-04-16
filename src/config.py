import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

# ─── LOCATE config.json ──────────────────────────────────────
# Look next to this file first, then project root
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# When frozen (PyInstaller), use exe directory
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = os.path.dirname(sys.executable)

_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.json")

if not os.path.exists(_CONFIG_PATH):
    print("=" * 60)
    print("ERROR: config.json not found!")
    print(f"  Expected at: {_CONFIG_PATH}")
    print()
    print("  Copy config.json.example to config.json and edit it")
    print("  with your own Airtable, Zoho, and branding settings.")
    print("=" * 60)
    sys.exit(1)

with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
    _CFG = json.load(f)

# ─── ENV VARS (.env) ─────────────────────────────────────────
AIRTABLE_API_TOKEN = os.getenv("AIRTABLE_API_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")
AIRTABLE_FIELD_NAME = os.getenv("AIRTABLE_FIELD_NAME", "Blended Image")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free")

BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")
BRAVE_USER_DATA_AUTO = os.getenv("BRAVE_USER_DATA_AUTO",
    os.path.join(os.path.expanduser("~"), ".socialbee_auto_profile"))

CHROME_PATH = os.getenv("CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe")
CHROME_USER_DATA_STORY = os.path.join(os.path.expanduser("~"), ".socialbee_chrome_story")
CHROME_USER_DATA_POST = os.path.join(os.path.expanduser("~"), ".socialbee_chrome_post")

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

# ─── FROM config.json ─────────────────────────────────────────
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

ZOHO_FIELD_FOLDER_MAP = _CFG.get("zoho_field_folder_map", {})
APP_SOURCES = _CFG.get("app_sources", {})
APP_FIELD_OPTIONS = _CFG.get("app_field_options", {})

# Convert paired/triple lists back to tuples (JSON stores as arrays)
PAIRED_FIELD_OPTIONS = {
    k: tuple(v) for k, v in _CFG.get("paired_field_options", {}).items()
}
TRIPLE_FIELD_OPTIONS = {
    k: tuple(v) for k, v in _CFG.get("triple_field_options", {}).items()
}

ZOHO_FETCH_OPTIONS = _CFG.get("zoho_fetch_options", {})
APP_TABLE_IDS = _CFG.get("app_table_ids", {})

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
}

# ─── FOOTER & MODELS ─────────────────────────────────────────
HOMECARTEL_FOOTER = _CFG.get("footer", "")

FALLBACK_MODELS = _CFG.get("fallback_models", [OPENROUTER_MODEL])
