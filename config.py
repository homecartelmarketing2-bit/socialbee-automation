import os
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_API_TOKEN = os.getenv("AIRTABLE_API_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")
AIRTABLE_FIELD_NAME = os.getenv("AIRTABLE_FIELD_NAME", "Blended Image")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free")

BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

# ─── AIRTABLE SOURCES ──────────────────────────────────────
APP_SOURCES = {
    "app8U3Sps9uuB6JnJ": "Styled Feeds (one item)",
    "appgvioE6b0ZvtpT8": "Styled Stories (multiple items)",
    "appxUdat0vbQNLjCc": "Product Closeup",
    "app3WTO9O2Rkm8QjV": "Styled Feeds (multiple items)",
    "appSAnIy8QWSP2aZ9": "Feeds Artwork Creation",
}

# Sources that require a field sub-dropdown before loading
APP_FIELD_OPTIONS = {
    "appSAnIy8QWSP2aZ9": [
        "── Attachment ──",
        "Blended Image",
        "Styled Photo",
        "Moodboard Image",
        "── Attachment pero Reels ──",
        "Before Reels",
        "After Reels",
    ],
}

# Each app ID has its own set of table IDs
APP_TABLE_IDS = {
    "app8U3Sps9uuB6JnJ": [
        "tblVkpzLNPpPEKi7Y",  # Cluster Chandelier
        "tbllqUaPKORhKkIQu",  # Chandelier
        "tbl4D7Q82mx4fuqcb",  # Table Lamps
        "tblJrepwA3VeiUrjN",  # Pendant Lights
        "tbllg7aEN1CCWiIx0",  # Wall Lights
        "tbls7Crc2ZepVmJ3k",  # Floor Lamps
        "tbll4Qqo9OwuA3UFB",  # Rechargeable Table Lamps
        "tbljPezI9DnU9TbTP",  # Semi Flush Mounted Lights
        "tblTU1HWItSpnDZu7",  # Ceiling Lights
        "tbl9Vc6Sfa4DxVuxy",  # Painting and Bathroom Lights
    ],
    "appgvioE6b0ZvtpT8": [
        "tbl0H4CE8jdcawJfT",  # Floor Lamp + Ceiling Mounted
        "tblUdcQhWKBbj2QG2",  # Floor Lamp + Chandelier
        "tblYrmZTWRBzQnBFd",  # Flush Ceiling Lights + Wall Lights
        "tblozD79qS5YuJXXv",  # Semi Ceiling Lights and Wall Lights
        "tblYTf4qZJ6UHGAPN",  # Flush Ceiling Lights and Table Lamps
        "tblFbDpIVCKCX3Mpf",  # Semi Ceiling Lights and Table Lamps
        "tblnvjkVkL0BpWfTR",  # Flush Ceiling Lights and Floor Lamps
        "tblbhmfLEjC62rOH6",  # Semi Ceiling Lights and Floor Lamps
        "tblTL9xe4fLuAa96W",  # Chandelier and Wall Lights
        "tblWcWGHhaJBmxCSl",  # Cluster Chandelier and Wall Lights
        "tblvkeFCfcKYH9hPg",  # Chandelier and Table Lamps
        "tblvLVkVGaoKuVxCA",  # Cluster Chandelier and Table Lamps
        "tblpdaohkCjyypjZO",  # Chandelier and Floor Lamps
        "tblVeh75sIJfIje07",  # Cluster Chandelier and Floor Lamps
        "tblBi9yHI2fEq7KTD",  # Pendant Lights and Wall Lights
        "tblev1cIxtxBAlQ4o",  # Pendant Lights and Table Lamps
        "tbl086DTyCgaKVe0j",  # Pendant Lights and Floor Lamps
        "tblbNOklr1NPwsoMO",  # Bathroom Lights + Chandelier
        "tbloulRxtH5w4eG0p",  # Bathroom Lights + Pendant Light
    ],
    "appxUdat0vbQNLjCc": [
        "tbl0H4CE8jdcawJfT",  # Floor Lamp + Ceiling Mounted
        "tblUdcQhWKBbj2QG2",  # Floor Lamp + Chandelier
        "tblYrmZTWRBzQnBFd",  # Flush Ceiling Lights + Wall Lights
        "tblYTf4qZJ6UHGAPN",  # Flush Ceiling Lights and Table Lamps
        "tblnvjkVkL0BpWfTR",  # Flush Ceiling Lights and Floor Lamps
        "tblTL9xe4fLuAa96W",  # Chandelier and Wall Lights
        "tblWcWGHhaJBmxCSl",  # Cluster Chandelier and Wall Lights
        "tblvkeFCfcKYH9hPg",  # Chandelier and Table Lamps
        "tblvLVkVGaoKuVxCA",  # Cluster Chandelier and Table Lamps
        "tblpdaohkCjyypjZO",  # Chandelier and Floor Lamps
        "tblVeh75sIJfIje07",  # Cluster Chandelier and Floor Lamps
        "tblBi9yHI2fEq7KTD",  # Pendant Lights and Wall Lights
        "tblev1cIxtxBAlQ4o",  # Pendant Lights and Table Lamps
        "tbl086DTyCgaKVe0j",  # Pendant Lights and Floor Lamps
        "tblbNOklr1NPwsoMO",  # Bathroom Lights + Chandelier
        "tbloulRxtH5w4eG0p",  # Bathroom Lights + Pendant Light
    ],
    "app3WTO9O2Rkm8QjV": [
        "tbl0H4CE8jdcawJfT",  # Floor Lamp + Ceiling Mounted
        "tblUdcQhWKBbj2QG2",  # Floor Lamp + Chandelier
        "tblYrmZTWRBzQnBFd",  # Flush Ceiling Lights + Wall Lights
        "tblYTf4qZJ6UHGAPN",  # Flush Ceiling Lights and Table Lamps
        "tblnvjkVkL0BpWfTR",  # Flush Ceiling Lights and Floor Lamps
        "tblTL9xe4fLuAa96W",  # Chandelier and Wall Lights
        "tblWcWGHhaJBmxCSl",  # Cluster Chandelier and Wall Lights
        "tblvkeFCfcKYH9hPg",  # Chandelier and Table Lamps
        "tblvLVkVGaoKuVxCA",  # Cluster Chandelier and Table Lamps
        "tblpdaohkCjyypjZO",  # Chandelier and Floor Lamps
        "tblVeh75sIJfIje07",  # Cluster Chandelier and Floor Lamps
        "tblBi9yHI2fEq7KTD",  # Pendant Lights and Wall Lights
        "tblev1cIxtxBAlQ4o",  # Pendant Lights and Table Lamps
        "tbl086DTyCgaKVe0j",  # Pendant Lights and Floor Lamps
        "tblbNOklr1NPwsoMO",  # Bathroom Lights + Chandelier
        "tbloulRxtH5w4eG0p",  # Bathroom Lights + Pendant Light
    ],
    "appSAnIy8QWSP2aZ9": [
        "tbl0H4CE8jdcawJfT",  # Floor Lamp + Ceiling Mounted
        "tblUdcQhWKBbj2QG2",  # Floor Lamp and Chandelier
        "tblYrmZTWRBzQnBFd",  # Flush Ceiling Lights and Wall Lights
        "tblozD79qS5YuJXXv",  # Semi Ceiling Lights and Wall Lights
        "tblYTf4qZJ6UHGAPN",  # Flush Ceiling Lights and Table Lamps
        "tblFbDpIVCKCX3Mpf",  # Semi Ceiling Lights and Table Lamps
        "tblnvjkVkL0BpWfTR",  # Flush Ceiling Lights and Floor Lamps
        "tblbhmfLEjC62rOH6",  # Semi Ceiling Lights and Floor Lamps
        "tblTL9xe4fLuAa96W",  # Chandelier and Wall Lights
        "tblWcWGHhaJBmxCSl",  # Cluster Chandelier and Wall Lights
        "tblvkeFCfcKYH9hPg",  # Chandelier and Table Lamps
        "tblvLVkVGaoKuVxCA",  # Cluster Chandelier and Table Lamps
        "tblpdaohkCjyypjZO",  # Chandelier and Floor Lamps
        "tble6pPlSXkrbUbuT",  # Lighted Ceiling Fans + Floor Lamps
        "tblVeh75sIJfIje07",  # Cluster Chandelier and Floor Lamps
        "tblBi9yHI2fEq7KTD",  # Pendant Lights and Wall Lights
        "tblev1cIxtxBAlQ4o",  # Pendant Lights and Table Lamps
        "tbl086DTyCgaKVe0j",  # Pendant Lights and Floor Lamps
        "tblbNOklr1NPwsoMO",  # Bathroom Lights + Chandelier
        "tbloulRxtH5w4eG0p",  # Bathroom Lights + Pendant Light
    ],
}

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
}

# ─── FIXED FOOTER ───────────────────────────────────────────
HOMECARTEL_FOOTER = """You can also visit our products at the following Furniture Republic Stores :
Alabang Festival Mall
Glorietta 3
Shangri-la Plaza
SM Megamall
SM North EDSA
Trinoma
UP Town Center
SM Mall of Asia
SM Aura
SM Fairview
Robinsons Magnolia
Robinsons Manila
Robinsons Galleria
Festival Mall Filinvest City
SM Lanang Premier, Davao
SM Seaside City, Cebu

We are now also available at Commune Home, Makati

📞0977-8255588 (or send us DM)
📧homecartelsales@gmail.com

Our FREE delivery & installation applies to lighting fixtures only.

#homecartelfix #shopbydesign #lightingph #lightingdesign #interiordesignph #homedecorphilippines #homeinteriors #modernlighting #contemporarylighting #luxurylighting #chandelierph #pendantlights #ceilinglights #walllights #floorlamps #tablelamps #designerlighting #homecartellighting"""

# Fallback models — if one is rate-limited, try the next
FALLBACK_MODELS = [
    OPENROUTER_MODEL,
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "google/gemma-3-4b-it:free",
    "google/gemma-3n-e4b-it:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]
