import requests
from src.config import AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID, AIRTABLE_FIELD_NAME, HEADERS, APP_TABLE_IDS


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
        all_records.extend(data.get("records", []))
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


def fetch_all_records_for_base(base_id, progress_callback=None, field_name=None):
    """Fetch all records from ALL tables in a base."""
    use_field = field_name or AIRTABLE_FIELD_NAME
    table_ids = APP_TABLE_IDS.get(base_id, [])
    total_tables = len(table_ids)
    all_images = []
    for i, table_id in enumerate(table_ids):
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        offset = None
        while True:
            params = {}
            if offset:
                params["offset"] = offset
            resp = requests.get(url, headers=HEADERS, params=params)
            if resp.status_code != 200:
                print(f"  Warning: table {table_id} error {resp.status_code}, skipping")
                break
            data = resp.json()
            records = data.get("records", [])
            for rec in records:
                fields = rec.get("fields", {})
                attachments = fields.get(use_field, [])
                if not attachments:
                    continue
                for att in attachments:
                    img_url = att.get("url")
                    filename = att.get("filename", "unknown")
                    if img_url:
                        all_images.append({
                            "url": img_url,
                            "filename": filename,
                            "record_id": rec["id"],
                            "fields": fields,
                        })
            offset = data.get("offset")
            if not offset:
                break
        if progress_callback:
            progress_callback(i + 1, total_tables, len(all_images))
    return all_images
