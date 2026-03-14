"""
SocialBee Auto-Poster (CLI)
- Fetches images from Airtable (Blended Image field)
- Generates AI captions via OpenRouter
- Posts to SocialBee via browser automation (Brave)

Close Brave browser before running this script!
"""
import os
import requests

from config import (
    AIRTABLE_FIELD_NAME, OPENROUTER_API_KEY, OPENROUTER_MODEL,
    BRAVE_PATH, BRAVE_USER_DATA,
)
from airtable_client import fetch_all_records, extract_images
from socialbee_poster import download_image


# ─── AI CAPTION (simpler prompt for CLI batch mode) ────────

def generate_caption(image_info):
    """Generate a social media caption using OpenRouter AI."""
    filename = image_info.get("filename", "image")
    fields = image_info.get("fields", {})

    context_parts = []
    for key, val in fields.items():
        if key == AIRTABLE_FIELD_NAME:
            continue
        if isinstance(val, str) and val.strip():
            context_parts.append(f"{key}: {val}")

    context = "\n".join(context_parts) if context_parts else f"Image: {filename}"

    prompt = f"""Write a short, engaging Facebook post caption for this image.
Context about the image:
{context}

Rules:
- Keep it 1-3 sentences max
- Make it engaging and natural
- Add 2-3 relevant hashtags at the end
- Do NOT use markdown or formatting
- Just return the caption text, nothing else"""

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"].get("content", "")
    return content.strip().strip('"') if content else "Check out this amazing post!"


# ─── SOCIALBEE BROWSER HELPERS ─────────────────────────────

def dismiss_tiktok_popup(page):
    """Close TikTok profile popup if it appears."""
    try:
        cancel_btn = page.locator("button:has-text('Cancel')").first
        if cancel_btn.is_visible(timeout=3000):
            popup_text = page.locator("text=TikTok")
            if popup_text.is_visible(timeout=1000):
                cancel_btn.click()
                page.wait_for_timeout(1000)
                print("  Dismissed TikTok popup")
    except Exception:
        pass


def set_category(page, category_name):
    """Select a category from the dropdown."""
    try:
        cat_selector = page.locator(".category-selector")
        if cat_selector.is_visible(timeout=3000):
            cat_selector.click()
            page.wait_for_timeout(1000)

            cat_option = page.locator(f"text={category_name}").first
            if cat_option.is_visible(timeout=3000):
                cat_option.click()
                page.wait_for_timeout(500)
                print(f"  Selected category: {category_name}")
                return True
    except Exception as e:
        print(f"  Category selection error: {e}")
    return False


def create_socialbee_post(page, caption, image_path, category=None):
    """Create a single post in SocialBee."""
    print("  Clicking 'Create post'...")
    create_btn = page.locator("button.btn.btn-primary-sb.rounded-pill:has-text('Create post')")
    create_btn.click()
    page.wait_for_timeout(3000)

    dismiss_tiktok_popup(page)

    print("  Typing caption...")
    editor = page.locator(".ql-editor").first
    editor.click()
    editor.fill("")
    page.wait_for_timeout(500)
    editor.type(caption, delay=20)
    page.wait_for_timeout(500)

    print("  Uploading image...")
    file_input = page.locator("input[type='file'][name='file']").first
    file_input.set_input_files(image_path)
    page.wait_for_timeout(5000)

    if category:
        set_category(page, category)

    print("  Saving post...")
    save_btn = page.locator("button.submit-button:has-text('Save post')")
    save_btn.click()
    page.wait_for_timeout(3000)

    dismiss_tiktok_popup(page)
    print("  Post saved!")


# ─── MAIN CLI FLOW ─────────────────────────────────────────

def run_automation(category=None, max_posts=None):
    """Main automation flow."""
    print("=" * 50)
    print("STEP 1: Fetching images from Airtable...")
    print("=" * 50)
    records = fetch_all_records()
    images = extract_images(records)
    print(f"Found {len(images)} images")

    if not images:
        print("No images found. Exiting.")
        return

    if max_posts:
        images = images[:max_posts]
        print(f"Processing first {max_posts} images")

    print("\n" + "=" * 50)
    print("STEP 2: Generating AI captions...")
    print("=" * 50)
    for i, img in enumerate(images):
        print(f"  [{i+1}/{len(images)}] Generating caption for {img['filename']}...")
        img["caption"] = generate_caption(img)
        print(f"  Caption: {img['caption'][:80]}...")

    print("\n" + "=" * 50)
    print("STEP 3: Downloading images...")
    print("=" * 50)
    for i, img in enumerate(images):
        print(f"  [{i+1}/{len(images)}] Downloading {img['filename']}...")
        img["local_path"] = download_image(img["url"], img["filename"])
        print(f"  Saved to: {img['local_path']}")

    print("\n" + "=" * 50)
    print("STEP 4: Posting to SocialBee...")
    print("=" * 50)
    print("Launching Brave browser...")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=BRAVE_USER_DATA,
            executable_path=BRAVE_PATH,
            headless=False,
            channel=None,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        print("Navigating to SocialBee...")
        page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        for i, img in enumerate(images):
            print(f"\n--- Post {i+1}/{len(images)}: {img['filename']} ---")
            try:
                create_socialbee_post(
                    page,
                    caption=img["caption"],
                    image_path=img["local_path"],
                    category=category,
                )
                print(f"  [OK] Post {i+1} created successfully!")
            except Exception as e:
                print(f"  [ERROR] Post {i+1} failed: {e}")

            if i < len(images) - 1:
                page.wait_for_timeout(2000)

        browser.close()

    print("\n" + "=" * 50)
    print("CLEANUP")
    print("=" * 50)
    for img in images:
        try:
            os.unlink(img.get("local_path", ""))
        except Exception:
            pass

    print(f"\nDone! Created {len(images)} posts on SocialBee.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SocialBee Auto-Poster")
    parser.add_argument("--category", type=str, default=None, help="SocialBee category name")
    parser.add_argument("--max", type=int, default=None, help="Max number of posts to create")
    parser.add_argument("--dry-run", action="store_true", help="Preview captions without posting")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN MODE - Preview only")
        print("=" * 50)
        records = fetch_all_records()
        images = extract_images(records)
        print(f"Found {len(images)} images\n")

        if args.max:
            images = images[:args.max]

        for i, img in enumerate(images):
            caption = generate_caption(img)
            print(f"[{i+1}] {img['filename']}")
            print(f"    Caption: {caption}")
            print()
    else:
        run_automation(category=args.category, max_posts=args.max)
