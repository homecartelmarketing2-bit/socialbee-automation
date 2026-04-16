# SocialBee AutoPoster

A desktop app that automates social media posting through [SocialBee](https://socialbee.com/). It fetches images and videos from Airtable, generates AI captions via OpenRouter, and posts them to SocialBee using browser automation.

## Features

- Fetch images/videos from Airtable (single, paired, triple/carousel)
- AI-generated captions with customizable footer
- Post to SocialBee via browser automation (Chrome/Brave)
- Instagram Story support with watermarks and auto-resize
- Video support with Zoho WorkDrive integration
- Drag-and-drop batch operations
- Grid view and single image view

## Prerequisites

- **Python 3.10+**
- **Google Chrome** or **Brave Browser**
- **Airtable** account with API token
- **SocialBee** account (logged in via Chrome/Brave)
- **OpenRouter** API key (free tier works)
- **Zoho WorkDrive** account (optional, for video uploads)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/homecartelmarketing2-bit/socialbee-automation.git
cd socialbee-automation
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `AIRTABLE_API_TOKEN` | Yes | Your Airtable personal access token |
| `AIRTABLE_BASE_ID` | Yes | Airtable base ID (starts with `app...`) |
| `AIRTABLE_TABLE_ID` | Yes | Default table ID (starts with `tbl...`) |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for AI captions |
| `BRAVE_PATH` | No | Path to Brave browser executable |
| `CHROME_PATH` | No | Path to Chrome executable |
| `ZOHO_CLIENT_ID` | No | Zoho API client ID (for video uploads) |
| `ZOHO_CLIENT_SECRET` | No | Zoho API client secret |
| `ZOHO_REFRESH_TOKEN` | No | Zoho API refresh token |

### 4. Configure app settings

```bash
cp config.json.example config.json
```

Edit `config.json` to match your Airtable structure:

- **`app_sources`** — Map of Airtable base IDs to display names
- **`app_table_ids`** — List of table IDs per base to fetch records from
- **`app_field_options`** — Dropdown options for field selection in the UI
- **`paired_field_options`** — Field pairs for before/after posts
- **`triple_field_options`** — Field triples for carousel posts
- **`zoho_field_folder_map`** — Maps Airtable fields to Zoho folder IDs
- **`zoho_fetch_options`** — Zoho folders to fetch videos from
- **`footer`** — Text appended to every caption
- **`fallback_models`** — OpenRouter models to try (in order) for caption generation

### 5. Set up browser profile

On first run, you'll need to log in to SocialBee in the browser window that opens. The session is saved locally so you only need to do this once.

### 6. Run the app

```bash
python app.py
```

The app opens a local web UI in Chrome/Edge/default browser.

## Building an Executable (Windows)

To create a standalone `.exe`:

```bash
pip install pyinstaller
pyinstaller "SocialBee AutoPoster.spec"
```

The executable will be in the `dist/` folder. Place `config.json` and `.env` next to the `.exe` for it to work.

## Project Structure

```
├── app.py                  # Main entry point (Eel web server)
├── automate.py             # Batch automation logic
├── config.json.example     # App configuration template
├── .env.example            # Environment variables template
├── requirements.txt        # Python dependencies
├── src/
│   ├── config.py           # Configuration loader
│   ├── airtable_client.py  # Airtable API integration
│   ├── caption.py          # AI caption generation
│   ├── socialbee_poster.py # Browser automation for posting
│   ├── app_window.py       # UI helper functions
│   └── zoho_client.py      # Zoho WorkDrive integration
└── web/
    ├── index.html          # Web UI
    ├── css/style.css       # Styles
    └── js/app.js           # Frontend logic
```

## License

MIT
