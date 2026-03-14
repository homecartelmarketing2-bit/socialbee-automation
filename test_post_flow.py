"""
Test the SocialBee posting flow step by step.
Takes screenshots at each step so we can see what's happening.
CLOSE BRAVE BEFORE RUNNING!
"""
import os
import sys
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
    page.screenshot(path="step1_loaded.png")
    print("  Screenshot: step1_loaded.png")

    print("[3] Clicking 'Create post'...")
    create_btn = page.locator("button:has-text('Create post')").first
    try:
        create_btn.wait_for(state="visible", timeout=10000)
        create_btn.click()
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  ERROR clicking Create post: {e}")
        page.screenshot(path="step2_error.png")
        browser.close()
        sys.exit(1)

    page.screenshot(path="step2_after_create.png")
    print("  Screenshot: step2_after_create.png")

    # Check what's on screen
    print("\n[4] Checking for 'Select None' button...")
    select_none_btns = page.locator("button:has-text('Select None')").all()
    print(f"  Found {len(select_none_btns)} 'Select None' buttons")
    for i, btn in enumerate(select_none_btns):
        try:
            visible = btn.is_visible()
            text = btn.text_content()
            print(f"  [{i}] visible={visible} text='{text}'")
        except:
            pass

    # Try clicking Select None
    print("\n[5] Clicking 'Select None'...")
    try:
        select_none = page.locator("button:has-text('Select None')").first
        if select_none.is_visible(timeout=5000):
            select_none.click()
            page.wait_for_timeout(1500)
            print("  Clicked 'Select None'")
        else:
            print("  'Select None' not visible")
    except Exception as e:
        print(f"  ERROR: {e}")

    page.screenshot(path="step3_after_select_none.png")
    print("  Screenshot: step3_after_select_none.png")

    # Check for TikTok popup
    print("\n[6] Checking for TikTok popup...")
    try:
        tiktok = page.locator("text=TikTok").first
        if tiktok.is_visible(timeout=3000):
            print("  TikTok popup IS visible")
            page.screenshot(path="step4_tiktok_popup.png")
            print("  Screenshot: step4_tiktok_popup.png")

            # Click cancel
            cancel = page.locator("button:has-text('Cancel')").first
            if cancel.is_visible(timeout=2000):
                cancel.click()
                page.wait_for_timeout(1000)
                print("  Clicked Cancel on TikTok popup")
        else:
            print("  No TikTok popup (good!)")
    except Exception as e:
        print(f"  TikTok check: {e}")

    page.screenshot(path="step5_after_tiktok.png")
    print("  Screenshot: step5_after_tiktok.png")

    # Check for Facebook profile
    print("\n[7] Looking for Facebook profile...")
    all_account_imgs = page.locator("img.account-image").all()
    print(f"  Found {len(all_account_imgs)} account-image elements")
    for i, img in enumerate(all_account_imgs):
        try:
            src = img.get_attribute("src") or ""
            visible = img.is_visible()
            platform = "unknown"
            if "facebook" in src or "graph.facebook" in src:
                platform = "FACEBOOK"
            elif "instagram" in src or "cdninstagram" in src:
                platform = "INSTAGRAM"
            elif "tiktok" in src:
                platform = "TIKTOK"
            print(f"  [{i}] {platform} visible={visible} src={src[:80]}...")
        except Exception as e:
            print(f"  [{i}] error: {e}")

    # Try clicking Facebook
    print("\n[8] Clicking Facebook profile...")
    try:
        fb = page.locator("img.account-image[src*='graph.facebook.com']").first
        if fb.is_visible(timeout=5000):
            fb.click()
            page.wait_for_timeout(500)
            print("  Clicked Facebook profile!")
        else:
            print("  Facebook profile NOT visible")
    except Exception as e:
        print(f"  ERROR: {e}")

    page.screenshot(path="step6_after_fb_select.png")
    print("  Screenshot: step6_after_fb_select.png")

    # Check for editor
    print("\n[9] Checking for caption editor...")
    try:
        editor = page.locator(".ql-editor").first
        if editor.is_visible(timeout=5000):
            print("  Editor IS visible")
            editor.click()
            editor.fill("Test caption from automation")
            page.wait_for_timeout(500)
            print("  Typed test caption")
        else:
            print("  Editor NOT visible")
    except Exception as e:
        print(f"  ERROR: {e}")

    page.screenshot(path="step7_after_caption.png")
    print("  Screenshot: step7_after_caption.png")

    # Check for file input
    print("\n[10] Checking for file upload input...")
    file_inputs = page.locator("input[type='file']").all()
    print(f"  Found {len(file_inputs)} file inputs")
    for i, fi in enumerate(file_inputs):
        try:
            name = fi.get_attribute("name") or "no-name"
            accept = fi.get_attribute("accept") or "no-accept"
            print(f"  [{i}] name='{name}' accept='{accept}'")
        except:
            pass

    # Check for Save post button
    print("\n[11] Checking for 'Save post' button...")
    save_btns = page.locator("button:has-text('Save post')").all()
    print(f"  Found {len(save_btns)} 'Save post' buttons")
    for i, btn in enumerate(save_btns):
        try:
            visible = btn.is_visible()
            text = btn.text_content()
            classes = btn.get_attribute("class") or ""
            print(f"  [{i}] visible={visible} text='{text.strip()}' class='{classes}'")
        except:
            pass

    print("\n=== DONE ===")
    print("Check the screenshots in socialbee-automation folder.")
    print("Press Enter to close browser...")
    input()
    browser.close()
