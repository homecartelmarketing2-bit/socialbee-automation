"""
Test: Check file upload after full profile selection flow
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

# Create a small test image
from PIL import Image
test_img = Image.new('RGB', (200, 200), color='red')
tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix='test_')
test_img.save(tmp.name)
tmp.close()
print(f"Test image: {tmp.name}")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=BRAVE_USER_DATA,
        executable_path=BRAVE_PATH,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
    )
    page = browser.pages[0] if browser.pages else browser.new_page()

    print("[1] Navigating to SocialBee...")
    page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    print("[2] Click Create post...")
    page.locator("button:has-text('Create post')").first.click()
    page.wait_for_timeout(3000)

    print("[3] Click Select None...")
    page.locator("button:has-text('Select None')").first.click()
    page.wait_for_timeout(2000)

    print("[4] Handle TikTok popup...")
    try:
        tiktok = page.locator("text=TikTok").first
        if tiktok.is_visible(timeout=3000):
            page.locator("button:has-text('Proceed')").first.click()
            page.wait_for_timeout(2000)
            print("  Clicked Proceed")
    except:
        pass

    print("[5] Select Facebook...")
    page.locator("img.account-image[src*='graph.facebook.com']").first.click()
    page.wait_for_timeout(1500)

    print("[6] Type caption...")
    editor = page.locator(".ql-editor").first
    editor.wait_for(state="visible", timeout=10000)
    editor.click()
    editor.fill("Test upload caption")
    page.wait_for_timeout(500)

    # Now check all file inputs AFTER profile selection
    print("\n[7] Checking file inputs AFTER profile selection...")
    file_inputs = page.locator("input[type='file']").all()
    print(f"  Found {len(file_inputs)} file inputs total")
    for i, fi in enumerate(file_inputs):
        name = fi.get_attribute("name") or "?"
        accept = fi.get_attribute("accept") or "?"
        visible = fi.is_visible()
        enabled = fi.is_enabled()
        print(f"  [{i}] name='{name}' accept='{accept[:50]}' visible={visible} enabled={enabled}")

    # Also check for "Add a photo or video" button/area
    print("\n[8] Looking for photo upload area...")
    photo_btns = page.locator("text='Add a photo or video'").all()
    print(f"  Found {len(photo_btns)} 'Add a photo or video' elements")
    for i, btn in enumerate(photo_btns):
        try:
            visible = btn.is_visible()
            html = btn.evaluate("el => el.outerHTML")
            print(f"  [{i}] visible={visible} html={html[:200]}")
        except:
            pass

    # Try uploading with different approaches
    print("\n[9] Attempting upload with input[type='file'][name='file']...")
    try:
        file_input = page.locator("input[type='file'][name='file']").first
        file_input.set_input_files(tmp.name)
        page.wait_for_timeout(5000)
        page.screenshot(path="test_upload_result1.png")
        print("  Done! Screenshot: test_upload_result1.png")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Check if image appeared
    print("\n[10] Checking if image preview appeared...")
    # Look for any image preview indicators
    previews = page.locator("img[class*='preview'], img[class*='thumb'], .image-preview, [class*='upload']").all()
    print(f"  Found {len(previews)} preview-like elements")

    page.screenshot(path="test_upload_final.png")
    print("  Final screenshot: test_upload_final.png")

    page.wait_for_timeout(2000)
    browser.close()

os.unlink(tmp.name)
