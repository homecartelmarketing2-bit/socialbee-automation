"""SocialBee AutoPoster — Eel Web UI backend."""
import eel
import os
import sys
import queue
import threading
import tempfile
import requests

from src.config import (
    APP_SOURCES, APP_FIELD_OPTIONS, PAIRED_FIELD_OPTIONS, TRIPLE_FIELD_OPTIONS,
    ZOHO_FETCH_OPTIONS, VIDEO_EXTENSIONS, ZOHO_FIELD_FOLDER_MAP
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
from src.caption import generate_short_caption, get_item_names, compose_caption
from src.socialbee_poster import (
    post_to_socialbee, post_to_socialbee_multiple,
    post_to_socialbee_story, setup_chrome_post_profile, setup_chrome_story_profile,
)

# ── State ──
_images = []
_images_lock = threading.Lock()
_current_index = 0
_paired_mode = False
_paired_field_name = None
_fetch_base_id = None
_fetch_cache_key = None
_fetch_id = 0
_result_queue = queue.Queue()


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


@eel.expose
def fetch_images(base_id, field_name=None, paired_fields=None, triple_fields=None, zoho_folder_id=None):
    """Start background Airtable fetch. Calls JS callbacks with progress and results."""
    global _images, _current_index, _paired_mode, _paired_field_name
    global _fetch_base_id, _fetch_cache_key, _fetch_id

    _fetch_base_id = base_id
    _paired_mode = paired_fields is not None or triple_fields is not None
    _paired_field_name = field_name if (paired_fields or triple_fields) else None

    if zoho_folder_id:
        _fetch_cache_key = f"zoho_{zoho_folder_id}"
    elif triple_fields:
        _fetch_cache_key = f"{triple_fields[0]}+{triple_fields[1]}+{triple_fields[2]}"
    elif paired_fields:
        _fetch_cache_key = f"{paired_fields[0]}+{paired_fields[1]}"
    else:
        _fetch_cache_key = field_name or "Blended Image"

    # Bump the fetch id so any in-flight batches from an older fetch are dropped
    # by the JS layer when a new fetch starts.
    _fetch_id += 1
    this_fetch_id = _fetch_id

    with _images_lock:
        _images.clear()
        _current_index = 0

    def _do():
        global _current_index
        try:
            def progress(done, total, count):
                if this_fetch_id != _fetch_id:
                    return
                try:
                    eel.on_fetch_progress(done, total, count)
                except Exception:
                    pass

            def batch(items):
                # Drop batches from a superseded fetch
                if this_fetch_id != _fetch_id:
                    return
                with _images_lock:
                    _images.extend(items)
                try:
                    eel.on_images_appended(_serialize_images(items), this_fetch_id)
                except Exception as e:
                    print(f"Batch emit warning: {e}")

            if zoho_folder_id:
                # 1. Fetch Zoho WorkDrive files
                token = get_valid_token()
                url = f"https://workdrive.zoho.com/api/v1/files/{zoho_folder_id}/files"
                headers = {"Authorization": f"Zoho-oauthtoken {token}"}
                resp = requests.get(url, headers=headers)
                zoho_files = resp.json().get("data", [])
                
                # 2. Extract record IDs from filenames
                record_id_to_zoho = {}
                for zf in zoho_files:
                    name = zf.get("attributes", {}).get("name", "")
                    parts = name.split('_')
                    if parts[0].startswith("rec"):
                        record_id_to_zoho[parts[0]] = {
                            "file_id": zf["id"],
                            "filename": name,
                            "url": f"/zoho_video/{zf['id']}" # Proxy URL
                        }
                
                # 3. Fetch all Airtable records (using "Blended Image" to leverage cache)
                all_records = fetch_all_records_for_base(
                    base_id, progress_callback=progress, field_name="Blended Image"
                )
                
                records = []
                for rec in all_records:
                    rid = rec.get("record_id")
                    if rid in record_id_to_zoho:
                        z = record_id_to_zoho[rid]
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
                # No batching for zoho mode right now, we just pass all records
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
            # Normal path: streamed batches already populated _images, but we
            # also reconcile from `records` as the authoritative list (same data,
            # but this way order matches what gets cached).
            if this_fetch_id == _fetch_id:
                with _images_lock:
                    if not _images:
                        _images.extend(records)
                    _current_index = 0
                data = _serialize_images(records)
                eel.on_images_loaded(data, this_fetch_id)

        except Exception as e:
            print(f"Fetch error: {e}")
            try:
                eel.on_images_loaded([], this_fetch_id)
            except Exception:
                pass

    threading.Thread(target=_do, daemon=True).start()


def _serialize_one(img):
    """Convert a single image dict to a JSON-safe shape."""
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
    elif img.get("type") == "zoho":
        d["type"] = "zoho"
        d["url"] = img["url"]
        d["thumb_url"] = img.get("thumb_url", img["url"])
        d["filename"] = img["filename"]
        d["file_id"] = img.get("file_id")
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
        d["type"] = "single"
        d["url"] = img["url"]
        d["thumb_url"] = img.get("thumb_url", img["url"])
        d["filename"] = img["filename"]

    d["fields"] = img.get("fields", {})
    d["record_id"] = img.get("record_id")
    d["base_id"] = img.get("base_id")
    d["table_id"] = img.get("table_id")
    return d


def _serialize_images(images):
    """Convert image list to JSON-safe dicts."""
    return [_serialize_one(img) for img in images]


@eel.expose
def refresh_cache():
    clear_cache()


@eel.expose
def get_item_names_for_index(index):
    """Get item names for display."""
    if index < 0 or index >= len(_images):
        return ""
    fields = _images[index].get("fields", {})
    return get_item_names(fields)


@eel.expose
def generate_caption(index):
    """Generate AI caption in background. Calls on_caption_ready or on_caption_error."""
    if index < 0 or index >= len(_images):
        return

    def _do():
        try:
            img_data = _images[index]
            fields = img_data.get("fields", {})
            ai_line = generate_short_caption(img_data)
            item_names = get_item_names(fields)
            full_caption = compose_caption(ai_line, item_names)
            eel.on_caption_ready(full_caption)
        except Exception as e:
            eel.on_caption_error(str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def post_to_sb(index, caption, category, schedule_date, schedule_time):
    """Post to SocialBee (regular post). Calls on_post_result."""
    if index < 0 or index >= len(_images):
        return

    img_data = _images[index]
    is_pair = img_data.get("type") == "pair"
    result_queue = queue.Queue()

    is_triple = img_data.get("type") == "triple"

    def _do():
        try:
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
                post_to_socialbee(
                    caption, img_data["url"], img_data["filename"],
                    category, schedule_date, schedule_time, result_queue,
                )

            status, message = result_queue.get(timeout=600)
            eel.on_post_result(status, message)
        except Exception as e:
            eel.on_post_result("error", str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def post_story_to_sb(index, caption, category, schedule_date, schedule_time):
    """Post to SocialBee Story. Calls on_post_story_result."""
    if index < 0 or index >= len(_images):
        return

    img_data = _images[index]
    result_queue = queue.Queue()

    def _do():
        try:
            post_to_socialbee_story(
                caption, img_data["url"], img_data["filename"],
                category, schedule_date, schedule_time, result_queue,
            )
            status, message = result_queue.get(timeout=600)
            eel.on_post_story_result(status, message)
        except Exception as e:
            eel.on_post_story_result("error", str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def mark_posted(index):
    """Mark record as posted in Airtable. Calls on_posted_marked."""
    if index < 0 or index >= len(_images):
        return

    cache_base = _fetch_base_id
    cache_key = _fetch_cache_key
    images_ref = _images

    def _do():
        img_data = images_ref[index]
        base_id = img_data.get("base_id")
        table_id = img_data.get("table_id")
        record_id = img_data.get("record_id")
        if not all([base_id, table_id, record_id]):
            return
        success = mark_record_posted(base_id, table_id, record_id)
        if success:
            img_data.setdefault("fields", {})["SB Posted"] = True
            try:
                if cache_base and cache_key:
                    update_cache(cache_base, cache_key, images_ref)
            except Exception as e:
                print(f"Cache update warning: {e}")
        eel.on_posted_marked(index)

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def disregard_records(indices, disregard):
    """Move discarded images to Zoho Workdrive and remove from Airtable."""
    if not disregard:
        print("Undo disregard not supported when items are moved directly to Zoho.")
        eel.on_disregard_done([], False)
        return

    cache_base = _fetch_base_id
    cache_key = _fetch_cache_key
    images_ref = _images

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

            eel.on_watermark_done(True, data_uri)
        except Exception as e:
            print(f"  Watermark error: {e}")
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
            url = img_data["left"]["url"] if is_multi else img_data["url"]

            # Download the image
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
            eel.on_story_converted(True, data_uri)
        except Exception as e:
            print(f"  Story conversion error: {e}")
            eel.on_story_converted(False, str(e))

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def setup_chrome_post():
    """Open Chrome for post login setup."""
    def _do():
        try:
            setup_chrome_post_profile()
            eel.on_setup_done("Login saved! Headless posting ready.")
        except Exception as e:
            eel.on_setup_done(f"Setup error: {e}")

    threading.Thread(target=_do, daemon=True).start()


@eel.expose
def setup_chrome_story():
    """Open Chrome for story login setup."""
    def _do():
        try:
            setup_chrome_story_profile()
            eel.on_setup_done("Story login saved!")
        except Exception as e:
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
                    eel.on_video_progress(pct, downloaded / 1048576, total / 1048576)
            tmp.close()
            os.startfile(tmp.name)
            eel.on_video_progress(100, 0, 0)
        except Exception as e:
            print(f"Video download error: {e}")
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
