"""
Test: TikTok profile selection + variation flow
Screenshots every step so we can see exactly what's happening.
CLOSE BRAVE BEFORE RUNNING!
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def ss(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.screenshot(path=path)
    print(f"  [SCREENSHOT] {name}.png")

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

    print("[2] Navigating to SocialBee poster...")
    page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    ss(page, "01_page_loaded")

    print("[3] Clicking 'Create post'...")
    page.locator("button:has-text('Create post')").first.click()
    page.wait_for_timeout(3000)
    ss(page, "02_after_create_post")

    print("[4] Clicking 'Select None'...")
    try:
        page.locator("button:has-text('Select None')").first.click()
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  Select None failed: {e}")
    ss(page, "03_after_select_none")

    print("[5] Handling TikTok deselect popup (Proceed)...")
    try:
        tiktok_text = page.locator("text=TikTok").first
        if tiktok_text.is_visible(timeout=3000):
            print("  TikTok popup visible!")
            ss(page, "04_tiktok_deselect_popup")
            page.locator("button:has-text('Proceed')").first.click()
            page.wait_for_timeout(2000)
            print("  Clicked Proceed — TikTok deselected")
        else:
            print("  No TikTok popup")
    except Exception as e:
        print(f"  Error: {e}")
    ss(page, "05_after_tiktok_deselect")

    print("[6] Selecting Facebook...")
    try:
        fb = page.locator("img.account-image[src*='graph.facebook.com']").first
        fb.wait_for(state="visible", timeout=5000)
        fb.click()
        page.wait_for_timeout(1000)
        print("  Facebook selected")
    except Exception as e:
        print(f"  FB error: {e}")
    ss(page, "06_after_fb_select")

    print("[7] Selecting Instagram...")
    try:
        ig = page.locator("img.account-image[src*='39373932_264858911021104']").first
        ig.wait_for(state="visible", timeout=5000)
        ig.click()
        page.wait_for_timeout(1000)
        print("  Instagram selected")
    except Exception as e:
        print(f"  IG error: {e}")
    ss(page, "07_after_ig_select")

    # Check editor BEFORE TikTok — is it visible at this point?
    print("\n[8] Checking .ql-editor BEFORE TikTok selection...")
    try:
        editor_check = page.locator(".ql-editor").first
        is_vis = editor_check.is_visible(timeout=3000)
        print(f"  .ql-editor visible = {is_vis}")
    except Exception as e:
        print(f"  .ql-editor check error: {e}")

    print("\n[9] Selecting TikTok profile...")
    try:
        tiktok = page.locator("img.account-image[src*='tiktokcdn']").first
        tiktok.wait_for(state="visible", timeout=5000)
        tiktok.click()
        page.wait_for_timeout(2000)
        print("  TikTok clicked")
    except Exception as e:
        print(f"  TikTok click error: {e}")
    ss(page, "08_after_tiktok_click")

    print("[10] Handling TikTok ADD confirmation popup (Proceed)...")
    try:
        proceed_btn = page.locator("button.btn.btn-primary-sb:has-text('Proceed')").first
        if proceed_btn.is_visible(timeout=5000):
            ss(page, "09_tiktok_add_popup")
            proceed_btn.click()
            page.wait_for_timeout(3000)
            print("  Clicked Proceed — TikTok added")
        else:
            print("  No Proceed button visible")
    except Exception as e:
        print(f"  Proceed error: {e}")
    ss(page, "10_after_tiktok_proceed")

    # NOW check editor — this is where the error happens
    print("\n[11] Checking .ql-editor AFTER TikTok added...")
    try:
        editor = page.locator(".ql-editor").first
        is_vis = editor.is_visible(timeout=3000)
        print(f"  .ql-editor visible = {is_vis}")
    except Exception as e:
        print(f"  .ql-editor NOT visible: {e}")

    # Let's also check ALL .ql-editor instances
    ql_editors = page.locator(".ql-editor").all()
    print(f"  Total .ql-editor elements: {len(ql_editors)}")
    for i, ed in enumerate(ql_editors):
        try:
            vis = ed.is_visible()
            bbox = ed.bounding_box() if vis else None
            print(f"    [{i}] visible={vis} bbox={bbox}")
        except Exception as e:
            print(f"    [{i}] error: {e}")

    # Check if there's ANY text editor or contenteditable element
    print("\n[12] Checking for other editor elements...")
    for selector in [".ql-editor", "[contenteditable='true']", "textarea", ".ql-container", ".editor"]:
        els = page.locator(selector).all()
        vis_count = sum(1 for el in els if el.is_visible())
        print(f"  '{selector}': {len(els)} total, {vis_count} visible")

    # Dump the page's visible text to understand the UI state
    print("\n[13] Page state — looking for key elements...")
    for text in ["Save post", "Add a photo", "Select None", "Select All", "TikTok", "Customize", "Variation"]:
        els = page.locator(f"text={text}").all()
        vis = [el for el in els if el.is_visible()]
        if els:
            print(f"  '{text}': {len(els)} found, {len(vis)} visible")

    # Extra wait and recheck
    print("\n[14] Waiting 5 more seconds and rechecking editor...")
    page.wait_for_timeout(5000)
    ss(page, "11_after_extra_wait")

    try:
        editor = page.locator(".ql-editor").first
        is_vis = editor.is_visible(timeout=3000)
        print(f"  .ql-editor visible after extra wait = {is_vis}")
    except Exception as e:
        print(f"  Still not visible: {e}")

    ql_editors = page.locator(".ql-editor").all()
    print(f"  Total .ql-editor elements after wait: {len(ql_editors)}")

    # Final screenshot
    ss(page, "12_final_state")

    print("\n=== DONE ===")
    print(f"Screenshots saved to: {SCREENSHOT_DIR}")
    print("Closing browser in 3 seconds...")
    page.wait_for_timeout(3000)
    browser.close()
