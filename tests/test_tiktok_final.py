"""
Final test: Full flow with FB + IG + TikTok using the new approach.
Caption + upload FIRST, then add TikTok. Does NOT save the post.
CLOSE BRAVE BEFORE RUNNING!
"""
import os, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from PIL import Image

load_dotenv()
BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def ss(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.screenshot(path=path)
    print(f"  [SS] {name}.png")

# Create test image
test_img = Image.new('RGB', (200, 200), color='orange')
tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix='test_')
test_img.save(tmp.name)
tmp.close()

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

    print("[2] Navigate to SocialBee...")
    page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    print("[3] Click Create post...")
    page.locator("button:has-text('Create post')").first.click()
    page.wait_for_timeout(3000)

    print("[4] Click Select None...")
    page.locator("button:has-text('Select None')").first.click()
    page.wait_for_timeout(2000)

    # Handle TikTok deselect popup
    try:
        if page.locator("text=TikTok").first.is_visible(timeout=3000):
            page.locator("button:has-text('Proceed')").first.click()
            page.wait_for_timeout(2000)
            print("  TikTok deselect: Proceed")
    except:
        pass

    print("[5] Select FB + IG...")
    page.locator("img.account-image[src*='graph.facebook.com']").first.click()
    page.wait_for_timeout(500)
    page.locator("img.account-image[src*='39373932_264858911021104']").first.click()
    page.wait_for_timeout(500)

    print("[6] Fill caption FIRST...")
    editor = page.locator(".ql-editor").first
    editor.wait_for(state="visible", timeout=10000)
    editor.click()
    editor.fill("FINAL TEST - caption before TikTok")
    page.wait_for_timeout(500)
    print("  Caption OK!")

    print("[7] Upload image FIRST...")
    page.locator("input[type='file']").first.set_input_files(tmp.name)
    page.wait_for_timeout(3000)
    print("  Upload OK!")
    ss(page, "final_01_before_tiktok")

    print("[8] NOW add TikTok...")
    page.locator("img.account-image[src*='tiktokcdn']").first.click()
    page.wait_for_timeout(2000)

    print("[9] Click Proceed on TikTok add popup...")
    try:
        proceed = page.locator("button.btn.btn-primary-sb:has-text('Proceed')").first
        if proceed.is_visible(timeout=5000):
            proceed.click()
            page.wait_for_timeout(3000)
            print("  Proceed clicked!")
    except Exception as e:
        print(f"  Error: {e}")
    ss(page, "final_02_after_tiktok_proceed")

    # Expand TikTok variation row first
    print("[10] Expanding TikTok variation row...")
    try:
        activate_btns = page.locator("[ng-click*='activateVariant']").all()
        print(f"  Found {len(activate_btns)} activateVariant buttons")
        if len(activate_btns) >= 3:
            activate_btns[2].click()  # 3rd = TikTok
            page.wait_for_timeout(2000)
            print("  TikTok variation expanded!")
        ss(page, "final_03_tiktok_expanded")

        # Now check content disclosure toggle
        disclosure = page.locator("[ng-click*='updateContentDisclosure']").first
        if disclosure.is_visible(timeout=3000):
            cls = disclosure.get_attribute("class") or ""
            print(f"  Disclosure class: {cls}")
            if "inactive" in cls:
                disclosure.click()
                page.wait_for_timeout(1000)
                print("  Content disclosure enabled!")
            else:
                print("  Toggle already active")
        else:
            print("  Disclosure toggle not visible")
    except Exception as e:
        print(f"  Error: {e}")
    ss(page, "final_03_after_disclosure")

    # Check final state
    print("\n[11] Final state check...")
    # Check variation rows
    variations = page.locator("text=Variation").all()
    print(f"  Variation elements: {len(variations)}")

    # Check warnings
    warnings = page.locator(".fa-exclamation-triangle").all()
    vis_warnings = sum(1 for w in warnings if w.is_visible())
    print(f"  Warning triangles: {len(warnings)} total, {vis_warnings} visible")

    # Check Save post button
    save_btn = page.locator("button:has-text('Save post')").first
    save_visible = save_btn.is_visible()
    print(f"  Save post button visible: {save_visible}")

    ss(page, "final_04_ready_to_save")

    print("\n=== TEST COMPLETE ===")
    print("NOT saving the post — just checking if everything is ready.")
    print(f"Screenshots in: {SCREENSHOT_DIR}")
    page.wait_for_timeout(3000)
    browser.close()

os.unlink(tmp.name)
