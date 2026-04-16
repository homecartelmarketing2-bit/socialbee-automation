import os
import requests
import json
import time
from src.config import ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN

# Cache token to avoid refreshing on every upload
_access_token = None
_token_expiry = 0

def get_valid_token():
    global _access_token, _token_expiry
    
    # Return cached token if valid (with 60 seconds buffer)
    if _access_token and time.time() < (_token_expiry - 60):
        return _access_token

    if not all([ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN]):
        raise ValueError("Zoho credentials missing. Please check .env file.")

    url = "https://accounts.zoho.com/oauth/v2/token"
    params = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token"
    }

    resp = requests.post(url, data=params)
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        raise Exception(f"Failed to refresh Zoho token: {data}")

    _access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)  # usually 3600 seconds
    _token_expiry = time.time() + expires_in

    return _access_token

def upload_file_to_workdrive(folder_id, filename, file_data):
    """
    Uploads file content to the specified Zoho Workdrive folder.
    """
    token = get_valid_token()
    url = "https://workdrive.zoho.com/api/v1/upload"
    
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}"
    }

    files = {
        "content": (filename, file_data),
    }
    
    data = {
        "filename": filename,
        "parent_id": folder_id,
        "override-name-exist": "true"
    }

    try:
        resp = requests.post(url, headers=headers, data=data, files=files)
        resp.raise_for_status()
        resp_data = resp.json()
        print(f"  Successfully uploaded '{filename}' to Zoho folder '{folder_id}'")
        return resp_data
    except Exception as e:
        print(f"  Zoho upload error: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"  Response: {e.response.text}")
        raise e
