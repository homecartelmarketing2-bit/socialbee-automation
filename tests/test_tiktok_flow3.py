"""
Test: Explore TikTok variation - find the warning/privacy mode element.
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
test_img = Image.new('RGB', (200, 200), color='green')
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

    print("[2] Navigate + Create post + Select None + Proceed...")
    page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    page.locator("button:has-text('Create post')").first.click()
    page.wait_for_timeout(3000)
    page.locator("button:has-text('Select None')").first.click()
    page.wait_for_timeout(2000)
    try:
        if page.locator("text=TikTok").first.is_visible(timeout=3000):
            page.locator("button:has-text('Proceed')").first.click()
            page.wait_for_timeout(2000)
    except:
        pass

    print("[3] Select FB + IG, fill caption, upload image...")
    page.locator("img.account-image[src*='graph.facebook.com']").first.click()
    page.wait_for_timeout(500)
    page.locator("img.account-image[src*='39373932_264858911021104']").first.click()
    page.wait_for_timeout(500)
    editor = page.locator(".ql-editor").first
    editor.wait_for(state="visible", timeout=10000)
    editor.click()
    editor.fill("Test caption for privacy mode check")
    page.wait_for_timeout(500)
    page.locator("input[type='file']").first.set_input_files(tmp.name)
    page.wait_for_timeout(3000)

    print("[4] Add TikTok + Proceed...")
    page.locator("img.account-image[src*='tiktokcdn']").first.click()
    page.wait_for_timeout(2000)
    try:
        proceed = page.locator("button.btn.btn-primary-sb:has-text('Proceed')").first
        if proceed.is_visible(timeout=5000):
            proceed.click()
            page.wait_for_timeout(3000)
    except:
        pass
    ss(page, "t3_01_variations_visible")

    # NOW explore the TikTok variation DOM
    print("\n[5] Dumping variant-editors HTML...")
    try:
        variant_editors = page.locator(".variant-editors").all()
        print(f"  .variant-editors count: {len(variant_editors)}")
        for i, ve in enumerate(variant_editors):
            html = ve.evaluate("el => el.innerHTML.substring(0, 2000)")
            print(f"\n  === variant-editors [{i}] ===")
            print(f"  {html}")
    except Exception as e:
        print(f"  Error: {e}")

    # Try to find the TikTok-specific warning or privacy elements
    print("\n[6] Looking for TikTok-specific elements...")
    for selector in [
        "[ng-click*='variant']",
        "[ng-click*='edit']",
        "[ng-click*='expand']",
        "[ng-click*='open']",
        ".variant-editor",
        ".variant-content",
        ".tiktok-privacy",
        "[class*='privacy']",
        "[class*='tiktok']",
        "select[ng-model*='privacy']",
        "select[ng-model*='tiktok']",
        "[ng-model*='privacy']",
        "[ng-model*='tiktok']",
        ".fa-exclamation-triangle",
    ]:
        els = page.locator(selector).all()
        if els:
            vis = sum(1 for e in els if e.is_visible())
            print(f"  '{selector}': {len(els)} found, {vis} visible")
            for j, el in enumerate(els[:3]):
                try:
                    html = el.evaluate("el => el.outerHTML.substring(0, 300)")
                    print(f"    [{j}] {html}")
                except:
                    pass

    # Try clicking directly on the TikTok variation row container
    print("\n[7] Finding TikTok variation row and exploring its children...")
    try:
        # Get all variant rows (ng-repeat="variant in value track by $index")
        variant_rows = page.locator("[ng-repeat*='variant in value']").all()
        print(f"  Variant rows: {len(variant_rows)}")
        for i, row in enumerate(variant_rows):
            html = row.evaluate("el => el.outerHTML.substring(0, 500)")
            vis = row.is_visible()
            bbox = row.bounding_box() if vis else None
            print(f"\n  [{i}] vis={vis} bbox={bbox}")
            print(f"  HTML: {html}")
    except Exception as e:
        print(f"  Error: {e}")

    # Try clicking the TEXT content of the TikTok variation (3rd row)
    print("\n[8] Trying to click on TikTok variant row text...")
    try:
        # The TikTok row is the 3rd one (index 2)
        variant_rows = page.locator("[ng-repeat*='variant in value']").all()
        if len(variant_rows) >= 3:
            tk_row = variant_rows[2]
            print(f"  Clicking TikTok variant row...")
            tk_row.click()
            page.wait_for_timeout(3000)
            ss(page, "t3_02_after_click_tk_row")

            # Check what changed
            ql = page.locator(".ql-editor").all()
            print(f"  .ql-editor count: {len(ql)}")

            # Check for new elements that appeared
            for sel in [".ql-editor", "[contenteditable]", "textarea", "select", "[class*='privacy']"]:
                els = page.locator(sel).all()
                vis = sum(1 for e in els if e.is_visible())
                if els:
                    print(f"  '{sel}': {len(els)} found, {vis} visible")
    except Exception as e:
        print(f"  Error: {e}")

    # Try to find ANY ng-click on the variant row or its children
    print("\n[9] Finding all ng-click attributes in variation area...")
    try:
        all_clickable = page.evaluate("""() => {
            const editors = document.querySelectorAll('.variant-editors');
            const results = [];
            editors.forEach((editor, i) => {
                const clickable = editor.querySelectorAll('[ng-click]');
                clickable.forEach(el => {
                    results.push({
                        editorIdx: i,
                        tag: el.tagName,
                        ngClick: el.getAttribute('ng-click'),
                        class: el.className.substring(0, 100),
                        text: el.textContent.substring(0, 80).trim(),
                        visible: el.offsetParent !== null
                    });
                });
            });
            return results;
        }""")
        print(f"  Found {len(all_clickable)} clickable elements in variant-editors:")
        for item in all_clickable:
            print(f"    <{item['tag']}> ng-click='{item['ngClick']}' class='{item['class']}' text='{item['text']}' vis={item['visible']}")
    except Exception as e:
        print(f"  Error: {e}")

    ss(page, "t3_03_final")
    print("\n=== DONE ===")
    page.wait_for_timeout(3000)
    browser.close()

os.unlink(tmp.name)
