import os
import sys
import json
import shutil
from dotenv import load_dotenv

# ─── LOCATE project root ────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# When frozen (PyInstaller), use exe directory
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = os.path.dirname(sys.executable)

# ─── Auto-copy config/env on first run ──────────────────────
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.json")
_CONFIG_EXAMPLE = os.path.join(_PROJECT_ROOT, "config.json.example")
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
_ENV_EXAMPLE = os.path.join(_PROJECT_ROOT, ".env.example")

if not os.path.exists(_CONFIG_PATH):
    if os.path.exists(_CONFIG_EXAMPLE):
        shutil.copy2(_CONFIG_EXAMPLE, _CONFIG_PATH)
        print(f"First run: created config.json from example at {_CONFIG_PATH}")
    else:
        print("=" * 60)
        print("ERROR: config.json and config.json.example both missing!")
        print(f"  Expected at: {_CONFIG_PATH}")
        print("=" * 60)
        sys.exit(1)

if not os.path.exists(_ENV_PATH):
    if os.path.exists(_ENV_EXAMPLE):
        shutil.copy2(_ENV_EXAMPLE, _ENV_PATH)
        print(f"First run: created .env from example at {_ENV_PATH}")

load_dotenv(_ENV_PATH)

with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
    _CFG = json.load(f)


def _env_int(name, default):
    """Parse an integer env var with a safe fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_optional_int(name, default):
    """Parse an optional integer env var. Empty/none values map to None."""
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip().lower()
    if raw in ("", "none", "null", "infinite", "inf"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    """Parse a float env var with a safe fallback."""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

# ─── ENV VARS (.env) ─────────────────────────────────────────
AIRTABLE_API_TOKEN = os.getenv("AIRTABLE_API_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")
AIRTABLE_FIELD_NAME = os.getenv("AIRTABLE_FIELD_NAME", "Blended Image")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free")
LMSTUDIO_API_BASE_URL = os.getenv("LMSTUDIO_API_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "zai-org/glm-4.6v-flash")
LMSTUDIO_MAX_TOKENS = _env_int("LMSTUDIO_MAX_TOKENS", 128)
LMSTUDIO_CONNECT_TIMEOUT = _env_int("LMSTUDIO_CONNECT_TIMEOUT", 5)
LMSTUDIO_READ_TIMEOUT = _env_optional_int("LMSTUDIO_READ_TIMEOUT", None)
CAPTION_HISTORY_LIMIT = _env_int("CAPTION_HISTORY_LIMIT", 500)
CAPTION_HISTORY_PROMPT_LIMIT = _env_int("CAPTION_HISTORY_PROMPT_LIMIT", 40)
CAPTION_RETRY_ATTEMPTS = _env_int("CAPTION_RETRY_ATTEMPTS", 4)
KIE_API_KEY = os.getenv("KIE_API_KEY")
KIE_API_BASE_URL = os.getenv("KIE_API_BASE_URL", "https://api.kie.ai").rstrip("/")
KIE_CALLBACK_URL = os.getenv("KIE_CALLBACK_URL", "").strip()
KIE_VOICE_ID = os.getenv("KIE_VOICE_ID", "EkK5I93UQWFDigLMpZcX")
KIE_STABILITY = _env_float("KIE_STABILITY", 0.5)
KIE_POLL_TIMEOUT_SECONDS = _env_int("KIE_POLL_TIMEOUT_SECONDS", 180)
KIE_POLL_INTERVAL_SECONDS = _env_int("KIE_POLL_INTERVAL_SECONDS", 3)

BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

# ─── Data directory (browser profiles live here) ─────────────
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
os.makedirs(_DATA_DIR, exist_ok=True)
CAPTION_HISTORY_PATH = os.getenv(
    "CAPTION_HISTORY_PATH",
    os.path.join(_DATA_DIR, "caption_history.json"),
)

BRAVE_USER_DATA_AUTO = os.getenv("BRAVE_USER_DATA_AUTO",
    os.path.join(_DATA_DIR, "auto_profile"))

# ─── Chrome / Chromium path ─────────────────────────────────
from src.browser_utils import get_chromium_path
CHROME_PATH = os.getenv("CHROME_PATH", get_chromium_path())

CHROME_USER_DATA_STORY = os.path.join(_DATA_DIR, "chrome_profile_story")
CHROME_USER_DATA_POST = os.path.join(_DATA_DIR, "chrome_profile_post")

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

# ─── FROM config.json ─────────────────────────────────────────
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

ZOHO_FIELD_FOLDER_MAP = _CFG.get("zoho_field_folder_map", {})
ZOHO_STATUS_FOLDER_MAP = _CFG.get("zoho_status_folder_map", {})
APP_SOURCES = _CFG.get("app_sources", {})
APP_FIELD_OPTIONS = _CFG.get("app_field_options", {})
COLLECTION_CATEGORY_SEPARATOR = "── Collection Category ──"
COLLECTION_CATEGORY_FIELD = "Collection Categ System"
TIPS_EDU_SEPARATOR = "── Tips Edu ──"
TIPS_EDU_FIELD = "Tips Educational Photos"
QUOTES_PHOTOS_SEPARATOR = "── Quotes Photos ──"
QUOTES_PHOTOS_FIELD = "Quotes Photos"

for source_id, raw_options in list(APP_FIELD_OPTIONS.items()):
    options = list(raw_options)
    if COLLECTION_CATEGORY_FIELD not in options:
        options.extend([COLLECTION_CATEGORY_SEPARATOR, COLLECTION_CATEGORY_FIELD])
    if TIPS_EDU_FIELD not in options:
        options.extend([TIPS_EDU_SEPARATOR, TIPS_EDU_FIELD])
    if QUOTES_PHOTOS_FIELD not in options:
        options.extend([QUOTES_PHOTOS_SEPARATOR, QUOTES_PHOTOS_FIELD])
    APP_FIELD_OPTIONS[source_id] = options

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
