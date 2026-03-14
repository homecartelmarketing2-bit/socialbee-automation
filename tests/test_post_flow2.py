"""
Test 2: Fix TikTok deselection — click Proceed instead of Cancel
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

with sync_playwright() as p:
    print("[1] Launching Brave...")
    browser = p.chromium.launch_persistent_context(
        user_data_dir=BRAVE_USER_DATA,
        executable_path=BRAVE_PATH,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
    )
    page = browser.pages[0] if browser.pages else browser.new_page()

    print("[2] Navigating to SocialBee...")
    page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    print("[3] Clicking 'Create post'...")
    create_btn = page.locator("button:has-text('Create post')").first
    create_btn.wait_for(state="visible", timeout=10000)
    create_btn.click()
    page.wait_for_timeout(3000)
    page.screenshot(path="test2_step1_after_create.png")

    print("[4] Clicking 'Select None'...")
    select_none = page.locator("button:has-text('Select None')").first
    select_none.wait_for(state="visible", timeout=5000)
    select_none.click()
    page.wait_for_timeout(2000)
    page.screenshot(path="test2_step2_after_select_none.png")

    # Check if TikTok popup appeared
    print("[5] Checking for TikTok popup...")
    try:
        tiktok_text = page.locator("text=TikTok").first
        if tiktok_text.is_visible(timeout=3000):
            print("  TikTok popup detected!")

            # Try clicking PROCEED instead of Cancel
            proceed_btn = page.locator("button:has-text('Proceed')").first
            if proceed_btn.is_visible(timeout=3000):
                print("  Clicking 'Proceed' to confirm TikTok deselection...")
                proceed_btn.click()
                page.wait_for_timeout(2000)
                print("  Clicked Proceed!")
            else:
                print("  No 'Proceed' button found, trying Cancel...")
                cancel_btn = page.locator("button:has-text('Cancel')").first
                cancel_btn.click()
                page.wait_for_timeout(2000)
        else:
            print("  No TikTok popup")
    except Exception as e:
        print(f"  Error: {e}")

    page.screenshot(path="test2_step3_after_tiktok.png")

    # Check which profiles are now selected
    print("\n[6] Checking profile states...")
    all_imgs = page.locator("img.account-image").all()
    for i, img in enumerate(all_imgs):
        try:
            src = img.get_attribute("src") or ""
            # Check if profile is selected by looking at parent opacity/style
            parent = img.locator("xpath=..").first
            parent_html = parent.evaluate("el => el.outerHTML")

            platform = "?"
            if "facebook" in src: platform = "FB"
            elif "cdninstagram" in src: platform = "IG"
            elif "tiktok" in src: platform = "TK"

            # Check for selected state (opacity, class, etc)
            is_gray = "opacity" in parent_html or "gray" in parent_html or "disabled" in parent_html
            classes = parent.get_attribute("class") or ""
            print(f"  [{i}] {platform} classes='{classes}' gray={is_gray}")
            print(f"       html={parent_html[:200]}")
        except Exception as e:
            print(f"  [{i}] error: {e}")

    # Now select only Facebook
    print("\n[7] Selecting Facebook...")
    fb = page.locator("img.account-image[src*='graph.facebook.com']").first
    try:
        fb.wait_for(state="visible", timeout=5000)
        fb.click()
        page.wait_for_timeout(1000)
        print("  Clicked Facebook")
    except Exception as e:
        print(f"  Error: {e}")

    page.screenshot(path="test2_step4_fb_selected.png")

    # Check profiles again after selecting FB
    print("\n[8] Profile states after FB select...")
    all_imgs = page.locator("img.account-image").all()
    for i, img in enumerate(all_imgs):
        try:
            src = img.get_attribute("src") or ""
            parent = img.locator("xpath=..").first
            parent_html = parent.evaluate("el => el.outerHTML")
            platform = "?"
            if "facebook" in src: platform = "FB"
            elif "cdninstagram" in src: platform = "IG"
            elif "tiktok" in src: platform = "TK"
            print(f"  [{i}] {platform} => {parent_html[:200]}")
        except:
            pass

    page.screenshot(path="test2_step5_final.png")
    print("\nDone! Check screenshots.")

    # Don't wait for input, just close
    page.wait_for_timeout(3000)
    browser.close()
