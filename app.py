"""SocialBee AutoPoster — Eel Web UI backend."""
import eel
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import queue
import threading
import tempfile
import traceback
import time
import uuid
import requests

from src.config import (
    APP_SOURCES, APP_FIELD_OPTIONS, PAIRED_FIELD_OPTIONS, TRIPLE_FIELD_OPTIONS,
    ZOHO_FETCH_OPTIONS, VIDEO_EXTENSIONS, ZOHO_FIELD_FOLDER_MAP, ZOHO_STATUS_FOLDER_MAP,
    COLLECTION_CATEGORY_FIELD, TIPS_EDU_FIELD, QUOTES_PHOTOS_FIELD,
    BLENDED_IMAGE_LOCAL_FIELD,
    KIE_API_KEY, KIE_API_BASE_URL, KIE_CALLBACK_URL, KIE_VOICE_ID, KIE_STABILITY,
    KIE_POLL_TIMEOUT_SECONDS, KIE_POLL_INTERVAL_SECONDS,
)
import bottle
from src.zoho_client import upload_file_to_workdrive, get_valid_token
from src.airtable_client import (
    fetch_raw_records_for_base,
    fetch_all_records_for_base, fetch_paired_records_for_base,
    fetch_triple_records_for_base,
    clear_cache, mark_record_posted, mark_record_disregarded, update_cache,
    propagate_disregard, remove_specific_attachment
)
from src.caption import (
    generate_short_caption,
    generate_local_image_caption,
    generate_lmstudio_visual_caption,
    generate_video_tip_from_frames,
    get_item_names,
    compose_caption,
)
from src.socialbee_poster import (
    post_to_socialbee, post_to_socialbee_multiple,
    post_to_socialbee_story, setup_chrome_post_profile, setup_chrome_story_profile,
)

# ── State ──
APP_BUILD = "2026-04-29-tips-reels-04"
_images = []
_images_lock = threading.Lock()
_current_index = 0
_paired_mode = False
_paired_field_name = None
_fetch_base_id = None
_fetch_cache_key = None
_fetch_id = 0
_fetch_sessions = {}
_fetch_sessions_lock = threading.Lock()
_result_queue = queue.Queue()
_app_root = os.path.dirname(os.path.abspath(__file__))
_local_upload_root = os.path.join(_app_root, "data", "local_uploads")
_local_upload_manifest_path = os.path.join(_app_root, "data", "local_upload_manifest.json")
_disregard_manifest_path = os.path.join(_app_root, "data", "disregard_manifest.json")
_tips_reel_root = os.path.join(_app_root, "data", "tips_reels")
_tips_reel_manifest_path = os.path.join(_app_root, "data", "tips_reel_manifest.json")
_tips_reel_upload_root = os.path.join(_app_root, "data", "tips_reel_uploads")
_tips_reel_upload_manifest_path = os.path.join(_app_root, "data", "tips_reel_upload_manifest.json")
_local_uploads = {}
_local_upload_lists = {}
_local_uploads_lock = threading.Lock()
_disregard_state = {}
_disregard_lock = threading.Lock()
_tips_reel_state = {}
_tips_reel_lock = threading.Lock()
_tips_reel_uploads = {}
_tips_reel_upload_list = []
_tips_reel_uploads_lock = threading.Lock()
_eel_lock = threading.Lock()


_LOCAL_UPLOAD_FIELDS = (
    COLLECTION_CATEGORY_FIELD,
    TIPS_EDU_FIELD,
    QUOTES_PHOTOS_FIELD,
    BLENDED_IMAGE_LOCAL_FIELD,
)
_LOCAL_UPLOAD_FIELD_DIRS = {
    COLLECTION_CATEGORY_FIELD: "collection-category",
    TIPS_EDU_FIELD: "tips-and-education",
    QUOTES_PHOTOS_FIELD: "quotes-photos",
    BLENDED_IMAGE_LOCAL_FIELD: "blended-image-local",
}
_TIPS_REEL_VISUAL_FIELDS = ("Blended Image", "Styled Photo", "Moodboard Image")
_TIPS_REEL_COMBO_TYPE = "tips_combo"

# Categories that show BOTH Airtable-fetched media AND user-uploaded local items
# in the same lane. Local uploads here must be appended to the fetched session
# rather than replacing it.
_COMBINED_LOCAL_UPLOAD_CATEGORIES = frozenset({"blended-image"})


def _is_combined_local_upload_session(session_id):
    """Return True when the session is for a category that mixes fetch + local uploads."""
    category_id = _category_id_from_session_id(session_id)
    return category_id in _COMBINED_LOCAL_UPLOAD_CATEGORIES

os.makedirs(_local_upload_root, exist_ok=True)
os.makedirs(_tips_reel_root, exist_ok=True)
os.makedirs(_tips_reel_upload_root, exist_ok=True)
for _field_dir in _LOCAL_UPLOAD_FIELD_DIRS.values():
    os.makedirs(os.path.join(_local_upload_root, _field_dir), exist_ok=True)


# ── Exposed Functions ──

@eel.expose
def get_sources():
    """Return {base_id: display_name} for all sources."""
    return APP_SOURCES


@eel.expose
def get_field_options(base_id):
    """Return field dropdown options for a source, or None."""
    return APP_FIELD_OPTIONS.get(base_id)


@eel.expose
def get_paired_field_info(field_name):
    """If field_name is a paired option, return [field1, field2]. Else None."""
    pair = PAIRED_FIELD_OPTIONS.get(field_name)
    if pair:
        return list(pair)
    return None


@eel.expose
def get_triple_field_info(field_name):
    """If field_name is a triple option, return [field1, field2, field3]. Else None."""
    triple = TRIPLE_FIELD_OPTIONS.get(field_name)
    if triple:
        return list(triple)
    return None

@eel.expose
def get_zoho_folder_info(field_name):
    """If field_name is a zoho fetch option, return the folder ID. Else None."""
    return ZOHO_FETCH_OPTIONS.get(field_name)


@eel.expose
def get_app_build_info():
    """Return backend runtime/build metadata for UI diagnostics."""
    frozen = bool(getattr(sys, "frozen", False))
    return {
        "build": APP_BUILD,
        "frozen": frozen,
        "runtime": "exe" if frozen else "source",
        "entry": os.path.basename(sys.executable if frozen else __file__),
    }

@bottle.route('/zoho_video/<file_id>')
def serve_zoho_video(file_id):
    """Proxy route to stream video from Zoho Workdrive without exposing tokens."""
    token = get_valid_token()
    url = f"https://workdrive.zoho.com/api/v1/download/{file_id}"
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    req = requests.get(url, headers=headers, stream=True)
    
    content_type = req.headers.get('Content-Type', 'video/mp4')
    bottle.response.set_header('Content-Type', content_type)
    if 'Content-Length' in req.headers:
        bottle.response.set_header('Content-Length', req.headers['Content-Length'])
        
    return req.iter_content(chunk_size=1024*1024)


@bottle.get('/tips_reel_video/<media_key>')
def serve_tips_reel_video(media_key):
    """Serve a rendered Tips Reel video from the local conversion cache."""
    safe_key = re.sub(r"[^a-f0-9]", "", str(media_key or "").lower())[:64]
    if not safe_key:
        return bottle.HTTPError(404, "Tips Reel not found.")
    with _tips_reel_lock:
        entry = dict(_tips_reel_state.get(safe_key) or {})
    if entry.get("status") != "ready":
        return bottle.HTTPError(404, "Tips Reel not ready.")
    output_path = _tips_reel_output_path(safe_key, entry)
    if not os.path.exists(output_path):
        return bottle.HTTPError(404, "Tips Reel not found.")
    bottle.response.set_header("Cache-Control", "no-store, max-age=0")
    return bottle.static_file(os.path.basename(output_path), root=os.path.dirname(output_path), mimetype="video/mp4")


def _normalize_local_source_field(source_field=None):
    """Return the supported local-upload source field for a request."""
    if source_field in _LOCAL_UPLOAD_FIELDS:
        return source_field
    return COLLECTION_CATEGORY_FIELD


def _local_upload_dir_for_field(source_field):
    """Return the persistent storage directory for a local-upload category."""
    source_field = _normalize_local_source_field(source_field)
    return os.path.join(_local_upload_root, _LOCAL_UPLOAD_FIELD_DIRS[source_field])


def _manifest_payload_unlocked():
    """Return a JSON-serializable snapshot of the local-upload library."""
    categories = {}
    for source_field in _LOCAL_UPLOAD_FIELDS:
        categories[source_field] = []
        for entry in _local_upload_lists.get(source_field, []):
            categories[source_field].append({
                "upload_id": entry["upload_id"],
                "filename": entry["filename"],
                "stored_name": entry["stored_name"],
                "source_field": entry["source_field"],
                "fields": dict(entry.get("fields", {})),
            })
    return {"version": 1, "categories": categories}


def _save_local_upload_manifest_unlocked():
    """Persist the local-upload manifest. Caller must hold _local_uploads_lock."""
    os.makedirs(os.path.dirname(_local_upload_manifest_path), exist_ok=True)
    with open(_local_upload_manifest_path, "w", encoding="utf-8") as fh:
        json.dump(_manifest_payload_unlocked(), fh, ensure_ascii=True, indent=2)


def _build_local_upload_index_unlocked():
    """Rebuild the upload-id lookup table. Caller must hold _local_uploads_lock."""
    _local_uploads.clear()
    for entries in _local_upload_lists.values():
        for entry in entries:
            _local_uploads[entry["upload_id"]] = entry


def _load_local_upload_manifest():
    """Restore persisted local uploads on startup."""
    data = {}
    try:
        if os.path.exists(_local_upload_manifest_path):
            with open(_local_upload_manifest_path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh) or {}
    except Exception as exc:
        print(f"Local upload manifest load warning: {exc}")
        data = {}

    categories = data.get("categories", {}) if isinstance(data, dict) else {}
    changed = False

    with _local_uploads_lock:
        _local_upload_lists.clear()
        for source_field in _LOCAL_UPLOAD_FIELDS:
            _local_upload_lists[source_field] = []
            if source_field not in categories:
                changed = True
            raw_entries = categories.get(source_field, [])
            if not isinstance(raw_entries, list):
                changed = True
                continue
            for raw in raw_entries:
                if not isinstance(raw, dict):
                    changed = True
                    continue
                upload_id = str(raw.get("upload_id") or "").strip()
                filename = os.path.basename(str(raw.get("filename") or "").strip())
                stored_name = os.path.basename(str(raw.get("stored_name") or "").strip())
                if not upload_id or not filename or not stored_name:
                    changed = True
                    continue
                file_path = os.path.join(_local_upload_dir_for_field(source_field), stored_name)
                if not os.path.exists(file_path):
                    changed = True
                    continue
                entry = {
                    "upload_id": upload_id,
                    "filename": filename,
                    "stored_name": stored_name,
                    "source_field": source_field,
                    "fields": dict(raw.get("fields") or {}),
                    "path": file_path,
                }
                _local_upload_lists[source_field].append(entry)
        _build_local_upload_index_unlocked()
        if changed:
            _save_local_upload_manifest_unlocked()


def _category_id_from_session_id(session_id=None):
    """Return the category id encoded by the frontend session id, if any."""
    if not session_id or "::" not in str(session_id):
        return None
    return str(session_id).split("::", 1)[0] or None


def _save_disregard_manifest_unlocked():
    """Persist the local disregard manifest. Caller must hold _disregard_lock."""
    os.makedirs(os.path.dirname(_disregard_manifest_path), exist_ok=True)
    payload = {
        "version": 1,
        "items": dict(sorted(_disregard_state.items())),
    }
    with open(_disregard_manifest_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=2)


def _load_disregard_manifest():
    """Restore persisted disregard flags on startup."""
    data = {}
    try:
        if os.path.exists(_disregard_manifest_path):
            with open(_disregard_manifest_path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh) or {}
    except Exception as exc:
        print(f"Disregard manifest load warning: {exc}")
        data = {}

    raw_items = data.get("items", {}) if isinstance(data, dict) else {}
    with _disregard_lock:
        _disregard_state.clear()
        if isinstance(raw_items, dict):
            for raw_key, raw_value in raw_items.items():
                key = str(raw_key or "").strip()
                if key and bool(raw_value):
                    _disregard_state[key] = True


def _save_tips_reel_manifest_unlocked():
    """Persist Tips Reel conversion state. Caller must hold _tips_reel_lock."""
    os.makedirs(os.path.dirname(_tips_reel_manifest_path), exist_ok=True)
    payload = {
        "version": 1,
        "items": dict(sorted(_tips_reel_state.items())),
    }
    with open(_tips_reel_manifest_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=2)


def _load_tips_reel_manifest():
    """Restore persisted Tips Reel conversion state on startup."""
    data = {}
    try:
        if os.path.exists(_tips_reel_manifest_path):
            with open(_tips_reel_manifest_path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh) or {}
    except Exception as exc:
        print(f"Tips Reel manifest load warning: {exc}")
        data = {}

    raw_items = data.get("items", {}) if isinstance(data, dict) else {}
    changed = False
    with _tips_reel_lock:
        _tips_reel_state.clear()
        if isinstance(raw_items, dict):
            for raw_key, raw_value in raw_items.items():
                key = str(raw_key or "").strip()
                if not key or not isinstance(raw_value, dict):
                    changed = True
                    continue
                entry = dict(raw_value)
                if entry.get("status") == "ready":
                    output_path = _tips_reel_output_path(key, entry)
                    if not os.path.exists(output_path):
                        entry["status"] = "error"
                        entry["error"] = "Rendered Tips Reel file is missing."
                        changed = True
                elif entry.get("status") in ("queued", "downloading_source", "analyzing_frames", "writing_tip", "generating_voiceover", "rendering"):
                    entry["status"] = "error"
                    entry["error"] = "Previous conversion did not finish."
                    changed = True
                _tips_reel_state[key] = entry
        if changed:
            _save_tips_reel_manifest_unlocked()


def _safe_tips_reel_filename(media_key, filename=None):
    """Return a safe rendered Tips Reel filename for a manifest entry."""
    raw = os.path.basename(str(filename or "").strip())
    if raw and raw.startswith(f"tips_reel_{media_key}") and raw.lower().endswith(".mp4"):
        return raw
    return f"tips_reel_{media_key}.mp4"


def _tips_reel_output_path(media_key, entry=None):
    """Return the active rendered MP4 path for one Tips Reel media key."""
    filename = _safe_tips_reel_filename(media_key, (entry or {}).get("filename"))
    return os.path.join(_tips_reel_root, filename)


def _new_tips_reel_filename(media_key):
    """Return a fresh rendered filename for one Tips Reel attempt."""
    render_id = uuid.uuid4().hex[:10]
    return f"tips_reel_{media_key}_{render_id}.mp4"


def _cleanup_old_tips_reel_files(media_key, keep_filename):
    """Best-effort cleanup for older rendered versions after a successful render."""
    keep_filename = os.path.basename(str(keep_filename or ""))
    for name in os.listdir(_tips_reel_root):
        if not name.startswith(f"tips_reel_{media_key}") or not name.lower().endswith(".mp4"):
            continue
        if name == keep_filename:
            continue
        path = os.path.join(_tips_reel_root, name)
        try:
            os.unlink(path)
        except Exception as exc:
            print(f"Tips Reel cleanup warning ({name}): {exc}")


def _tips_reel_source_payload(img_data):
    """Return a stable source identity for a reel-like media item."""
    if not isinstance(img_data, dict):
        return {}
    return {
        "record_id": str(img_data.get("record_id") or ""),
        "file_id": str(img_data.get("file_id") or ""),
        "filename": os.path.basename(str(img_data.get("filename") or "")),
        "source_field": str(img_data.get("source_field") or ""),
        "type": str(img_data.get("type") or "single"),
        "url": str(img_data.get("url") or "") if not (img_data.get("record_id") or img_data.get("file_id")) else "",
    }


def _build_tips_reel_key(img_data):
    """Return a stable cache key for one source reel."""
    payload = _tips_reel_source_payload(img_data)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _build_combined_tips_reel_key(items):
    """Return a stable cache key for a three-source combined Tips Reel."""
    payload = [_tips_reel_source_payload(item) for item in items]
    raw = json.dumps({"type": _TIPS_REEL_COMBO_TYPE, "items": payload}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _tips_reel_status_label(status):
    labels = {
        "not_converted": "Not Converted",
        "queued": "Queued",
        "downloading_source": "Downloading source video",
        "analyzing_frames": "Analyzing Row Image",
        "writing_tip": "Writing AI tip",
        "generating_voiceover": "Generating voiceover",
        "rendering": "Rendering 9:16 video",
        "ready": "Ready",
        "error": "Error",
    }
    return labels.get(status, "Not Converted")


def _normalize_tips_reel_entry(media_key, entry=None):
    """Return a JSON-safe Tips Reel status object."""
    entry = dict(entry or {})
    status = str(entry.get("status") or "not_converted")
    filename = _safe_tips_reel_filename(media_key, entry.get("filename"))
    if status == "ready" and not os.path.exists(_tips_reel_output_path(media_key, entry)):
        status = "error"
        entry["error"] = "Rendered Tips Reel file is missing."
    payload = {
        "key": media_key,
        "status": status,
        "label": str(entry.get("label") or _tips_reel_status_label(status)),
        "tip": str(entry.get("tip") or ""),
        "tips": list(entry.get("tips") or []),
        "visual_source": str(entry.get("visual_source") or ""),
        "visual_sources": list(entry.get("visual_sources") or []),
        "voiceover": bool(entry.get("voiceover")),
        "voiceover_error": str(entry.get("voiceover_error") or ""),
        "source_count": int(entry.get("source_count") or 1),
        "error": str(entry.get("error") or ""),
        "updated_at": float(entry.get("updated_at") or 0),
        "render_version": str(entry.get("render_version") or ""),
    }
    if status == "ready":
        version = payload["render_version"] or str(int(payload["updated_at"] or 0))
        payload["url"] = f"/tips_reel_video/{media_key}?v={version}"
        payload["filename"] = filename
    return payload


def _get_tips_reel_status(media_key):
    """Return current Tips Reel status for one media key."""
    with _tips_reel_lock:
        return _normalize_tips_reel_entry(media_key, _tips_reel_state.get(media_key))


def _set_tips_reel_status(media_key, status, **updates):
    """Update and persist Tips Reel conversion status."""
    with _tips_reel_lock:
        entry = dict(_tips_reel_state.get(media_key) or {})
        entry.update(updates)
        entry["status"] = status
        entry["updated_at"] = time.time()
        if "label" not in updates:
            entry.pop("label", None)
        if status != "error":
            entry["error"] = str(updates.get("error") or "")
        _tips_reel_state[media_key] = entry
        _save_tips_reel_manifest_unlocked()
        return _normalize_tips_reel_entry(media_key, entry)


def _serialize_tips_reel_status_for_item(img_data):
    """Return current Tips Reel status for one media item."""
    if not isinstance(img_data, dict) or img_data.get("type") in ("pair", "triple"):
        return None
    if img_data.get("type") == _TIPS_REEL_COMBO_TYPE:
        media_key = str(img_data.get("combo_key") or "").strip()
        return _get_tips_reel_status(media_key) if media_key else None
    filename = str(img_data.get("filename") or "")
    if os.path.splitext(filename)[1].lower() not in VIDEO_EXTENSIONS and img_data.get("type") != "zoho":
        return None
    return _get_tips_reel_status(_build_tips_reel_key(img_data))


def _emit_tips_reel_status(index, session_id, img_data, status_payload):
    """Notify the frontend about one Tips Reel status update."""
    try:
        with _eel_lock:
            eel.on_tips_reel_status(index, session_id, status_payload)
    except Exception as exc:
        print(f"Tips Reel status emit warning: {exc}")


def _emit_combined_tips_reel_status(session_id, combo_item):
    """Notify the frontend about a combined Tips Reel item update."""
    try:
        with _eel_lock:
            eel.on_combined_tips_reel_status(session_id, _serialize_one(combo_item))
    except Exception as exc:
        print(f"Combined Tips Reel status emit warning: {exc}")


def _build_disregard_key(img_data, category_id):
    """Return a stable category-scoped key for one media card."""
    if not isinstance(img_data, dict) or not category_id or img_data.get("local_upload"):
        return None

    record_id = str(img_data.get("record_id") or "").strip() or "-"
    img_type = str(img_data.get("type") or "single").strip() or "single"
    filename = lambda value: os.path.basename(str(value or "").strip())

    if img_type == "pair":
        left_data = img_data.get("left") or {}
        right_data = img_data.get("right") or {}
        left_name = filename(left_data.get("filename")) or "-"
        right_name = filename(right_data.get("filename")) or "-"
        return f"{category_id}|{record_id}|pair|{left_name}|{right_name}"

    if img_type == "triple":
        left_data = img_data.get("left") or {}
        center_data = img_data.get("center") or {}
        right_data = img_data.get("right") or {}
        left_name = filename(left_data.get("filename")) or "-"
        center_name = filename(center_data.get("filename")) or "-"
        right_name = filename(right_data.get("filename")) or "-"
        return f"{category_id}|{record_id}|triple|{left_name}|{center_name}|{right_name}"

    if img_type == "zoho":
        file_id = str(img_data.get("file_id") or "").strip()
        if file_id:
            return f"{category_id}|zoho|{file_id}"
        unique_name = filename(img_data.get("filename")) or "-"
        return f"{category_id}|zoho|{unique_name}"

    unique_name = filename(img_data.get("filename")) or "-"
    return f"{category_id}|{record_id}|single|{unique_name}"


def _is_disregarded(img_data, category_id):
    """Return True when a media card is marked disregarded for a category."""
    key = _build_disregard_key(img_data, category_id)
    if not key:
        return False
    with _disregard_lock:
        return bool(_disregard_state.get(key))


def _apply_disregard_flag(img_data, category_id):
    """Merge local disregard state into one media item."""
    if not isinstance(img_data, dict):
        return
    fields = img_data.setdefault("fields", {})
    if img_data.get("local_upload"):
        fields["Disregard"] = bool(fields.get("Disregard"))
        return
    fields["Disregard"] = _is_disregarded(img_data, category_id)


def _apply_disregard_flags(images, category_id):
    """Merge local disregard state into a list of media items."""
    if not isinstance(images, list):
        return images
    for img_data in images:
        _apply_disregard_flag(img_data, category_id)
    return images


def _download_zoho_file(file_id, filename):
    """Download a Zoho WorkDrive file to a temp path for upload/posting."""
    ext = os.path.splitext(filename)[1] or ".mp4"
    token = get_valid_token()
    url = f"https://workdrive.zoho.com/api/v1/download/{file_id}"
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    resp = requests.get(url, headers=headers, timeout=300, stream=True)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="sb_zoho_")
    try:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name


def _ffmpeg_exe():
    """Return the bundled imageio ffmpeg executable."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(f"FFmpeg is not available: {exc}") from exc


def _download_tips_reel_source(img_data):
    """Return (local_path, should_delete) for a source reel."""
    if img_data.get("local_path") and os.path.exists(img_data["local_path"]):
        return img_data["local_path"], False
    if img_data.get("type") == "zoho" and img_data.get("file_id"):
        return _download_zoho_file(img_data["file_id"], img_data.get("filename") or "reel.mp4"), True

    url = str(img_data.get("url") or "").strip()
    filename = os.path.basename(str(img_data.get("filename") or "reel.mp4"))
    if not url:
        raise ValueError("Selected reel is missing its source URL.")
    if url.startswith("/"):
        raise ValueError("Selected reel uses a local browser URL that cannot be rendered directly.")

    ext = os.path.splitext(filename)[1] or ".mp4"
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="tips_source_")
    try:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name, True


def _safe_temp_suffix(filename, default=".jpg"):
    """Return a conservative extension for a temporary media file."""
    ext = os.path.splitext(os.path.basename(str(filename or "")))[1].lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", ext or ""):
        return ext
    return default


def _iter_airtable_attachments(fields, field_name):
    """Yield Airtable attachment dictionaries from one row field."""
    raw = fields.get(field_name) if isinstance(fields, dict) else None
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return
    for item in raw:
        if isinstance(item, dict) and item.get("url"):
            yield item


def _download_tips_reel_row_visual(img_data, image_dir):
    """Download the same-row image used for AI tip analysis.

    Priority follows the user's Airtable workflow: Blended Image first, then
    Styled Photo, then Moodboard Image. The rendered reel still uses the
    selected video as its source.
    """
    fields = img_data.get("fields") or {}
    os.makedirs(image_dir, exist_ok=True)

    for field_name in _TIPS_REEL_VISUAL_FIELDS:
        for attachment in _iter_airtable_attachments(fields, field_name):
            url = str(attachment.get("url") or "").strip()
            if not url:
                continue
            filename = attachment.get("filename") or f"{field_name}.jpg"
            suffix = _safe_temp_suffix(filename, ".jpg")
            slug = re.sub(r"[^a-z0-9]+", "_", field_name.lower()).strip("_") or "row_image"
            tmp = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix=f"tips_{slug}_",
                dir=image_dir,
            )
            try:
                with requests.get(url, timeout=180, stream=True) as resp:
                    resp.raise_for_status()
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            tmp.write(chunk)
                tmp.close()
                if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
                    return [tmp.name], field_name
            except Exception as exc:
                print(f"  Tips Reel row image download warning ({field_name}): {exc}")
                try:
                    tmp.close()
                except Exception:
                    pass
                try:
                    if os.path.exists(tmp.name):
                        os.unlink(tmp.name)
                except Exception:
                    pass
                continue
            finally:
                try:
                    tmp.close()
                except Exception:
                    pass

    return [], ""


def _probe_video_duration(video_path):
    """Return video duration in seconds, or None when probing fails."""
    proc = subprocess.run(
        [_ffmpeg_exe(), "-hide_banner", "-i", video_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        timeout=45,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _extract_tips_reel_frames(video_path, frame_dir, frame_count=1):
    """Extract one representative midpoint JPEG frame from a source reel."""
    os.makedirs(frame_dir, exist_ok=True)
    duration = _probe_video_duration(video_path)
    if duration and math.isfinite(duration) and duration > 0.5:
        positions = [duration * 0.5]
    else:
        positions = [0.5]

    paths = []
    last_error = None
    for idx, seconds in enumerate(positions[:frame_count], start=1):
        frame_path = os.path.join(frame_dir, f"frame_{idx}.jpg")
        try:
            subprocess.run(
                [
                    _ffmpeg_exe(),
                    "-y",
                    "-ss", f"{max(0.0, seconds):.2f}",
                    "-i", video_path,
                    "-frames:v", "1",
                    "-q:v", "3",
                    frame_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=90,
                check=True,
            )
            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                paths.append(frame_path)
        except Exception as exc:
            last_error = exc

    if not paths and last_error:
        raise RuntimeError(f"Could not extract video frames: {last_error}") from last_error
    if not paths:
        raise RuntimeError("Could not extract video frames.")
    return paths


def _wrap_tip_text(text, width=24):
    """Wrap short tip text into one or two overlay-safe lines."""
    words = re.sub(r"\s+", " ", str(text or "")).strip().split(" ")
    if not words:
        return "Style the focal piece with soft room balance"

    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width and len(lines) < 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines[:2])


def _tip_text_lines(text):
    """Return overlay text as one or two centered-safe lines."""
    wrapped = _wrap_tip_text(text)
    lines = [line.strip() for line in wrapped.splitlines() if line.strip()]
    return lines[:2] or ["Style the focal piece with soft room balance"]


def _escape_drawtext_text(text):
    """Escape text for ffmpeg drawtext."""
    text = str(text or "")
    text = text.replace("'", "’")
    text = text.replace('"', '”')
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace(",", "\\,")
    text = text.replace(";", "\\;")
    text = text.replace("%", "\\%")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    text = text.replace("\n", "\\n")
    return text


def _escape_filter_path(path):
    """Escape a Windows path for ffmpeg filter usage."""
    return str(path).replace("\\", "/").replace(":", "\\:")


def _tips_reel_font_clause():
    """Return a drawtext fontfile clause when a system font is available."""
    candidates = [
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeuib.ttf"),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arialbd.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return f"fontfile='{_escape_filter_path(path)}':"
    return ""


def _drawtext_filter(text, enable_expr, alpha_expr=None, y_expr="h*0.675", fontsize=46):
    """Build a drawtext filter segment for the Tips Reel overlay."""
    alpha_part = f":alpha={alpha_expr}" if alpha_expr else ""
    return (
        "drawtext="
        f"{_tips_reel_font_clause()}"
        f"text='{_escape_drawtext_text(text)}':"
        "x=(w-text_w)/2:"
        f"y={y_expr}:"
        f"fontsize={fontsize}:"
        "fontcolor=white:"
        "borderw=3:"
        "bordercolor=black@0.42:"
        "shadowx=0:"
        "shadowy=4:"
        "shadowcolor=black@0.34:"
        "fix_bounds=1:"
        f"enable={enable_expr}"
        f"{alpha_part}"
    )


def _build_tips_reel_filter(tip_text):
    """Build ffmpeg filter_complex for 9:16 blur-fit video and popup/fade tip text."""
    lines = _tip_text_lines(tip_text)
    filters = [
        "[0:v]split=2[bgsrc][fgsrc]",
        "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=32:2[bg]",
        "[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease[fg]",
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v0]",
    ]

    start = 0.45
    fade_in_end = 0.72
    fade_out_start = 3.25
    end = 4.08
    fade_in_duration = fade_in_end - start
    fade_out_duration = end - fade_out_start
    enable = f"between(t\\,{start:.2f}\\,{end:.2f})"
    alpha = (
        f"if(lt(t\\,{fade_in_end:.2f})\\,(t-{start:.2f})/{fade_in_duration:.2f}\\,"
        f"if(lt(t\\,{fade_out_start:.2f})\\,1\\,"
        f"if(lt(t\\,{end:.2f})\\,({end:.2f}-t)/{fade_out_duration:.2f}\\,0)))"
    )
    base_y = "h*0.655"
    if len(lines) == 1:
        y_exprs = [f"{base_y}+if(lt(t\\,{fade_in_end:.2f})\\,({fade_in_end:.2f}-t)*48\\,0)"]
    else:
        y_exprs = [
            f"{base_y}-30+if(lt(t\\,{fade_in_end:.2f})\\,({fade_in_end:.2f}-t)*48\\,0)",
            f"{base_y}+30+if(lt(t\\,{fade_in_end:.2f})\\,({fade_in_end:.2f}-t)*48\\,0)",
        ]

    current_label = "v0"
    for idx, line in enumerate(lines):
        next_label = f"v{idx + 1}"
        filters.append(
            f"[{current_label}]{_drawtext_filter(line, enable, alpha, y_exprs[idx])}[{next_label}]"
        )
        current_label = next_label
    return ";".join(filters), current_label


def _extract_first_url(value):
    """Return the first URL found in a nested API result payload."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        return _extract_first_url(parsed)
    if isinstance(value, list):
        for item in value:
            found = _extract_first_url(item)
            if found:
                return found
    if isinstance(value, dict):
        preferred_keys = (
            "audioUrl", "audio_url", "url", "downloadUrl", "download_url",
            "resultUrl", "result_url", "resultUrls", "result_urls", "urls",
        )
        for key in preferred_keys:
            if key in value:
                found = _extract_first_url(value.get(key))
                if found:
                    return found
        for item in value.values():
            found = _extract_first_url(item)
            if found:
                return found
    return None


def _kie_voiceover_enabled():
    """Return whether Tips Reel voiceover should be attempted."""
    key = str(KIE_API_KEY or "").strip()
    return bool(key and key.lower() not in {"your_token_here", "none", "null"})


def _create_kie_voiceover_task(tip_text):
    """Create a KIE ElevenLabs dialogue task and return task id."""
    if not _kie_voiceover_enabled():
        return None
    payload = {
        "model": "elevenlabs/text-to-dialogue-v3",
        "input": {
            "dialogue": [
                {
                    "text": re.sub(r"\s+", " ", str(tip_text or "")).strip(),
                    "voice": KIE_VOICE_ID,
                }
            ],
            "stability": KIE_STABILITY,
        },
    }
    if KIE_CALLBACK_URL:
        payload["callBackUrl"] = KIE_CALLBACK_URL
    resp = requests.post(
        f"{KIE_API_BASE_URL}/api/v1/jobs/createTask",
        headers={
            "Authorization": f"Bearer {KIE_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(data.get("msg") or "KIE voiceover task failed.")
    task_id = ((data.get("data") or {}).get("taskId") or data.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError("KIE did not return a voiceover task id.")
    return task_id


def _poll_kie_voiceover_url(task_id):
    """Poll KIE task status and return the generated audio URL."""
    deadline = time.monotonic() + max(1, int(KIE_POLL_TIMEOUT_SECONDS or 1))
    interval = max(1, int(KIE_POLL_INTERVAL_SECONDS or 1))
    last_state = ""
    while time.monotonic() < deadline:
        resp = requests.get(
            f"{KIE_API_BASE_URL}/api/v1/jobs/recordInfo",
            headers={"Authorization": f"Bearer {KIE_API_KEY}"},
            params={"taskId": task_id},
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        detail = data.get("data") or {}
        state = str(detail.get("state") or "").strip().lower()
        last_state = state or last_state
        if state == "success":
            audio_url = _extract_first_url(detail.get("resultJson") or detail.get("result") or detail)
            if audio_url:
                return audio_url
            raise RuntimeError("KIE voiceover completed without an audio URL.")
        if state == "fail":
            raise RuntimeError(detail.get("failMsg") or "KIE voiceover generation failed.")
        time.sleep(interval)
    raise TimeoutError(f"KIE voiceover timed out while task was {last_state or 'pending'}.")


def _download_kie_voiceover(tip_text, work_dir):
    """Generate and download one KIE voiceover audio file, or return None on fallback."""
    if not _kie_voiceover_enabled():
        return None
    try:
        task_id = _create_kie_voiceover_task(tip_text)
        if not task_id:
            return None
        audio_url = _poll_kie_voiceover_url(task_id)
        suffix = _safe_temp_suffix(audio_url.split("?", 1)[0], ".mp3")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="tips_voice_", dir=work_dir)
        try:
            with requests.get(audio_url, timeout=180, stream=True) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        tmp.write(chunk)
            tmp.close()
            if os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
                return tmp.name
        finally:
            try:
                tmp.close()
            except Exception:
                pass
        return None
    except Exception as exc:
        print(f"  Tips Reel voiceover warning: {exc}")
        return None


def _render_tips_reel_video(input_path, output_path, tip_text, force_silent_audio=False, voiceover_path=None):
    """Render a 9:16 MP4 with blurred duplicate background and animated text."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    filter_complex, output_label = _build_tips_reel_filter(tip_text)
    tmp_output = f"{output_path}.tmp.mp4"
    if os.path.exists(tmp_output):
        os.unlink(tmp_output)

    command = [
        _ffmpeg_exe(),
        "-y",
        "-i", input_path,
    ]
    if voiceover_path and os.path.exists(voiceover_path):
        command.extend(["-i", voiceover_path])
    elif force_silent_audio:
        command.extend([
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        ])
    command.extend([
        "-filter_complex", filter_complex,
        "-map", f"[{output_label}]",
    ])
    if voiceover_path and os.path.exists(voiceover_path):
        command.extend(["-map", "1:a", "-r", "30"])
        command.extend(["-af", "apad"])
    elif force_silent_audio:
        command.extend(["-map", "1:a", "-r", "30"])
    else:
        command.extend(["-map", "0:a?"])
    command.extend([
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        "-shortest",
        tmp_output,
    ])
    proc = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        timeout=900,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "FFmpeg render failed.").strip()[-1800:])
    os.replace(tmp_output, output_path)
    return output_path


def _concat_tips_reel_segments(segment_paths, output_path):
    """Concatenate normalized Tips Reel segments into one final MP4."""
    segment_paths = [path for path in segment_paths if path and os.path.exists(path)]
    if len(segment_paths) != 3:
        raise ValueError("Combined Tips Reel requires exactly three rendered segments.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    list_path = os.path.join(os.path.dirname(output_path), f"concat_{uuid.uuid4().hex[:10]}.txt")
    tmp_output = f"{output_path}.tmp.mp4"
    if os.path.exists(tmp_output):
        os.unlink(tmp_output)
    try:
        with open(list_path, "w", encoding="utf-8") as fh:
            for path in segment_paths:
                safe_path = os.path.abspath(path).replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{safe_path}'\n")
        command = [
            _ffmpeg_exe(),
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-movflags", "+faststart",
            tmp_output,
        ]
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=900,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "FFmpeg concat failed.").strip()[-1800:])
        os.replace(tmp_output, output_path)
        return output_path
    finally:
        try:
            if os.path.exists(list_path):
                os.unlink(list_path)
        except Exception:
            pass


def _set_fetch_session(session_id, session):
    """Replace or create a fetch session entry."""
    with _fetch_sessions_lock:
        _fetch_sessions[session_id] = session


def _get_fetch_session(session_id):
    """Return a fetch session dict by id, if it exists."""
    with _fetch_sessions_lock:
        return _fetch_sessions.get(session_id)


def _update_fetch_session_images(session_id, images):
    """Replace the stored images for a fetch session."""
    with _fetch_sessions_lock:
        session = _fetch_sessions.get(session_id)
        if not session:
            return None
        session["images"] = list(images)
        return session


def _append_fetch_session_images(session_id, items):
    """Append streamed images to the stored fetch session."""
    with _fetch_sessions_lock:
        session = _fetch_sessions.get(session_id)
        if not session:
            return None
        session["images"].extend(items)
        return session


def _upsert_fetch_session_combo_item(session_id, combo_item):
    """Add or replace a synthetic combined Tips Reel item in a fetch session."""
    with _fetch_sessions_lock:
        session = _fetch_sessions.get(session_id)
        if not session:
            return None
        images = session.setdefault("images", [])
        combo_key = combo_item.get("combo_key")
        for idx, item in enumerate(images):
            if item.get("type") == _TIPS_REEL_COMBO_TYPE and item.get("combo_key") == combo_key:
                images[idx] = combo_item
                return session
        images.append(combo_item)
        return session


def _resolve_media_context(session_id=None):
    """Return (images, cache_base, cache_key) for a fetch session or legacy globals."""
    session = _resolve_media_session(session_id)
    if session:
        return session.get("images", []), session.get("base_id"), session.get("cache_key")
    return None, None, None


def _resolve_media_session(session_id=None):
    """Return the active media-session dict for a fetch session or legacy globals."""
    if session_id:
        return _get_fetch_session(session_id)
    field_name = None if _paired_mode else _fetch_cache_key
    return {
        "images": _images,
        "base_id": _fetch_base_id,
        "cache_key": _fetch_cache_key,
        "field_name": field_name,
        "paired_fields": None,
        "triple_fields": None,
        "zoho_folder_id": None,
        "category_id": None,
    }


def _get_session_field_name(session, img_data=None):
    """Return the source Airtable field for a media session, when available."""
    if isinstance(session, dict):
        field_name = str(session.get("field_name") or "").strip()
        if field_name:
            return field_name
        cache_key = str(session.get("cache_key") or "").strip()
        if cache_key and "+" not in cache_key and not cache_key.startswith("zoho_") and not cache_key.startswith("local:"):
            return cache_key
    if isinstance(img_data, dict):
        return str(img_data.get("source_field") or "").strip() or None
    return None


def _is_status_sync_target(img_data, field_name):
    """Return True when this media item should archive status changes to Zoho."""
    if field_name != "Blended Image":
        return False
    if not isinstance(img_data, dict) or img_data.get("local_upload"):
        return False
    if img_data.get("type") not in (None, "", "single"):
        return False
    return bool(str(img_data.get("url") or "").strip() and str(img_data.get("filename") or "").strip())


def _get_zoho_status_folder_id(field_name, status):
    """Resolve the Zoho folder id configured for one field/status pair."""
    status_map = ZOHO_STATUS_FOLDER_MAP.get(field_name, {})
    if isinstance(status_map, dict):
        folder_id = str(status_map.get(status) or "").strip()
        if folder_id:
            return folder_id
    if field_name == "Blended Image" and status == "disregard":
        legacy_folder_id = str(ZOHO_FIELD_FOLDER_MAP.get(field_name) or "").strip()
        if legacy_folder_id:
            return legacy_folder_id
    return None


def _format_error_message(error, fallback):
    """Return a user-safe error string for UI/status messages."""
    text = str(error or "").strip()
    return text or fallback


def _download_media_bytes(img_data):
    """Download the current media file so it can be re-uploaded to Zoho."""
    filename = os.path.basename(str((img_data or {}).get("filename") or "").strip())
    url = str((img_data or {}).get("url") or "").strip()
    if not filename or not url:
        raise ValueError("The selected media item is missing its file URL.")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return filename, resp.content


def _sync_media_status_to_zoho(img_data, field_name, status):
    """Upload a media file to the Zoho folder configured for one status."""
    folder_id = _get_zoho_status_folder_id(field_name, status)
    if not folder_id:
        raise ValueError(f"No Zoho folder is configured for {field_name} -> {status}.")
    filename, file_data = _download_media_bytes(img_data)
    upload_file_to_workdrive(folder_id, filename, file_data)
    return {"folder_id": folder_id, "filename": filename}


def _format_post_target_filename(img_data):
    """Return a compact filename summary for logging."""
    if not isinstance(img_data, dict):
        return "-"
    img_type = img_data.get("type")
    if img_type == "pair":
        return " | ".join(
            str(part.get("filename") or "-") for part in (img_data.get("left", {}), img_data.get("right", {}))
        )
    if img_type == "triple":
        return " | ".join(
            str(part.get("filename") or "-")
            for part in (img_data.get("left", {}), img_data.get("center", {}), img_data.get("right", {}))
        )
    return str(img_data.get("filename") or "-")


def _build_local_upload_item(upload_id, file_path, filename, source_field=None, fields=None):
    """Create an image record shaped like the existing single-image entries."""
    source_field = _normalize_local_source_field(source_field)
    return {
        "type": "single",
        "url": f"/local_upload/{upload_id}",
        "thumb_url": f"/local_upload/{upload_id}",
        "filename": filename,
        "fields": dict(fields or {}),
        "local_upload": True,
        "local_path": file_path,
        "upload_id": upload_id,
        "record_id": None,
        "base_id": None,
        "table_id": None,
        "source_field": source_field,
    }


def _build_local_upload_item_from_entry(entry):
    """Convert a persisted local-upload entry into the media item shape used by the UI."""
    return _build_local_upload_item(
        entry["upload_id"],
        entry["path"],
        entry["filename"],
        source_field=entry.get("source_field"),
        fields=entry.get("fields"),
    )


def _list_local_upload_items(source_field):
    """Return the current queued uploads for a local category."""
    source_field = _normalize_local_source_field(source_field)
    with _local_uploads_lock:
        entries = list(_local_upload_lists.get(source_field, []))
    return [_build_local_upload_item_from_entry(entry) for entry in entries]


def _set_local_session_items(source_field, session_id, items):
    """Store local-upload items in a media session so posting/captioning can reuse it."""
    source_field = _normalize_local_source_field(source_field)
    category_id = _category_id_from_session_id(session_id)
    _set_fetch_session(session_id, {
        "images": list(items),
        "base_id": None,
        "cache_key": f"local:{source_field}",
        "field_name": None,
        "paired_fields": None,
        "triple_fields": None,
        "zoho_folder_id": None,
        "source_field": source_field,
        "category_id": category_id,
    })


def _update_local_upload_fields(upload_id, fields):
    """Persist field mutations such as SB Posted for a local upload."""
    with _local_uploads_lock:
        entry = _local_uploads.get(upload_id)
        if not entry:
            return False
        entry["fields"] = dict(fields or {})
        _save_local_upload_manifest_unlocked()
        return True


# ── Tips Reel Video Upload persistence ──

def _save_tips_reel_upload_manifest_unlocked():
    """Persist the tips reel upload manifest. Caller must hold _tips_reel_uploads_lock."""
    os.makedirs(os.path.dirname(_tips_reel_upload_manifest_path), exist_ok=True)
    payload = {
        "version": 1,
        "items": [
            {
                "upload_id": entry["upload_id"],
                "filename": entry["filename"],
                "stored_name": entry["stored_name"],
                "category_id": entry.get("category_id", "tips-reels"),
                "fields": dict(entry.get("fields", {})),
            }
            for entry in _tips_reel_upload_list
        ],
    }
    with open(_tips_reel_upload_manifest_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=2)


def _load_tips_reel_upload_manifest():
    """Restore persisted tips reel video uploads on startup."""
    data = {}
    try:
        if os.path.exists(_tips_reel_upload_manifest_path):
            with open(_tips_reel_upload_manifest_path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh) or {}
    except Exception as exc:
        print(f"Tips reel upload manifest load warning: {exc}")
        data = {}

    raw_items = data.get("items", []) if isinstance(data, dict) else []
    changed = False

    with _tips_reel_uploads_lock:
        _tips_reel_upload_list.clear()
        _tips_reel_uploads.clear()
        if not isinstance(raw_items, list):
            raw_items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                changed = True
                continue
            upload_id = str(raw.get("upload_id") or "").strip()
            filename = os.path.basename(str(raw.get("filename") or "").strip())
            stored_name = os.path.basename(str(raw.get("stored_name") or "").strip())
            category_id = str(raw.get("category_id") or "tips-reels").strip()
            if not upload_id or not filename or not stored_name:
                changed = True
                continue
            file_path = os.path.join(_tips_reel_upload_root, stored_name)
            if not os.path.exists(file_path):
                changed = True
                continue
            entry = {
                "upload_id": upload_id,
                "filename": filename,
                "stored_name": stored_name,
                "category_id": category_id,
                "fields": dict(raw.get("fields") or {}),
                "path": file_path,
            }
            _tips_reel_upload_list.append(entry)
            _tips_reel_uploads[upload_id] = entry
        if changed:
            _save_tips_reel_upload_manifest_unlocked()


def _build_tips_reel_upload_item(entry):
    """Create a media item from a persisted tips reel video upload entry."""
    upload_id = entry["upload_id"]
    return {
        "type": "single",
        "url": f"/tips_reel_upload/{upload_id}",
        "thumb_url": f"/tips_reel_upload/{upload_id}",
        "filename": entry["filename"],
        "fields": dict(entry.get("fields", {})),
        "tips_reel_upload": True,
        "local_upload": False,
        "local_path": entry.get("path", ""),
        "upload_id": upload_id,
        "record_id": None,
        "base_id": None,
        "table_id": None,
        "source_field": None,
        "category_id": entry.get("category_id", "tips-reels"),
    }


def _list_tips_reel_upload_items(category_id=None):
    """Return queued video uploads, optionally filtered by category."""
    with _tips_reel_uploads_lock:
        entries = list(_tips_reel_upload_list)
    if category_id:
        entries = [e for e in entries if e.get("category_id") == category_id]
    return [_build_tips_reel_upload_item(entry) for entry in entries]


_load_local_upload_manifest()
_load_disregard_manifest()
_load_tips_reel_manifest()
_load_tips_reel_upload_manifest()


@eel.expose
def get_local_uploads(source_field=None, session_id=None):
    """Return persisted local uploads for one category and optionally bind them to a session."""
    source_field = _normalize_local_source_field(source_field)
    items = _list_local_upload_items(source_field)
    if session_id:
        if _is_combined_local_upload_session(session_id):
            existing_session = _get_fetch_session(session_id)
            existing_upload_ids = set()
            if existing_session:
                existing_upload_ids = {
                    img.get("upload_id")
                    for img in (existing_session.get("images") or [])
                    if img.get("upload_id")
                }
            new_items = [item for item in items if item.get("upload_id") not in existing_upload_ids]
            if new_items and existing_session:
                _append_fetch_session_images(session_id, new_items)
        else:
            _set_local_session_items(source_field, session_id, items)
    return _serialize_images(items)


@eel.expose
def delete_local_upload(upload_id, source_field=None, session_id=None):
    """Delete a persisted local upload and return the updated queue for its category."""
    source_field = _normalize_local_source_field(source_field)
    removed_path = None
    removed = False

    with _local_uploads_lock:
        entries = _local_upload_lists.get(source_field, [])
        next_entries = []
        for entry in entries:
            if entry["upload_id"] == upload_id:
                removed = True
                removed_path = entry.get("path")
                _local_uploads.pop(upload_id, None)
                continue
            next_entries.append(entry)
        _local_upload_lists[source_field] = next_entries
        if removed:
            _save_local_upload_manifest_unlocked()

    if removed_path and os.path.exists(removed_path):
        try:
            os.unlink(removed_path)
        except Exception as exc:
            print(f"Local upload delete warning ({removed_path}): {exc}")

    if not removed:
        return {"ok": False, "error": "Upload not found.", "images": []}

    items = _list_local_upload_items(source_field)
    if session_id:
        if _is_combined_local_upload_session(session_id):
            existing_session = _get_fetch_session(session_id)
            if existing_session:
                kept_images = [
                    img for img in (existing_session.get("images") or [])
                    if not (img.get("local_upload") and img.get("source_field") == source_field)
                ]
                _update_fetch_session_images(session_id, kept_images + items)
        else:
            _set_local_session_items(source_field, session_id, items)
    return {"ok": True, "images": _serialize_images(items)}


@bottle.post('/local_upload_photo')
def local_upload_photo():
    """Accept a single uploaded photo and append it to a persistent local queue."""
    global _current_index, _fetch_base_id, _fetch_cache_key, _paired_mode, _paired_field_name

    upload = bottle.request.files.get("photo")
    if not upload or not upload.filename:
        bottle.response.status = 400
        bottle.response.content_type = "application/json"
        return json.dumps({"ok": False, "error": "No photo was uploaded."})

    filename = os.path.basename(upload.filename)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
    if ext not in allowed_exts:
        bottle.response.status = 400
        bottle.response.content_type = "application/json"
        return json.dumps({"ok": False, "error": "Please upload an image file."})

    upload_id = uuid.uuid4().hex
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in filename)
    if not safe_name:
        safe_name = f"upload{ext or '.jpg'}"
    source_field = _normalize_local_source_field(bottle.request.forms.get("source_field"))
    session_id = bottle.request.forms.get("session_id") or None
    stored_name = f"{upload_id}_{safe_name}"
    file_path = os.path.join(_local_upload_dir_for_field(source_field), stored_name)
    upload.save(file_path, overwrite=True)

    entry = {
        "upload_id": upload_id,
        "filename": filename,
        "stored_name": stored_name,
        "source_field": source_field,
        "fields": {},
        "path": file_path,
    }

    with _local_uploads_lock:
        _local_upload_lists.setdefault(source_field, []).append(entry)
        _local_uploads[upload_id] = entry
        _save_local_upload_manifest_unlocked()

    item = _build_local_upload_item_from_entry(entry)
    items = _list_local_upload_items(source_field)
    if session_id:
        if _is_combined_local_upload_session(session_id):
            existing_session = _get_fetch_session(session_id)
            if existing_session:
                _append_fetch_session_images(session_id, [item])
            else:
                _set_fetch_session(session_id, {
                    "images": [item],
                    "base_id": None,
                    "cache_key": f"upload:{_category_id_from_session_id(session_id) or 'blended-image'}",
                    "field_name": None,
                    "paired_fields": None,
                    "triple_fields": None,
                    "zoho_folder_id": None,
                    "category_id": _category_id_from_session_id(session_id),
                })
        else:
            _set_local_session_items(source_field, session_id, items)
    else:
        with _images_lock:
            _images[:] = items
            _current_index = len(items) - 1
        _fetch_base_id = None
        _fetch_cache_key = None
        _paired_mode = False
        _paired_field_name = None

    bottle.response.content_type = "application/json"
    return json.dumps({"ok": True, "item": _serialize_one(item), "images": _serialize_images(items)})


@bottle.get('/local_upload/<upload_id>')
def serve_local_upload(upload_id):
    """Serve an uploaded photo back to the browser for preview/posting."""
    with _local_uploads_lock:
        info = _local_uploads.get(upload_id)
    if not info:
        return bottle.HTTPError(404, "Upload not found.")

    file_path = info.get("path")
    if not file_path or not os.path.exists(file_path):
        with _local_uploads_lock:
            entry = _local_uploads.pop(upload_id, None)
            if entry:
                entries = _local_upload_lists.get(entry["source_field"], [])
                _local_upload_lists[entry["source_field"]] = [
                    item for item in entries if item["upload_id"] != upload_id
                ]
                _save_local_upload_manifest_unlocked()
        return bottle.HTTPError(404, "Upload not found.")

    bottle.response.set_header("Cache-Control", "no-store")
    return bottle.static_file(os.path.basename(file_path), root=os.path.dirname(file_path))


@bottle.post('/tips_reel_upload_video')
def tips_reel_upload_video():
    """Accept a single uploaded video and persist it for Tips Reel / Styled Reel use."""
    upload = bottle.request.files.get("video")
    if not upload or not upload.filename:
        bottle.response.status = 400
        bottle.response.content_type = "application/json"
        return json.dumps({"ok": False, "error": "No video was uploaded."})

    filename = os.path.basename(upload.filename)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in VIDEO_EXTENSIONS:
        bottle.response.status = 400
        bottle.response.content_type = "application/json"
        return json.dumps({"ok": False, "error": f"Unsupported video format '{ext}'. Use .mp4, .mov, .avi, .mkv, .webm, or .m4v."})

    upload_id = uuid.uuid4().hex
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in filename)
    if not safe_name:
        safe_name = f"upload{ext or '.mp4'}"
    category_id = bottle.request.forms.get("category_id") or "tips-reels"
    session_id = bottle.request.forms.get("session_id") or None
    stored_name = f"{upload_id}_{safe_name}"
    file_path = os.path.join(_tips_reel_upload_root, stored_name)
    upload.save(file_path, overwrite=True)

    entry = {
        "upload_id": upload_id,
        "filename": filename,
        "stored_name": stored_name,
        "category_id": category_id,
        "fields": {},
        "path": file_path,
    }

    with _tips_reel_uploads_lock:
        _tips_reel_upload_list.append(entry)
        _tips_reel_uploads[upload_id] = entry
        _save_tips_reel_upload_manifest_unlocked()

    item = _build_tips_reel_upload_item(entry)

    # Register the item in the backend fetch session so post_to_sb can resolve it
    if session_id:
        session = _get_fetch_session(session_id)
        if session:
            _append_fetch_session_images(session_id, [item])
        else:
            _set_fetch_session(session_id, {
                "images": [item],
                "base_id": None,
                "cache_key": f"upload:{category_id}",
                "field_name": None,
                "paired_fields": None,
                "triple_fields": None,
                "zoho_folder_id": None,
                "source_field": None,
                "category_id": category_id,
            })

    bottle.response.content_type = "application/json"
    return json.dumps({"ok": True, "item": _serialize_one(item)})


@bottle.get('/tips_reel_upload/<upload_id>')
def serve_tips_reel_upload(upload_id):
    """Serve a previously uploaded video back to the browser."""
    with _tips_reel_uploads_lock:
        info = _tips_reel_uploads.get(upload_id)
    if not info:
        return bottle.HTTPError(404, "Upload not found.")

    file_path = info.get("path")
    if not file_path or not os.path.exists(file_path):
        with _tips_reel_uploads_lock:
            _tips_reel_uploads.pop(upload_id, None)
            _tips_reel_upload_list[:] = [
                item for item in _tips_reel_upload_list if item["upload_id"] != upload_id
            ]
            _save_tips_reel_upload_manifest_unlocked()
        return bottle.HTTPError(404, "Upload not found.")

    bottle.response.set_header("Cache-Control", "no-store")
    return bottle.static_file(os.path.basename(file_path), root=os.path.dirname(file_path))


@eel.expose
def get_tips_reel_uploads(session_id=None):
    """Return persisted video uploads for the tips reel categories."""
    category_id = _category_id_from_session_id(session_id)
    items = _list_tips_reel_upload_items(category_id)

    # Append uploaded items to the backend fetch session so post_to_sb can resolve them
    if session_id and items:
        session = _get_fetch_session(session_id)
        if session:
            existing_ids = {
                img.get("upload_id") for img in session.get("images", []) if img.get("upload_id")
            }
            new_items = [item for item in items if item.get("upload_id") not in existing_ids]
            if new_items:
                _append_fetch_session_images(session_id, new_items)

    return _serialize_images(items)


@eel.expose
def delete_tips_reel_upload(upload_id, session_id=None):
    """Delete a persisted tips reel video upload."""
    removed_path = None
    removed = False

    with _tips_reel_uploads_lock:
        entry = _tips_reel_uploads.pop(upload_id, None)
        if entry:
            removed = True
            removed_path = entry.get("path")
            _tips_reel_upload_list[:] = [
                item for item in _tips_reel_upload_list if item["upload_id"] != upload_id
            ]
            _save_tips_reel_upload_manifest_unlocked()

    if removed_path and os.path.exists(removed_path):
        try:
            os.unlink(removed_path)
        except Exception as exc:
            print(f"Tips reel upload delete warning ({removed_path}): {exc}")

    if not removed:
        return {"ok": False, "error": "Upload not found."}
    return {"ok": True}


@eel.expose
def fetch_images(base_id, field_name=None, paired_fields=None, triple_fields=None, zoho_folder_id=None, session_id=None):
    """Start background Airtable fetch. Calls JS callbacks with progress and results."""
    if not session_id:
        session_id = uuid.uuid4().hex
    category_id = _category_id_from_session_id(session_id)

    if zoho_folder_id:
        cache_key = f"zoho_{zoho_folder_id}"
    elif triple_fields:
        cache_key = f"{triple_fields[0]}+{triple_fields[1]}+{triple_fields[2]}"
    elif paired_fields:
        cache_key = f"{paired_fields[0]}+{paired_fields[1]}"
    else:
        cache_key = field_name or "Blended Image"

    _set_fetch_session(session_id, {
        "images": [],
        "base_id": base_id,
        "cache_key": cache_key,
        "field_name": field_name,
        "paired_fields": list(paired_fields) if paired_fields else None,
        "triple_fields": list(triple_fields) if triple_fields else None,
        "zoho_folder_id": zoho_folder_id,
        "category_id": category_id,
    })

    def _do():
        try:
            def progress(done, total, count):
                try:
                    with _eel_lock:
                        eel.on_fetch_progress(done, total, count, session_id)
                except Exception:
                    pass

            def batch(items):
                _apply_disregard_flags(items, category_id)
                _append_fetch_session_images(session_id, items)
                try:
                    with _eel_lock:
                        eel.on_images_appended(_serialize_images(items), session_id)
                except Exception as e:
                    print(f"Batch emit warning: {e}")

            if zoho_folder_id:
                # 1. Fetch Zoho WorkDrive files
                token = get_valid_token()
                url = f"https://workdrive.zoho.com/api/v1/files/{zoho_folder_id}/files"
                headers = {"Authorization": f"Zoho-oauthtoken {token}"}
                resp = requests.get(url, headers=headers)
                resp.raise_for_status()
                zoho_files = resp.json().get("data") or []

                # 2. Index folder files. If a filename starts with an Airtable
                # record id, we can still enrich it with Airtable metadata.
                zoho_entries = []
                record_id_to_zoho = {}
                for zf in zoho_files:
                    if not isinstance(zf, dict):
                        continue
                    name = zf.get("attributes", {}).get("name", "")
                    ext = os.path.splitext(name)[1].lower()
                    if ext and ext not in VIDEO_EXTENSIONS:
                        continue

                    entry = {
                        "file_id": zf.get("id"),
                        "filename": name,
                        "url": f"/zoho_video/{zf.get('id')}",
                    }
                    if not entry["file_id"]:
                        continue
                    zoho_entries.append(entry)

                    parts = name.split('_', 1)
                    if parts and parts[0].startswith("rec"):
                        record_id_to_zoho[parts[0]] = entry

                records = []
                matched_file_ids = set()

                if base_id and record_id_to_zoho:
                    # 3. Fetch Airtable records only when the folder naming scheme
                    # includes record ids. Otherwise the folder is treated as the
                    # source of truth on its own.
                    all_records = fetch_all_records_for_base(
                        base_id, progress_callback=progress, field_name="Blended Image"
                    )

                    for rec in all_records:
                        rid = rec.get("record_id")
                        if rid in record_id_to_zoho:
                            z = record_id_to_zoho[rid]
                            matched_file_ids.add(z["file_id"])
                            records.append({
                                "type": "zoho",
                                "record_id": rid,
                                "base_id": base_id,
                                "table_id": rec.get("table_id", ""),
                                "fields": rec.get("fields", {}),
                                "url": z["url"],
                                "filename": z["filename"],
                                "file_id": z["file_id"]
                            })

                for z in zoho_entries:
                    if z["file_id"] in matched_file_ids:
                        continue
                    records.append({
                        "type": "zoho",
                        "record_id": None,
                        "base_id": None,
                        "table_id": None,
                        "fields": {},
                        "url": z["url"],
                        "filename": z["filename"],
                        "file_id": z["file_id"],
                    })
            elif triple_fields:
                records = fetch_triple_records_for_base(
                    base_id, triple_fields[0], triple_fields[1], triple_fields[2],
                    progress_callback=progress,
                    batch_callback=batch,
                )
            elif paired_fields:
                records = fetch_paired_records_for_base(
                    base_id, paired_fields[0], paired_fields[1],
                    progress_callback=progress,
                    batch_callback=batch,
                )
            else:
                records = fetch_all_records_for_base(
                    base_id, progress_callback=progress,
                    field_name=field_name,
                    batch_callback=batch,
                )

            # Cache-hit path: no batches were streamed, so _images is still empty.
            # Normal path: streamed batches already populated the session, but we
            # also reconcile from `records` as the authoritative list (same data,
            # but this way order matches what gets cached).
            _apply_disregard_flags(records, category_id)
            _update_fetch_session_images(session_id, records)
            
            # Stream cached results in chunks for instant feedback
            chunk_size = 50
            for i in range(0, len(records), chunk_size):
                chunk = records[i:i+chunk_size]
                with _eel_lock:
                    eel.on_images_appended(_serialize_images(chunk), session_id)

            # Signal loaded (finalizes state and ensures UI is in sync)
            data = _serialize_images(records)
            with _eel_lock:
                eel.on_images_loaded(data, session_id)

        except Exception as e:
            print(f"Fetch error: {e}")
            traceback.print_exc()
            try:
                with _eel_lock:
                    eel.on_fetch_error(str(e), session_id)
            except Exception:
                pass

    threading.Thread(target=_do, daemon=True).start()


def _serialize_one(img):
    """Convert a single image dict to a JSON-safe shape."""
    try:
        if not isinstance(img, dict):
            return None
            
        d = {}
        if img.get("type") == "triple":
            d["type"] = "triple"
            d["left"] = {
                "url": img["left"]["url"],
                "thumb_url": img["left"].get("thumb_url", img["left"]["url"]),
                "filename": img["left"]["filename"],
                "label": img["left"].get("label", "Blended Image"),
            }
            d["center"] = {
                "url": img["center"]["url"],
                "thumb_url": img["center"].get("thumb_url", img["center"]["url"]),
                "filename": img["center"]["filename"],
                "label": img["center"].get("label", "Closeup Photo One"),
            }
            d["right"] = {
                "url": img["right"]["url"],
                "thumb_url": img["right"].get("thumb_url", img["right"]["url"]),
                "filename": img["right"]["filename"],
                "label": img["right"].get("label", "Closeup Photo Two"),
            }
        elif img.get("type") == _TIPS_REEL_COMBO_TYPE:
            d["type"] = _TIPS_REEL_COMBO_TYPE
            d["url"] = img.get("url") or ""
            d["thumb_url"] = img.get("thumb_url") or img.get("url") or ""
            d["filename"] = img.get("filename") or "combined_tips_reel.mp4"
            d["combo_key"] = img.get("combo_key")
            d["source_indices"] = list(img.get("source_indices") or [])
            d["source_count"] = int(img.get("source_count") or len(img.get("source_items") or []) or 3)
        elif img.get("type") == "zoho":
            d["type"] = "zoho"
            d["url"] = img["url"]
            d["thumb_url"] = img.get("thumb_url", img["url"])
            d["filename"] = img["filename"]
        elif img.get("type") == "pair":
            d["type"] = "pair"
            d["left"] = {
                "url": img["left"]["url"],
                "thumb_url": img["left"].get("thumb_url", img["left"]["url"]),
                "filename": img["left"]["filename"],
                "label": img["left"].get("label", "Before"),
            }
            d["right"] = {
                "url": img["right"]["url"],
                "thumb_url": img["right"].get("thumb_url", img["right"]["url"]),
                "filename": img["right"]["filename"],
                "label": img["right"].get("label", "After"),
            }
        else:
            # SINGLE image
            d["type"] = "single"
            d["url"] = img["url"]
            d["thumb_url"] = img.get("thumb_url", img["url"])
            d["filename"] = img["filename"]

        d["fields"] = img.get("fields", {})
        d["local_upload"] = bool(img.get("local_upload"))
        d["upload_id"] = img.get("upload_id")
        d["record_id"] = img.get("record_id")
        d["base_id"] = img.get("base_id")
        d["table_id"] = img.get("table_id")
        d["file_id"] = img.get("file_id")
        d["source_field"] = img.get("source_field")
        d["tips_reel_upload"] = bool(img.get("tips_reel_upload"))
        d["tips_reel"] = _serialize_tips_reel_status_for_item(img)
        return d
    except Exception as e:
        print(f"  Warning: could not serialize item: {e}")
        return None


def _serialize_images(images):
    """Convert image list to JSON-safe dicts."""
    if not images:
        return []
    serialized = [_serialize_one(img) for img in images]
    return [s for s in serialized if s is not None]


@eel.expose
def refresh_cache():
    clear_cache()


@eel.expose
def get_item_names_for_index(index):
    """Get item names for display."""
    if index < 0 or index >= len(_images):
        return ""
    if _images[index].get("local_upload"):
        field_name = _images[index].get("source_field")
        if field_name == TIPS_EDU_FIELD:
            return "Tips and Education upload"
        if field_name == QUOTES_PHOTOS_FIELD:
            return "Quotes Photos upload"
        if field_name == BLENDED_IMAGE_LOCAL_FIELD:
            return "Blended Image upload"
        return "Collection Category upload"
    fields = _images[index].get("fields", {})
    return get_item_names(fields)


def _caption_text_context_from_fields(fields):
    """Build compact non-attachment text context for LM Studio captions."""
    if not isinstance(fields, dict):
        return ""

    context_parts = []
    for key, val in fields.items():
        if isinstance(val, (dict, tuple)):
            continue
        if isinstance(val, list):
            if not val or any(isinstance(item, dict) for item in val):
                continue
            text = ", ".join(str(item).strip() for item in val if str(item).strip())
        else:
            text = str(val).strip() if val is not None else ""

        if not text:
            continue
        if len(text) > 300:
            text = text[:297].rstrip() + "..."
        context_parts.append(f"{key}: {text}")
        if sum(len(part) for part in context_parts) > 3500:
            break

    return "\n".join(context_parts)


def _caption_visual_inputs_from_item(img_data):
    """Return labeled image inputs for single, pair, and triple Airtable cards."""
    if not isinstance(img_data, dict):
        return []

    if img_data.get("type") == "pair":
        slots = [("Before", img_data.get("left") or {}), ("After", img_data.get("right") or {})]
    elif img_data.get("type") == "triple":
        slots = [
            ("Blended Image", img_data.get("left") or {}),
            ("Closeup Photo One", img_data.get("center") or {}),
            ("Closeup Photo Two", img_data.get("right") or {}),
        ]
    elif img_data.get("type") in (None, "", "single"):
        slots = [(str(img_data.get("source_field") or "").strip(), img_data)]
    else:
        return []

    inputs = []
    for idx, (default_label, slot) in enumerate(slots, start=1):
        url = str(slot.get("url") or "").strip()
        if not url:
            continue
        label = str(default_label or slot.get("label") or slot.get("filename") or f"Image {idx}").strip()
        inputs.append({"label": label, "url": url})
    return inputs


@eel.expose
def generate_caption(index, session_id=None):
    """Generate AI caption in background. Calls on_caption_ready or on_caption_error."""
    images_ref, _, _ = _resolve_media_context(session_id)
    if images_ref is None or index < 0 or index >= len(images_ref):
        return

    def _do():
        try:
            img_data = images_ref[index]
            fields = img_data.get("fields", {})
            if img_data.get("local_upload"):
                local_path = img_data["local_path"]
                if local_path.lower().endswith(tuple(VIDEO_EXTENSIONS)):
                    # For video uploads, extract a single frame to use for caption generation
                    frame_dir = tempfile.mkdtemp(prefix="caption_frame_")
                    try:
                        frames = _extract_tips_reel_frames(local_path, frame_dir, frame_count=1)
                        ai_line = generate_local_image_caption(frames[0])
                    finally:
                        try:
                            import shutil
                            shutil.rmtree(frame_dir)
                        except Exception:
                            pass
                else:
                    ai_line = generate_local_image_caption(local_path)
                item_names = ""
            elif (
                not img_data.get("tips_reel_upload")
                and not str(img_data.get("filename") or "").lower().endswith(tuple(VIDEO_EXTENSIONS))
                and img_data.get("type") in (None, "", "single", "pair", "triple")
            ):
                visual_inputs = _caption_visual_inputs_from_item(img_data)
                context = _caption_text_context_from_fields(fields)
                visual_context = (
                    "You are looking at one product or interior image from Airtable."
                    if len(visual_inputs) == 1
                    else "You are looking at a related image set from the same Airtable row."
                )
                ai_line = generate_lmstudio_visual_caption(
                    visual_inputs,
                    text_context=context,
                    visual_context=visual_context,
                    fallback_on_exhausted=False,
                )
                item_names = get_item_names(fields)
            else:
                ai_line = generate_short_caption(img_data)
                item_names = get_item_names(fields)
            full_caption = compose_caption(ai_line, item_names)
            with _eel_lock:
                eel.on_caption_ready(full_caption)
        except Exception as e:
            with _eel_lock:
                eel.on_caption_error(str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def prepare_tips_reel(index, session_id=None, force=False):
    """Convert a selected Styled Reel into a cached 9:16 Tips Reel."""
    session = _resolve_media_session(session_id)
    images_ref = session.get("images", []) if session else None
    if images_ref is None or index < 0 or index >= len(images_ref):
        return {"ok": False, "error": "Media item not found."}

    img_data = images_ref[index]
    if img_data.get("type") in ("pair", "triple"):
        return {"ok": False, "error": "Tips Reel conversion supports one video at a time."}
    if _serialize_tips_reel_status_for_item(img_data) is None:
        return {"ok": False, "error": "Selected item is not a supported reel video."}

    media_key = _build_tips_reel_key(img_data)
    current = _get_tips_reel_status(media_key)
    if current["status"] == "ready" and not force:
        _emit_tips_reel_status(index, session_id, img_data, current)
        return {"ok": True, "status": current}
    if current["status"] in ("queued", "downloading_source", "analyzing_frames", "writing_tip", "generating_voiceover", "rendering"):
        _emit_tips_reel_status(index, session_id, img_data, current)
        return {"ok": True, "status": current}

    source_filename = os.path.basename(str(img_data.get("filename") or "styled_reel.mp4"))
    queued = _set_tips_reel_status(
        media_key,
        "queued",
        source_filename=source_filename,
    )
    _emit_tips_reel_status(index, session_id, img_data, queued)

    def _do():
        source_path = None
        should_delete_source = False
        frame_dir = tempfile.mkdtemp(prefix="tips_frames_")
        current_step = "Queued"
        try:
            current_step = "Downloading source video"
            downloading = _set_tips_reel_status(
                media_key,
                "downloading_source",
                label=current_step,
                voiceover_error="",
            )
            _emit_tips_reel_status(index, session_id, img_data, downloading)
            source_path, should_delete_source = _download_tips_reel_source(img_data)

            current_step = "Analyzing row image"
            analyzing = _set_tips_reel_status(media_key, "analyzing_frames", label=current_step)
            _emit_tips_reel_status(index, session_id, img_data, analyzing)
            visual_paths, visual_source = _download_tips_reel_row_visual(img_data, frame_dir)
            if not visual_paths:
                visual_paths = _extract_tips_reel_frames(source_path, frame_dir)
                visual_source = "Video Frame"
            current_step = f"Analyzing {visual_source}"
            analyzing = _set_tips_reel_status(
                media_key,
                "analyzing_frames",
                label=current_step,
                visual_source=visual_source,
            )
            _emit_tips_reel_status(index, session_id, img_data, analyzing)

            current_step = "Writing AI tip"
            writing = _set_tips_reel_status(
                media_key,
                "writing_tip",
                label=current_step,
                visual_source=visual_source,
            )
            _emit_tips_reel_status(index, session_id, img_data, writing)

            item_names = get_item_names(img_data.get("fields", {}))
            tip = generate_video_tip_from_frames(
                visual_paths,
                item_names=item_names,
                filename=source_filename,
            )

            render_version = uuid.uuid4().hex[:12]
            output_filename = f"tips_reel_{media_key}_{render_version}.mp4"
            output_path = os.path.join(_tips_reel_root, output_filename)

            voiceover_path = None
            if _kie_voiceover_enabled():
                current_step = "Generating voiceover"
                voiceover_status = _set_tips_reel_status(
                    media_key,
                    "generating_voiceover",
                    label=current_step,
                    tip=tip,
                    visual_source=visual_source,
                )
                _emit_tips_reel_status(index, session_id, img_data, voiceover_status)
                voiceover_path = _download_kie_voiceover(tip, frame_dir)

            current_step = "Rendering 9:16 video"
            rendering_label = current_step if voiceover_path else "Rendering 9:16 video without voiceover"
            voiceover_error = "" if voiceover_path or not _kie_voiceover_enabled() else "Voiceover failed, rendering without voiceover."
            rendering = _set_tips_reel_status(
                media_key,
                "rendering",
                label=rendering_label,
                tip=tip,
                visual_source=visual_source,
                voiceover=bool(voiceover_path),
                voiceover_error=voiceover_error,
            )
            _emit_tips_reel_status(index, session_id, img_data, rendering)
            _render_tips_reel_video(
                source_path,
                output_path,
                tip,
                force_silent_audio=True,
                voiceover_path=voiceover_path,
            )

            ready = _set_tips_reel_status(
                media_key,
                "ready",
                tip=tip,
                filename=output_filename,
                render_version=render_version,
                visual_source=visual_source,
                voiceover=bool(voiceover_path),
                voiceover_error=voiceover_error,
            )
            _cleanup_old_tips_reel_files(media_key, output_filename)
            _emit_tips_reel_status(index, session_id, img_data, ready)
        except Exception as exc:
            error = _set_tips_reel_status(
                media_key,
                "error",
                label=f"Error at {current_step}",
                error=_format_error_message(exc, "Tips Reel conversion failed."),
            )
            _emit_tips_reel_status(index, session_id, img_data, error)
        finally:
            if should_delete_source and source_path and os.path.exists(source_path):
                try:
                    os.unlink(source_path)
                except Exception:
                    pass
            try:
                shutil.rmtree(frame_dir, ignore_errors=True)
            except Exception:
                pass

    threading.Thread(target=_do, daemon=True).start()
    return {"ok": True, "status": queued}


def _combo_item_payload(combo_key, source_items, source_indices, filename=None):
    """Build the in-session synthetic media item for one combined Tips Reel."""
    first = source_items[0] if source_items else {}
    status = _get_tips_reel_status(combo_key)
    output_filename = filename or status.get("filename") or f"tips_reel_{combo_key}.mp4"
    item_names = get_item_names(first.get("fields", {})) if isinstance(first, dict) else ""
    title = item_names or "Combined Tips Reel"
    return {
        "type": _TIPS_REEL_COMBO_TYPE,
        "combo_key": combo_key,
        "url": status.get("url") or "",
        "thumb_url": status.get("url") or "",
        "filename": output_filename,
        "source_indices": list(source_indices or []),
        "source_items": list(source_items or []),
        "source_count": len(source_items or []) or 3,
        "fields": {
            "Item Name from File": title,
            "Item Name from File2": "3 combined Tips Reel clips",
            "SB Posted": False,
            "Disregard": False,
        },
        "record_id": None,
        "base_id": None,
        "table_id": None,
        "source_field": "Combined Tips Reel",
    }


def _validate_combined_tips_reel_items(indices, images_ref):
    """Return ordered source items for a combined Tips Reel request."""
    if not isinstance(indices, list) or len(indices) != 3:
        raise ValueError("Select exactly 3 reel videos to combine.")
    ordered_indices = []
    seen = set()
    for raw in indices:
        idx = int(raw)
        if idx in seen:
            raise ValueError("Select 3 different reel videos to combine.")
        if idx < 0 or idx >= len(images_ref):
            raise ValueError("One selected reel is no longer available.")
        seen.add(idx)
        ordered_indices.append(idx)

    source_items = [images_ref[idx] for idx in ordered_indices]
    for item in source_items:
        if item.get("type") in ("pair", "triple", _TIPS_REEL_COMBO_TYPE):
            raise ValueError("Combined Tips Reel requires 3 single source videos.")
        if _serialize_tips_reel_status_for_item(item) is None:
            raise ValueError("One selected item is not a supported reel video.")
    return ordered_indices, source_items


@eel.expose
def prepare_combined_tips_reel(indices, session_id=None, force=False):
    """Convert exactly three selected reels into one combined 9:16 Tips Reel."""
    session = _resolve_media_session(session_id)
    images_ref = session.get("images", []) if session else None
    if images_ref is None:
        return {"ok": False, "error": "Media session not found."}

    try:
        source_indices, source_items = _validate_combined_tips_reel_items(indices, images_ref)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    media_key = _build_combined_tips_reel_key(source_items)
    current = _get_tips_reel_status(media_key)
    combo_item = _combo_item_payload(media_key, source_items, source_indices)

    if current["status"] == "ready" and not force:
        combo_item = _combo_item_payload(media_key, source_items, source_indices, current.get("filename"))
        _upsert_fetch_session_combo_item(session_id, combo_item)
        _emit_combined_tips_reel_status(session_id, combo_item)
        return {"ok": True, "item": _serialize_one(combo_item), "status": current}
    if current["status"] in ("queued", "downloading_source", "analyzing_frames", "writing_tip", "generating_voiceover", "rendering"):
        _upsert_fetch_session_combo_item(session_id, combo_item)
        _emit_combined_tips_reel_status(session_id, combo_item)
        return {"ok": True, "item": _serialize_one(combo_item), "status": current}

    queued = _set_tips_reel_status(
        media_key,
        "queued",
        label="Queued 3-clip Tips Reel",
        source_count=3,
        source_filenames=[os.path.basename(str(item.get("filename") or "")) for item in source_items],
    )
    combo_item = _combo_item_payload(media_key, source_items, source_indices)
    _upsert_fetch_session_combo_item(session_id, combo_item)
    _emit_combined_tips_reel_status(session_id, combo_item)

    def _do():
        work_dir = tempfile.mkdtemp(prefix="tips_combo_")
        downloaded_sources = []
        segment_paths = []
        tips = []
        visual_sources = []
        voiceover_count = 0
        voiceover_error = ""
        current_step = "Queued"
        try:
            for clip_pos, item in enumerate(source_items, start=1):
                label_suffix = f"clip {clip_pos}/3"
                current_step = f"Downloading source video {label_suffix}"
                downloading = _set_tips_reel_status(
                    media_key,
                    "downloading_source",
                    label=current_step,
                    tips=tips,
                    visual_sources=visual_sources,
                    source_count=3,
                    voiceover_error=voiceover_error,
                )
                _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))

                source_path, should_delete_source = _download_tips_reel_source(item)
                if should_delete_source:
                    downloaded_sources.append(source_path)

                current_step = f"Analyzing row image {label_suffix}"
                _set_tips_reel_status(
                    media_key,
                    "analyzing_frames",
                    label=current_step,
                    tips=tips,
                    visual_sources=visual_sources,
                    source_count=3,
                    voiceover_error=voiceover_error,
                )
                _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))

                visual_dir = os.path.join(work_dir, f"visual_{clip_pos}")
                visual_paths, visual_source = _download_tips_reel_row_visual(item, visual_dir)
                if not visual_paths:
                    visual_paths = _extract_tips_reel_frames(source_path, visual_dir)
                    visual_source = "Video Frame"
                visual_sources.append(visual_source)

                current_step = f"Analyzing {visual_source} {label_suffix}"
                _set_tips_reel_status(
                    media_key,
                    "analyzing_frames",
                    label=current_step,
                    tips=tips,
                    visual_sources=visual_sources,
                    source_count=3,
                    voiceover_error=voiceover_error,
                )
                _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))

                current_step = f"Writing AI tip {label_suffix}"
                _set_tips_reel_status(
                    media_key,
                    "writing_tip",
                    label=current_step,
                    tips=tips,
                    visual_sources=visual_sources,
                    source_count=3,
                    voiceover_error=voiceover_error,
                )
                _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))

                tip = generate_video_tip_from_frames(
                    visual_paths,
                    item_names=get_item_names(item.get("fields", {})),
                    filename=os.path.basename(str(item.get("filename") or f"clip_{clip_pos}.mp4")),
                )
                tips.append(tip)

                segment_path = os.path.join(work_dir, f"segment_{clip_pos}.mp4")
                voiceover_path = None
                if _kie_voiceover_enabled():
                    current_step = f"Generating voiceover {label_suffix}"
                    _set_tips_reel_status(
                        media_key,
                        "generating_voiceover",
                        label=current_step,
                        tips=tips,
                        visual_sources=visual_sources,
                        source_count=3,
                        voiceover=voiceover_count > 0,
                        voiceover_error=voiceover_error,
                    )
                    _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))
                    voiceover_path = _download_kie_voiceover(tip, work_dir)
                    if not voiceover_path:
                        voiceover_error = "Voiceover failed for one or more clips, rendering without that voiceover."

                if voiceover_path:
                    voiceover_count += 1
                current_step = f"Rendering 9:16 video {label_suffix}"
                render_label = current_step if voiceover_path or not _kie_voiceover_enabled() else f"Rendering 9:16 video without voiceover {label_suffix}"
                _set_tips_reel_status(
                    media_key,
                    "rendering",
                    label=render_label,
                    tips=tips,
                    visual_sources=visual_sources,
                    source_count=3,
                    voiceover=voiceover_count > 0,
                    voiceover_error=voiceover_error,
                )
                _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))
                _render_tips_reel_video(
                    source_path,
                    segment_path,
                    tip,
                    force_silent_audio=True,
                    voiceover_path=voiceover_path,
                )
                segment_paths.append(segment_path)

            current_step = "Combining 3 clips"
            _set_tips_reel_status(
                media_key,
                "rendering",
                label=current_step,
                tips=tips,
                visual_sources=visual_sources,
                source_count=3,
                voiceover=voiceover_count > 0,
                voiceover_error=voiceover_error,
            )
            _emit_combined_tips_reel_status(session_id, _combo_item_payload(media_key, source_items, source_indices))

            render_version = uuid.uuid4().hex[:12]
            output_filename = f"tips_reel_{media_key}_{render_version}.mp4"
            output_path = os.path.join(_tips_reel_root, output_filename)
            _concat_tips_reel_segments(segment_paths, output_path)

            ready = _set_tips_reel_status(
                media_key,
                "ready",
                tip=" | ".join(tips),
                tips=tips,
                visual_sources=visual_sources,
                filename=output_filename,
                render_version=render_version,
                source_count=3,
                voiceover=voiceover_count > 0,
                voiceover_error=voiceover_error,
            )
            _cleanup_old_tips_reel_files(media_key, output_filename)
            ready_item = _combo_item_payload(media_key, source_items, source_indices, output_filename)
            _upsert_fetch_session_combo_item(session_id, ready_item)
            _emit_combined_tips_reel_status(session_id, ready_item)
        except Exception as exc:
            _set_tips_reel_status(
                media_key,
                "error",
                label=f"Combined Tips Reel error at {current_step}",
                error=_format_error_message(exc, "Combined Tips Reel conversion failed."),
                tips=tips,
                visual_sources=visual_sources,
                source_count=3,
                voiceover=voiceover_count > 0,
                voiceover_error=voiceover_error,
            )
            error_item = _combo_item_payload(media_key, source_items, source_indices)
            _upsert_fetch_session_combo_item(session_id, error_item)
            _emit_combined_tips_reel_status(session_id, error_item)
        finally:
            for path in downloaded_sources:
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except Exception:
                    pass
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    threading.Thread(target=_do, daemon=True).start()
    return {"ok": True, "item": _serialize_one(combo_item), "status": queued}


def _resolve_tips_reel_post_media(img_data, session):
    """Return rendered Tips Reel media details when posting from the Tips Reels lane."""
    category_id = session.get("category_id") if isinstance(session, dict) else None
    if category_id != "tips-reels":
        return None

    media_key = str(img_data.get("combo_key") or "").strip() if img_data.get("type") == _TIPS_REEL_COMBO_TYPE else _build_tips_reel_key(img_data)
    status = _get_tips_reel_status(media_key)
    if status.get("status") != "ready":
        raise ValueError("Convert this video to a Tips Reel before posting it.")

    local_path = _tips_reel_output_path(media_key, status)
    if not os.path.exists(local_path):
        raise ValueError("Rendered Tips Reel file is missing. Convert it again.")
    return {
        "url": status.get("url") or img_data.get("url"),
        "filename": status.get("filename") or f"tips_reel_{media_key}.mp4",
        "local_path": local_path,
    }


@eel.expose
def post_to_sb(index, caption, category, schedule_date, schedule_time, session_id=None):
    """Post to SocialBee (regular post). Calls on_post_result."""
    images_ref, _, _ = _resolve_media_context(session_id)
    if images_ref is None:
        with _eel_lock:
            eel.on_post_result("error", "No media session found. Try refreshing or re-uploading the video.")
        return
    if index < 0 or index >= len(images_ref):
        with _eel_lock:
            eel.on_post_result("error", f"Selected item (index {index}) is out of range ({len(images_ref)} items in session). Try refreshing.")
        return

    session = _get_fetch_session(session_id) if session_id else None
    img_data = images_ref[index]
    img_type = img_data.get("type") or "single"
    session_field = session.get("field_name") if session else None
    session_cache_key = session.get("cache_key") if session else None
    zoho_folder_id = session.get("zoho_folder_id") if session else None
    is_zoho_session = bool(zoho_folder_id)
    is_pair = img_type == "pair"
    result_queue = queue.Queue()

    is_triple = img_type == "triple"

    def _do():
        temp_local_path = None
        try:
            print(
                "[post_to_sb] "
                f"session_id={session_id or '-'} "
                f"field={session_field or '-'} "
                f"cache_key={session_cache_key or '-'} "
                f"zoho_session={is_zoho_session} "
                f"index={index} "
                f"type={img_type} "
                f"filename={_format_post_target_filename(img_data)} "
                f"file_id={img_data.get('file_id') or '-'}"
            )

            if is_zoho_session:
                if img_type != "zoho":
                    raise ValueError(
                        f"Expected a single Zoho reel for '{session_field or session_cache_key or 'this lane'}', "
                        f"but got '{img_type}'."
                    )
                if not img_data.get("file_id"):
                    raise ValueError(
                        f"Selected Zoho reel '{img_data.get('filename') or '-'}' is missing its WorkDrive file id."
                    )

            if is_triple:
                image_urls = [img_data["left"]["url"], img_data["center"]["url"], img_data["right"]["url"]]
                filenames = [img_data["left"]["filename"], img_data["center"]["filename"], img_data["right"]["filename"]]
                post_to_socialbee_multiple(
                    caption, image_urls, filenames,
                    category, schedule_date, schedule_time, result_queue,
                )
            elif is_pair:
                image_urls = [img_data["left"]["url"], img_data["right"]["url"]]
                filenames = [img_data["left"]["filename"], img_data["right"]["filename"]]
                post_to_socialbee_multiple(
                    caption, image_urls, filenames,
                    category, schedule_date, schedule_time, result_queue,
                )
            else:
                tips_media = _resolve_tips_reel_post_media(img_data, session or {})
                local_path = img_data.get("local_path")
                post_url = img_data["url"]
                post_filename = img_data["filename"]
                if tips_media:
                    local_path = tips_media["local_path"]
                    post_url = tips_media["url"]
                    post_filename = tips_media["filename"]
                elif img_data.get("type") == "zoho" and img_data.get("file_id"):
                    temp_local_path = _download_zoho_file(img_data["file_id"], img_data["filename"])
                    local_path = temp_local_path
                post_to_socialbee(
                    caption, post_url, post_filename,
                    category, schedule_date, schedule_time, result_queue,
                    local_path=local_path,
                )

            status, message = result_queue.get(timeout=600)
            with _eel_lock:
                eel.on_post_result(status, message)
        except Exception as e:
            with _eel_lock:
                eel.on_post_result("error", str(e))
        finally:
            if temp_local_path and os.path.exists(temp_local_path):
                try:
                    os.unlink(temp_local_path)
                except Exception:
                    pass

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def post_story_to_sb(index, caption, category, schedule_date, schedule_time, session_id=None):
    """Post to SocialBee Story. Calls on_post_story_result."""
    session = _resolve_media_session(session_id)
    images_ref, _, _ = _resolve_media_context(session_id)
    if images_ref is None:
        with _eel_lock:
            eel.on_post_story_result("error", "No media session found. Try refreshing or re-uploading the video.")
        return
    if index < 0 or index >= len(images_ref):
        with _eel_lock:
            eel.on_post_story_result("error", f"Selected item (index {index}) is out of range ({len(images_ref)} items in session). Try refreshing.")
        return

    img_data = images_ref[index]
    result_queue = queue.Queue()

    def _do():
        temp_local_path = None
        try:
            tips_media = _resolve_tips_reel_post_media(img_data, session or {})
            local_path = img_data.get("local_path")
            post_url = img_data["url"]
            post_filename = img_data["filename"]
            if tips_media:
                local_path = tips_media["local_path"]
                post_url = tips_media["url"]
                post_filename = tips_media["filename"]
            elif img_data.get("type") == "zoho" and img_data.get("file_id"):
                temp_local_path = _download_zoho_file(img_data["file_id"], img_data["filename"])
                local_path = temp_local_path
            post_to_socialbee_story(
                caption, post_url, post_filename,
                category, schedule_date, schedule_time, result_queue,
                local_path=local_path,
            )
            status, message = result_queue.get(timeout=600)
            with _eel_lock:
                eel.on_post_story_result(status, message)
        except Exception as e:
            with _eel_lock:
                eel.on_post_story_result("error", str(e))
        finally:
            if temp_local_path and os.path.exists(temp_local_path):
                try:
                    os.unlink(temp_local_path)
                except Exception:
                    pass

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def mark_posted(index, session_id=None):
    """Mark record as posted in Airtable. Calls on_posted_marked."""
    session = _resolve_media_session(session_id)
    if not session:
        return
    images_ref, cache_base, cache_key = _resolve_media_context(session_id)
    if images_ref is None or index < 0 or index >= len(images_ref):
        return

    def _do():
        img_data = images_ref[index]
        if img_data.get("type") == _TIPS_REEL_COMBO_TYPE:
            result = {"ok": True, "zohoSynced": False, "posted_indices": list(img_data.get("source_indices") or [])}
            failures = 0
            for source_item in img_data.get("source_items") or []:
                base_id = source_item.get("base_id")
                table_id = source_item.get("table_id")
                record_id = source_item.get("record_id")
                if all([base_id, table_id, record_id]):
                    if not mark_record_posted(base_id, table_id, record_id):
                        failures += 1
                        continue
                source_item.setdefault("fields", {})["SB Posted"] = True
            img_data.setdefault("fields", {})["SB Posted"] = failures == 0
            for source_idx in result["posted_indices"]:
                try:
                    if 0 <= int(source_idx) < len(images_ref):
                        images_ref[int(source_idx)].setdefault("fields", {})["SB Posted"] = failures == 0
                except Exception:
                    pass
            try:
                if cache_base and cache_key:
                    update_cache(cache_base, cache_key, images_ref)
            except Exception as e:
                print(f"Cache update warning: {e}")
            if failures:
                result["ok"] = False
                result["warning"] = f"Posted on SocialBee, but {failures} source Airtable row(s) could not be marked."
            with _eel_lock:
                eel.on_posted_marked(index, session_id, result)
            return

        field_name = _get_session_field_name(session, img_data)
        sync_target = _is_status_sync_target(img_data, field_name)
        result = {"ok": True, "zohoSynced": None}

        sync_error = None
        if sync_target:
            try:
                _sync_media_status_to_zoho(img_data, field_name, "posted")
                result["zohoSynced"] = True
            except Exception as exc:
                sync_error = _format_error_message(exc, "Zoho archive failed.")
                result["zohoSynced"] = False
                print(f"Zoho posted archive warning for {_format_post_target_filename(img_data)}: {sync_error}")

        if img_data.get("local_upload"):
            img_data.setdefault("fields", {})["SB Posted"] = True
            _update_local_upload_fields(img_data.get("upload_id"), img_data.get("fields", {}))
            if sync_error:
                result["warning"] = f"Posted successfully, but Zoho archive failed: {sync_error}"
            with _eel_lock:
                eel.on_posted_marked(index, session_id, result)
            return
        base_id = img_data.get("base_id")
        table_id = img_data.get("table_id")
        record_id = img_data.get("record_id")
        if not all([base_id, table_id, record_id]):
            img_data.setdefault("fields", {})["SB Posted"] = True
            try:
                if cache_base and cache_key:
                    update_cache(cache_base, cache_key, images_ref)
            except Exception as e:
                print(f"Cache update warning: {e}")
            if sync_error:
                result["warning"] = f"Posted successfully, but Zoho archive failed: {sync_error}"
            with _eel_lock:
                eel.on_posted_marked(index, session_id, result)
            return
        success = mark_record_posted(base_id, table_id, record_id)
        if success:
            img_data.setdefault("fields", {})["SB Posted"] = True
            try:
                if cache_base and cache_key:
                    update_cache(cache_base, cache_key, images_ref)
            except Exception as e:
                print(f"Cache update warning: {e}")
        else:
            result["ok"] = False

        if result["ok"]:
            if sync_error:
                result["warning"] = f"Posted and marked in Airtable, but Zoho archive failed: {sync_error}"
        else:
            if sync_error:
                result["warning"] = f"Posted on SocialBee, but Airtable mark failed. Zoho archive also failed: {sync_error}"
            else:
                result["warning"] = "Posted on SocialBee, but Airtable mark failed."
        with _eel_lock:
            eel.on_posted_marked(index, session_id, result)

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def toggle_disregard(index, disregard, session_id=None):
    """Toggle local disregard state for one media card in the active category."""
    session = _resolve_media_session(session_id)
    if not session:
        return {"ok": False, "error": "Media item not found."}
    images_ref, _, _ = _resolve_media_context(session_id)
    if images_ref is None or index < 0 or index >= len(images_ref):
        return {"ok": False, "error": "Media item not found."}

    category_id = _category_id_from_session_id(session_id)
    if not category_id:
        return {"ok": False, "error": "Category context is missing."}

    img_data = images_ref[index]
    field_name = _get_session_field_name(session, img_data)
    sync_target = _is_status_sync_target(img_data, field_name)
    if img_data.get("local_upload"):
        return {"ok": False, "error": "Disregard is not enabled for local uploads."}

    fields = img_data.setdefault("fields", {})
    if disregard and fields.get("SB Posted"):
        return {"ok": False, "error": "Posted items cannot be marked as disregard."}

    item_key = _build_disregard_key(img_data, category_id)
    if not item_key:
        return {"ok": False, "error": "Could not identify the selected media item."}

    if disregard and sync_target:
        try:
            _sync_media_status_to_zoho(img_data, field_name, "disregard")
        except Exception as exc:
            error_text = _format_error_message(exc, "Zoho archive failed.")
            print(f"Zoho disregard archive error for {_format_post_target_filename(img_data)}: {error_text}")
            return {"ok": False, "error": f"Zoho archive failed: {error_text}"}

    with _disregard_lock:
        if disregard:
            _disregard_state[item_key] = True
        else:
            _disregard_state.pop(item_key, None)
        _save_disregard_manifest_unlocked()

    _apply_disregard_flag(img_data, category_id)
    return {
        "ok": True,
        "disregard": bool(img_data.get("fields", {}).get("Disregard")),
        "zohoSynced": bool(disregard and sync_target),
        "message": (
            "Item moved to this category's Disregard tab and archived to Zoho."
            if disregard and sync_target else
            "Item moved to this category's Disregard tab."
            if disregard else
            "Item returned to this category's active queue. Zoho archive left in place."
            if sync_target else
            "Item returned to this category's active queue."
        ),
    }


@eel.expose
def disregard_records(indices, disregard, session_id=None):
    """Move discarded images to Zoho Workdrive and remove from Airtable."""
    if not disregard:
        print("Undo disregard not supported when items are moved directly to Zoho.")
        with _eel_lock:
            eel.on_disregard_done([], False)
        return

    images_ref, cache_base, cache_key = _resolve_media_context(session_id)
    if images_ref is None:
        with _eel_lock:
            eel.on_disregard_done([], False)
        return

    def _do():
        updated_by_base = {}
        successful_indices = []
        for idx in indices:
            if idx < 0 or idx >= len(images_ref):
                continue
            img_data = images_ref[idx]
            base_id = img_data.get("base_id")
            table_id = img_data.get("table_id")
            record_id = img_data.get("record_id")
            if not all([base_id, table_id, record_id]):
                continue

            is_pair = img_data.get("type") == "pair"
            is_triple = img_data.get("type") == "triple"
            if is_triple:
                items_to_process = [
                    (img_data["left"]["url"], img_data["left"]["filename"], img_data["left"].get("label")),
                    (img_data["center"]["url"], img_data["center"]["filename"], img_data["center"].get("label")),
                    (img_data["right"]["url"], img_data["right"]["filename"], img_data["right"].get("label"))
                ]
            elif is_pair:
                items_to_process = [
                    (img_data["left"]["url"], img_data["left"]["filename"], img_data["left"].get("label")),
                    (img_data["right"]["url"], img_data["right"]["filename"], img_data["right"].get("label"))
                ]
            elif img_data.get("type") == "zoho":
                # Video is already in Zoho, and not an attachment in Airtable.
                # Just let the routine mark it disregarded in Airtable below.
                items_to_process = []
            else:
                field_name = cache_key  # cache key for single is the field name
                items_to_process = [(img_data["url"], img_data["filename"], field_name)]

            success_for_item = False
            for url, filename, field_n in items_to_process:
                # 1. Download internally
                try:
                    resp = requests.get(url, timeout=60)
                    resp.raise_for_status()
                    file_data = resp.content
                except Exception as e:
                    print(f"Failed to download {filename} for disregard: {e}")
                    continue

                # 2. Upload to Zoho
                folder_id = ZOHO_FIELD_FOLDER_MAP.get(field_n)
                if folder_id:
                    try:
                        upload_file_to_workdrive(folder_id, filename, file_data)
                    except Exception as e:
                        print(f"Failed to upload {filename} to Zoho: {e}")
                        continue
                else:
                    print(f"No Zoho folder mapped for field '{field_n}'. Skipping upload.")

                # 3. Remove attachment specifically from Airtable
                rem_success = remove_specific_attachment(base_id, table_id, record_id, field_n, filename)
                if rem_success:
                    success_for_item = True

            if success_for_item:
                successful_indices.append(idx)
                img_data.setdefault("fields", {})["Disregard"] = True
                updated_by_base.setdefault(base_id, set()).add(record_id)
                
        try:
            if cache_base and cache_key:
                update_cache(cache_base, cache_key, images_ref)
        except Exception as e:
            print(f"Cache update warning: {e}")

        # Note: propagate_disregard is removed because the item is removed from Airtable entirely.
        with _eel_lock:
            eel.on_disregard_done(successful_indices, disregard)

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def add_watermark(index, position, current_src=""):
    """Add Home Cartel watermark to image. position: 'upper' or 'lower'."""
    if index < 0 or index >= len(_images):
        return

    def _do():
        try:
            from PIL import Image
            import base64
            from io import BytesIO

            # Use current displayed image if it's a base64 data URI (e.g. from IG Story conversion)
            if current_src and current_src.startswith("data:image"):
                b64_data = current_src.split(",", 1)[1]
                src_img = Image.open(BytesIO(base64.b64decode(b64_data))).convert("RGBA")
            else:
                img_data = _images[index]
                is_multi = img_data.get("type") in ("pair", "triple")
                if img_data.get("local_upload"):
                    src_img = Image.open(img_data["local_path"]).convert("RGBA")
                else:
                    url = img_data["left"]["url"] if is_multi else img_data["url"]
                    resp = requests.get(url, timeout=60)
                    resp.raise_for_status()
                    src_img = Image.open(BytesIO(resp.content)).convert("RGBA")

            # Load logo (transparent bg version)
            logo_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'web', 'assets', 'homecartel_logo.png'
            )
            if getattr(sys, 'frozen', False):
                logo_path = os.path.join(sys._MEIPASS, 'web', 'assets', 'homecartel_logo.png')
            logo = Image.open(logo_path).convert("RGBA")

            # Resize logo to ~15% of image width (visible size)
            img_w, img_h = src_img.size
            logo_w = int(img_w * 0.15)
            logo_ratio = logo.height / logo.width
            logo_h = int(logo_w * logo_ratio)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

            # Position with ~2% padding
            pad_x = int(img_w * 0.02)
            pad_y = int(img_h * 0.02)
            if position == "upper":
                pos = (pad_x, pad_y)
            else:
                pos = (pad_x, img_h - logo_h - pad_y)

            # Paste with transparency
            src_img.paste(logo, pos, logo)

            # Convert to RGB for JPEG output
            result = src_img.convert("RGB")
            buf = BytesIO()
            result.save(buf, "JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64}"

            with _eel_lock:
                eel.on_watermark_done(True, data_uri)
        except Exception as e:
            print(f"  Watermark error: {e}")
            with _eel_lock:
                eel.on_watermark_done(False, str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def convert_to_ig_story(index):
    """Convert image to 1080x1920 Instagram Story size. Calls on_story_converted."""
    if index < 0 or index >= len(_images):
        return

    def _do():
        try:
            from PIL import Image
            import base64
            img_data = _images[index]
            is_multi = img_data.get("type") in ("pair", "triple")
            if img_data.get("local_upload"):
                src_img = Image.open(img_data["local_path"]).convert("RGB")
            else:
                url = img_data["left"]["url"] if is_multi else img_data["url"]
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                from io import BytesIO
                src_img = Image.open(BytesIO(resp.content)).convert("RGB")

            # Target: 1080x1920 (9:16) — crop-to-fill (no black bars)
            target_w, target_h = 1080, 1920
            src_w, src_h = src_img.size

            # Scale to COVER the target (fill entirely), then center-crop
            scale = max(target_w / src_w, target_h / src_h)
            new_w = int(src_w * scale)
            new_h = int(src_h * scale)
            resized = src_img.resize((new_w, new_h), Image.LANCZOS)

            # Center crop to exact 1080x1920
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            result = resized.crop((left, top, left + target_w, top + target_h))

            # Convert to base64 data URI
            buf = BytesIO()
            result.save(buf, "JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64}"

            print(f"  Converted to IG Story: 1080x1920")
            with _eel_lock:
                eel.on_story_converted(True, data_uri)
        except Exception as e:
            print(f"  Story conversion error: {e}")
            with _eel_lock:
                eel.on_story_converted(False, str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def setup_chrome_post():
    """Open Chrome for post login setup."""
    def _do():
        try:
            setup_chrome_post_profile()
            with _eel_lock:
                eel.on_setup_done("Login saved! Headless posting ready.")
        except Exception as e:
            with _eel_lock:
                eel.on_setup_done(f"Setup error: {e}")

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def setup_chrome_story():
    """Open Chrome for story login setup."""
    def _do():
        try:
            setup_chrome_story_profile()
            with _eel_lock:
                eel.on_setup_done("Story login saved!")
        except Exception as e:
            with _eel_lock:
                eel.on_setup_done(f"Setup error: {e}")

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def download_video(url, filename):
    """Download video to temp file and open in system player."""
    def _do():
        try:
            ext = os.path.splitext(filename)[1] or ".mp4"
            resp = requests.get(url, timeout=300, stream=True)
            resp.raise_for_status()
            total = int(resp.headers.get('content-length', 0))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="sb_video_")
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                tmp.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded / total * 100)
                    with _eel_lock:
                        eel.on_video_progress(pct, downloaded / 1048576, total / 1048576)
            tmp.close()
            os.startfile(tmp.name)
            with _eel_lock:
                eel.on_video_progress(100, 0, 0)
        except Exception as e:
            print(f"Video download error: {e}")
            with _eel_lock:
                eel.on_video_progress(100, 0, 0)

    threading.Thread(target=_do, daemon=True).start()


# ── Entry Point ──

def main():
    # Determine web folder path (works both as script and frozen exe)
    if getattr(sys, 'frozen', False):
        web_dir = os.path.join(sys._MEIPASS, 'web')
    else:
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')

    eel.init(web_dir)

    # Point Eel to bundled Chromium when running as frozen exe
    if getattr(sys, 'frozen', False):
        from src.browser_utils import get_chromium_path
        bundled = get_chromium_path()
        if os.path.exists(bundled):
            import eel.browsers as browsers
            browsers.set_path('chrome', bundled)

    try:
        eel.start('index.html', size=(1400, 900), mode='chrome-app', port=0)
    except EnvironmentError:
        # Chrome not found, try Edge
        try:
            eel.start('index.html', size=(1400, 900), mode='edge', port=0)
        except EnvironmentError:
            # Fallback to default browser
            eel.start('index.html', size=(1400, 900), port=0)


if __name__ == '__main__':
    main()
