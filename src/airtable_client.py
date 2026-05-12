import os
import json
import time
import hashlib
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from src.config import AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID, AIRTABLE_FIELD_NAME, HEADERS, APP_TABLE_IDS

# ─── Shared infrastructure ────────────────────────────────────

CACHE_DIR = os.path.join(tempfile.gettempdir(), "socialbee_cache")
CACHE_EXPIRY = 15 * 60  # 15 minutes — Airtable URLs expire in ~2 hours so this is safe

# Reuse TCP connections across all requests
_session = requests.Session()
_session.headers.update(HEADERS)


class _RateLimiter:
    """Throttle requests to stay under Airtable's 5 req/sec limit."""

    def __init__(self, max_per_second=4):
        self._lock = threading.Lock()
        self._min_interval = 1.0 / max_per_second
        self._last = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            wait_time = self._last + self._min_interval - now
            if wait_time > 0:
                time.sleep(wait_time)
            self._last = time.monotonic()


_rate_limiter = _RateLimiter(max_per_second=4)


# ─── Cache helpers ─────────────────────────────────────────────

def _cache_path(base_id, field_key):
    raw = f"{base_id}_{field_key}"
    h = hashlib.md5(raw.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")


def _load_cache(base_id, field_key):
    path = _cache_path(base_id, field_key)
    try:
        if os.path.exists(path):
            age = time.time() - os.path.getmtime(path)
            if age < CACHE_EXPIRY:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f), age
    except Exception:
        pass
    return None, 0


def _save_cache(base_id, field_key, data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _cache_path(base_id, field_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"  Cache save warning: {e}")


def update_cache(base_id, field_key, data):
    """Re-save cached data (e.g. after marking a record as posted)."""
    _save_cache(base_id, field_key, data)


def propagate_disregard(base_id, record_ids, disregard):
    """Update the 'Disregard' flag for the given record_ids across every cache file.

    The same Airtable record can appear in multiple field-specific caches
    (e.g. one record has both "Blended Image" and "Styled Photo" attachments).
    When the user toggles Disregard from one field, we walk all cache files for
    this base and patch matching records so the mark shows up after a field switch.
    """
    if not record_ids:
        return
    record_id_set = set(record_ids)
    try:
        if not os.path.isdir(CACHE_DIR):
            return
        for fname in os.listdir(CACHE_DIR):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(CACHE_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            modified = False
            for img in data:
                if not isinstance(img, dict):
                    continue
                if img.get("base_id") != base_id:
                    continue
                if img.get("record_id") in record_id_set:
                    img.setdefault("fields", {})["Disregard"] = disregard
                    modified = True
            if modified:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                except Exception as e:
                    print(f"  Disregard propagate warning ({fname}): {e}")
    except Exception as e:
        print(f"  Disregard propagate scan warning: {e}")


def clear_cache():
    """Delete all cached data (called from UI refresh button)."""
    try:
        if os.path.isdir(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                os.remove(os.path.join(CACHE_DIR, f))
            print("  Cache cleared")
    except Exception as e:
        print(f"  Cache clear warning: {e}")


# ─── Core: fetch a single table (with rate limiting + retry) ──

def _fetch_single_table(base_id, table_id, page_callback=None):
    """Fetch all records from one table. Handles pagination and rate limits."""
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
    records = []
    offset = None

    while True:
        _rate_limiter.wait()
        params = {}
        if offset:
            params["offset"] = offset

        try:
            resp = _session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                # Rate limited — back off and retry
                retry_after = int(resp.headers.get("Retry-After", 2))
                print(f"  Rate limited on {table_id}, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  Warning: table {table_id} error: {e}")
            break

        new_records = data.get("records") or []
        records.extend(new_records)
        
        if page_callback and new_records:
            try:
                page_callback(table_id, new_records)
            except Exception as e:
                print(f"  Page callback warning: {e}")

        offset = data.get("offset")
        if not offset:
            break

    return table_id, records


# ─── Public API: fetch all images (parallel + cached) ─────────

def fetch_raw_records_for_base(base_id):
    """Fetch raw records from ALL tables in a base (in parallel) without attachment filtering.
    Used for Zoho mode to reconcile record IDs."""
    table_ids = APP_TABLE_IDS.get(base_id, [])
    all_raw = []
    lock = threading.Lock()

    def _on_table_done(future):
        table_id, records = future.result()
        with lock:
            all_raw.extend(records)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for tid in table_ids:
            f = executor.submit(_fetch_single_table, base_id, tid)
            f.add_done_callback(_on_table_done)
            futures.append(f)
        for f in futures:
            f.result()

    return all_raw


def fetch_all_records_for_base(base_id, progress_callback=None, field_name=None, batch_callback=None):
    """Fetch all images from ALL tables in a base, in parallel with caching.

    If `batch_callback` is provided, it is called incrementally as each page 
    of records is fetched (streaming). The final aggregated list is still
    returned and cached as before.
    """
    use_field = field_name or AIRTABLE_FIELD_NAME
    table_ids = APP_TABLE_IDS.get(base_id, [])
    total_tables = len(table_ids)

    # 1. Try cache first
    cached, age = _load_cache(base_id, use_field)
    if cached is not None:
        mins = int(age // 60)
        print(f"  Loaded {len(cached)} images from cache ({mins}m ago)")
        if progress_callback:
            progress_callback(total_tables, total_tables, len(cached))
        return cached

    # 2. Parallel fetch from Airtable
    all_images = []
    completed = [0]
    lock = threading.Lock()

    def _process_records(tid, records):
        images = []
        for rec in records:
            fields = rec.get("fields", {})
            attachments = fields.get(use_field, [])
            if not isinstance(attachments, list):
                continue
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                img_url = att.get("url")
                filename = att.get("filename", "unknown")
                if img_url:
                    # Safely handle potentially null thumbnail objects
                    thumbnails = att.get("thumbnails") or {}
                    large_thumb = thumbnails.get("large") or {}
                    thumb_url = large_thumb.get("url") or img_url
                    
                    images.append({
                        "url": img_url,
                        "thumb_url": thumb_url,
                        "filename": filename,
                        "record_id": rec["id"],
                        "base_id": base_id,
                        "table_id": tid,
                        "fields": fields,
                    })
        return images

    def _on_page(tid, records):
        images = _process_records(tid, records)
        with lock:
            all_images.extend(images)
        if batch_callback and images:
            try:
                batch_callback(images)
            except Exception as e:
                print(f"  Batch callback warning: {e}")

    def _on_table_done(future):
        try:
            tid, records = future.result()
            with lock:
                completed[0] += 1
                if progress_callback:
                    progress_callback(completed[0], total_tables, len(all_images))
        except Exception as e:
            print(f"  Table fetch error: {e}")
            with lock:
                completed[0] += 1

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for tid in table_ids:
            # We use _on_page for immediate streaming, and _on_table_done for progress
            f = executor.submit(_fetch_single_table, base_id, tid, page_callback=_on_page)
            f.add_done_callback(_on_table_done)
            futures.append(f)
        # Wait for all to finish
        for f in futures:
            try:
                f.result()
            except Exception:
                pass

    # 3. Cache the result
    _save_cache(base_id, use_field, all_images)

    return all_images


def fetch_paired_records_for_base(base_id, field1, field2, progress_callback=None, batch_callback=None):
    """Fetch records that have BOTH field1 and field2, in parallel with caching.

    If `batch_callback` is provided, it is called with the per-table pair list
    as each table finishes (streaming).
    """
    cache_key = f"{field1}+{field2}"
    table_ids = APP_TABLE_IDS.get(base_id, [])
    total_tables = len(table_ids)

    # 1. Try cache first
    cached, age = _load_cache(base_id, cache_key)
    if cached is not None:
        mins = int(age // 60)
        print(f"  Loaded {len(cached)} pairs from cache ({mins}m ago)")
        if progress_callback:
            progress_callback(total_tables, total_tables, len(cached))
        return cached

    # 2. Parallel fetch
    all_pairs = []
    completed = [0]
    lock = threading.Lock()

    def _on_table_done(future):
        table_id, records = future.result()
        pairs = []
        for rec in records:
            fields = rec.get("fields", {})
            att1 = fields.get(field1, [])
            att2 = fields.get(field2, [])
            if not att1 or not att2:
                continue
            img1 = att1[0] if isinstance(att1, list) else None
            img2 = att2[0] if isinstance(att2, list) else None
            if img1 and img2 and img1.get("url") and img2.get("url"):
                # Safely handle potentially null thumbnail objects
                thumb1 = (img1.get("thumbnails") or {}).get("large") or {}
                thumb2 = (img2.get("thumbnails") or {}).get("large") or {}
                
                pairs.append({
                    "type": "pair",
                    "left": {
                        "url": img1["url"],
                        "thumb_url": thumb1.get("url") or img1["url"],
                        "filename": img1.get("filename", "image1.jpg"),
                        "label": field1,
                    },
                    "right": {
                        "url": img2["url"],
                        "thumb_url": thumb2.get("url") or img2["url"],
                        "filename": img2.get("filename", "image2.jpg"),
                        "label": field2,
                    },
                    "record_id": rec["id"],
                    "base_id": base_id,
                    "table_id": table_id,
                    "fields": fields,
                })
        with lock:
            all_pairs.extend(pairs)
            completed[0] += 1
            if progress_callback:
                progress_callback(completed[0], total_tables, len(all_pairs))
        if batch_callback and pairs:
            try:
                batch_callback(pairs)
            except Exception as e:
                print(f"  Batch callback warning: {e}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for tid in table_ids:
            f = executor.submit(_fetch_single_table, base_id, tid)
            f.add_done_callback(_on_table_done)
            futures.append(f)
        for f in futures:
            f.result()

    # 3. Cache
    _save_cache(base_id, cache_key, all_pairs)

    return all_pairs


def fetch_triple_records_for_base(base_id, field1, field2, field3, progress_callback=None, batch_callback=None):
    """Fetch records that have ALL three fields, in parallel with caching.

    If `batch_callback` is provided, it is called with the per-table triple list
    as each table finishes (streaming).
    """
    cache_key = f"{field1}+{field2}+{field3}"
    table_ids = APP_TABLE_IDS.get(base_id, [])
    total_tables = len(table_ids)

    # 1. Try cache first
    cached, age = _load_cache(base_id, cache_key)
    if cached is not None:
        mins = int(age // 60)
        print(f"  Loaded {len(cached)} triples from cache ({mins}m ago)")
        if progress_callback:
            progress_callback(total_tables, total_tables, len(cached))
        return cached

    # 2. Parallel fetch
    all_triples = []
    completed = [0]
    lock = threading.Lock()

    def _on_table_done(future):
        table_id, records = future.result()
        triples = []
        for rec in records:
            fields = rec.get("fields", {})
            att1 = fields.get(field1, [])
            att2 = fields.get(field2, [])
            att3 = fields.get(field3, [])
            if not att1 or not att2 or not att3:
                continue
            img1 = att1[0] if isinstance(att1, list) else None
            img2 = att2[0] if isinstance(att2, list) else None
            img3 = att3[0] if isinstance(att3, list) else None
            if img1 and img2 and img3 and img1.get("url") and img2.get("url") and img3.get("url"):
                # Safely handle potentially null thumbnail objects
                thumb1 = (img1.get("thumbnails") or {}).get("large") or {}
                thumb2 = (img2.get("thumbnails") or {}).get("large") or {}
                thumb3 = (img3.get("thumbnails") or {}).get("large") or {}
                
                triples.append({
                    "type": "triple",
                    "left": {
                        "url": img1["url"],
                        "thumb_url": thumb1.get("url") or img1["url"],
                        "filename": img1.get("filename", "image1.jpg"),
                        "label": field1,
                    },
                    "center": {
                        "url": img2["url"],
                        "thumb_url": thumb2.get("url") or img2["url"],
                        "filename": img2.get("filename", "image2.jpg"),
                        "label": field2,
                    },
                    "right": {
                        "url": img3["url"],
                        "thumb_url": thumb3.get("url") or img3["url"],
                        "filename": img3.get("filename", "image3.jpg"),
                        "label": field3,
                    },
                    "record_id": rec["id"],
                    "base_id": base_id,
                    "table_id": table_id,
                    "fields": fields,
                })
        with lock:
            all_triples.extend(triples)
            completed[0] += 1
            if progress_callback:
                progress_callback(completed[0], total_tables, len(all_triples))
        if batch_callback and triples:
            try:
                batch_callback(triples)
            except Exception as e:
                print(f"  Batch callback warning: {e}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for tid in table_ids:
            f = executor.submit(_fetch_single_table, base_id, tid)
            f.add_done_callback(_on_table_done)
            futures.append(f)
        for f in futures:
            f.result()

    # 3. Cache
    _save_cache(base_id, cache_key, all_triples)

    return all_triples


# ─── Public API: mark record as posted ────────────────────────

def mark_record_posted(base_id, table_id, record_id):
    """Mark a record as posted by setting the 'SB Posted' checkbox to True."""
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    _rate_limiter.wait()
    try:
        resp = _session.patch(url, json={"fields": {"SB Posted": True}})
        if resp.status_code == 422:
            print(f"  Warning: 'SB Posted' field not found in table {table_id}")
            return False
        resp.raise_for_status()
        print(f"  Marked record {record_id} as posted")
        return True
    except requests.RequestException as e:
        print(f"  Warning: Could not mark as posted: {e}")
        return False


def mark_record_disregarded(base_id, table_id, record_id, disregard=True):
    """Set the 'Disregard' checkbox on an Airtable record."""
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    _rate_limiter.wait()
    try:
        resp = _session.patch(url, json={"fields": {"Disregard": disregard}})
        if resp.status_code == 422:
            print(f"  Warning: 'Disregard' field not found in table {table_id}")
            return False
        resp.raise_for_status()
        action = "disregarded" if disregard else "un-disregarded"
        print(f"  Marked record {record_id} as {action}")
        return True
    except requests.RequestException as e:
        print(f"  Warning: Could not update Disregard: {e}")
        return False


def remove_specific_attachment(base_id, table_id, record_id, field_name, target_filename):
    """
    Fetch the record, remove the specific attachment by filename from the array,
    and update the record in Airtable.
    """
    url = f"https://api.airtable.com/v0/{base_id}/{table_id}/{record_id}"
    _rate_limiter.wait()
    
    try:
        # Step 1: Fetch current record
        resp = _session.get(url)
        resp.raise_for_status()
        current_fields = resp.json().get("fields", {})
        
        attachments = current_fields.get(field_name, [])
        if not attachments:
            return True # Already empty
            
        # Step 2: Keep attachments that DO NOT match the target filename
        new_attachments = []
        removed_any = False
        for att in attachments:
            if att.get("filename") == target_filename and not removed_any:
                removed_any = True # Only remove the first instance of this filename to be safe
                continue
            # When patching, we only need to provide the "id" of existing attachments
            if "id" in att:
                new_attachments.append({"id": att["id"]})
            else:
                new_attachments.append(att)
                
        # Step 3: Patch update
        if removed_any:
            patch_resp = _session.patch(url, json={"fields": {field_name: new_attachments}})
            patch_resp.raise_for_status()
            print(f"  Removed attachment '{target_filename}' from record {record_id}")
            
        return True
    except requests.RequestException as e:
        print(f"  Warning: Could not remove attachment: {e}")
        return False


# ─── Legacy functions (used by automate.py CLI) ───────────────

def fetch_all_records():
    """Fetch all records from Airtable, handling pagination."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
    all_records = []
    offset = None

    while True:
        params = {}
        if offset:
            params["offset"] = offset

        resp = requests.get(url, headers=HEADERS, params=params)
        if resp.status_code != 200:
            raise Exception(f"Airtable API error {resp.status_code}: {resp.text}")

        data = resp.json()
        all_records.extend(data.get("records") or [])
        offset = data.get("offset")
        if not offset:
            break

    return all_records


def extract_images(records):
    """Extract image URLs and record info from records that have the Blended Image field."""
    images = []
    for rec in records:
        fields = rec.get("fields", {})
        attachments = fields.get(AIRTABLE_FIELD_NAME, [])
        if not attachments:
            continue
        for att in attachments:
            url = att.get("url")
            filename = att.get("filename", "unknown")
            if url:
                images.append({
                    "url": url,
                    "filename": filename,
                    "record_id": rec["id"],
                    "fields": fields,
                })
    return images
