"""
Test: Fill caption FIRST, then add TikTok, then handle TikTok variation.
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
test_img = Image.new('RGB', (200, 200), color='blue')
tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix='test_')
test_img.save(tmp.name)
tmp.close()
print(f"Test image: {tmp.name}")

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

    print("[3] Click Create post...")
    page.locator("button:has-text('Create post')").first.click()
    page.wait_for_timeout(3000)

    print("[4] Click Select None...")
    page.locator("button:has-text('Select None')").first.click()
    page.wait_for_timeout(2000)

    # Handle TikTok deselect popup
    try:
        tiktok = page.locator("text=TikTok").first
        if tiktok.is_visible(timeout=3000):
            page.locator("button:has-text('Proceed')").first.click()
            page.wait_for_timeout(2000)
            print("  TikTok deselect: Proceed")
    except:
        pass

    print("[5] Select Facebook...")
    page.locator("img.account-image[src*='graph.facebook.com']").first.click()
    page.wait_for_timeout(1000)

    print("[6] Select Instagram...")
    page.locator("img.account-image[src*='39373932_264858911021104']").first.click()
    page.wait_for_timeout(1000)

    # FILL CAPTION AND UPLOAD BEFORE TIKTOK
    print("[7] Filling caption FIRST (before TikTok)...")
    editor = page.locator(".ql-editor").first
    editor.wait_for(state="visible", timeout=10000)
    editor.click()
    editor.fill("Test caption - checking if it survives TikTok add")
    page.wait_for_timeout(500)
    print("  Caption filled!")

    print("[8] Uploading image FIRST (before TikTok)...")
    file_input = page.locator("input[type='file']").first
    file_input.set_input_files(tmp.name)
    page.wait_for_timeout(3000)
    print("  Image uploaded!")
    ss(page, "t2_01_before_tiktok_with_content")

    # NOW add TikTok
    print("\n[9] NOW selecting TikTok profile...")
    page.locator("img.account-image[src*='tiktokcdn']").first.click()
    page.wait_for_timeout(2000)
    ss(page, "t2_02_tiktok_popup")

    print("[10] Clicking Proceed on TikTok add...")
    try:
        proceed = page.locator("button.btn.btn-primary-sb:has-text('Proceed')").first
        if proceed.is_visible(timeout=5000):
            proceed.click()
            page.wait_for_timeout(3000)
            print("  Proceed clicked!")
    except Exception as e:
        print(f"  Error: {e}")
    ss(page, "t2_03_after_tiktok_proceed")

    # Check what we have now — variations?
    print("\n[11] Checking page state after TikTok added...")
    ql_editors = page.locator(".ql-editor").all()
    print(f"  .ql-editor count: {len(ql_editors)}")

    # Check for variation rows
    variations = page.locator("text=Variation").all()
    print(f"  'Variation' text count: {len(variations)}")

    # Look at the variation rows — what elements are clickable?
    print("\n[12] Exploring variation area...")
    # The variation rows seem to have profile images + warning triangles
    # Let's find clickable areas near the profile images

    # Check all account-image elements in the variation area
    all_imgs = page.locator("img.account-image").all()
    print(f"  Total account images: {len(all_imgs)}")
    for i, img in enumerate(all_imgs):
        try:
            src = img.get_attribute("src") or ""
            vis = img.is_visible()
            bbox = img.bounding_box() if vis else None
            platform = "?"
            if "facebook" in src: platform = "FB"
            elif "39373932" in src: platform = "IG"
            elif "tiktok" in src: platform = "TK"
            print(f"  [{i}] {platform} vis={vis} bbox={bbox}")
        except Exception as e:
            print(f"  [{i}] error: {e}")

    # Try clicking on the FIRST variation row (FB) to see if editor opens
    print("\n[13] Trying to click first variation row (FB)...")
    try:
        # The variation row might be a parent div containing the profile image + "Variation 1" text
        # Let's try clicking the area near the first variation's warning icon or text
        first_variation = page.locator("text=Variation 1").first
        if first_variation.is_visible(timeout=3000):
            first_variation.click()
            page.wait_for_timeout(2000)
            print("  Clicked first 'Variation 1' text")
            ss(page, "t2_04_after_click_first_variation")

            # Check if editor appeared
            ql = page.locator(".ql-editor").all()
            print(f"  .ql-editor count after click: {len(ql)}")
            if ql:
                vis = ql[0].is_visible()
                print(f"  First .ql-editor visible: {vis}")
                # Check if it has the caption we typed earlier
                text_content = ql[0].text_content()
                print(f"  Editor text: '{text_content[:80]}'" if text_content else "  Editor empty")
    except Exception as e:
        print(f"  Error: {e}")

    # Also try clicking the warning triangle icon
    print("\n[14] Looking for clickable warning/alert icons...")
    alerts = page.locator(".fa-exclamation-triangle, .alert-icon, [class*='warning'], [class*='alert']").all()
    print(f"  Alert-like elements: {len(alerts)}")

    # Try finding the variation row container
    print("\n[15] Inspecting variation row structure...")
    try:
        # Get the HTML around the variation area
        variation_html = page.locator(".ql-editor, [class*='variation'], [class*='customize']").first
        if variation_html.is_visible(timeout=2000):
            html = variation_html.evaluate("el => el.outerHTML")
            print(f"  HTML: {html[:300]}")
    except:
        pass

    # Let's try to get the parent container of the variation area
    print("\n[16] Getting full HTML of the post editor area...")
    try:
        # Look for the container that holds the variations
        containers = page.locator("[class*='variation'], [class*='post-editor'], [class*='customize'], [ng-repeat*='variation']").all()
        print(f"  Variation containers: {len(containers)}")
        for i, cont in enumerate(containers):
            try:
                html = cont.evaluate("el => el.outerHTML.substring(0, 400)")
                vis = cont.is_visible()
                print(f"  [{i}] vis={vis}")
                print(f"       {html}")
            except:
                pass
    except Exception as e:
        print(f"  Error: {e}")

    # Try another approach — click on the TikTok profile image in the variation area
    # (not the one in the top profile selector)
    print("\n[17] Trying to click TikTok variation row specifically...")
    try:
        # The TikTok variation might be the 3rd row with a TikTok icon
        tiktok_imgs = page.locator("img.account-image[src*='tiktokcdn']").all()
        print(f"  TikTok images found: {len(tiktok_imgs)}")
        # The first one is in the profile selector, subsequent ones in variation rows
        for i, tk_img in enumerate(tiktok_imgs):
            vis = tk_img.is_visible()
            bbox = tk_img.bounding_box() if vis else None
            print(f"  [{i}] vis={vis} bbox={bbox}")

        if len(tiktok_imgs) > 1:
            print("  Clicking last TikTok image (variation tab)...")
            tiktok_imgs[-1].click()
            page.wait_for_timeout(2000)
            ss(page, "t2_05_after_click_tiktok_variation")

            ql = page.locator(".ql-editor").all()
            print(f"  .ql-editor count: {len(ql)}")
            for i, q in enumerate(ql):
                print(f"    [{i}] visible={q.is_visible()}")
    except Exception as e:
        print(f"  Error: {e}")

    ss(page, "t2_06_final")
    print("\n=== DONE ===")
    print(f"Screenshots in: {SCREENSHOT_DIR}")
    page.wait_for_timeout(3000)
    browser.close()

os.unlink(tmp.name)
