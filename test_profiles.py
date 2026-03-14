"""
Test: Select Facebook + homecartel Instagram profiles
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
BRAVE_PATH = os.getenv("BRAVE_PATH")
BRAVE_USER_DATA = os.getenv("BRAVE_USER_DATA")

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

    page.screenshot(path="test_prof_1_all_deselected.png")
    print("  Screenshot: all deselected")

    # List all account images and their src
    print("\n[5] All account-image elements:")
    all_imgs = page.locator("img.account-image").all()
    for i, img in enumerate(all_imgs):
        src = img.get_attribute("src") or ""
        visible = img.is_visible()
        # Check which part of 39373932 is in the src
        has_hc_ig = "39373932" in src
        has_fb = "graph.facebook" in src
        print(f"  [{i}] visible={visible} fb={has_fb} hc_ig={has_hc_ig} src={src[:100]}...")

    # Click Facebook
    print("\n[6] Clicking Facebook...")
    try:
        fb = page.locator("img.account-image[src*='graph.facebook.com']").first
        print(f"  FB found, visible={fb.is_visible()}")
        fb.click()
        page.wait_for_timeout(1000)
        print("  Clicked FB!")
    except Exception as e:
        print(f"  FB error: {e}")

    page.screenshot(path="test_prof_2_fb_selected.png")

    # Click homecartel Instagram
    print("\n[7] Clicking homecartel Instagram...")
    # Try exact selector first
    try:
        ig = page.locator("img.account-image[src*='39373932']").first
        print(f"  IG found, visible={ig.is_visible()}")
        ig.click()
        page.wait_for_timeout(1000)
        print("  Clicked IG!")
    except Exception as e:
        print(f"  IG error with 39373932: {e}")
        # Try clicking by index
        print("  Trying by index...")
        all_imgs = page.locator("img.account-image").all()
        for i, img in enumerate(all_imgs):
            src = img.get_attribute("src") or ""
            if "cdninstagram" in src and "39373932" in src:
                print(f"  Found at index {i}, clicking...")
                img.click()
                page.wait_for_timeout(1000)
                print("  Clicked!")
                break

    page.screenshot(path="test_prof_3_both_selected.png")
    print("\n  Screenshot: after both selected")

    # Final check
    print("\n[8] Final state:")
    all_imgs = page.locator("img.account-image").all()
    for i, img in enumerate(all_imgs):
        src = img.get_attribute("src") or ""
        platform = "?"
        if "facebook" in src: platform = "FB"
        elif "39373932" in src: platform = "IG-homecartel"
        elif "cdninstagram" in src: platform = "IG-other"
        elif "tiktok" in src: platform = "TK"
        # Try to detect if selected by checking parent classes/styles
        try:
            parent = img.locator("xpath=ancestor::div[contains(@class,'poster')]").first
            parent_class = parent.get_attribute("class") or ""
            print(f"  [{i}] {platform} parent_class='{parent_class}'")
        except:
            print(f"  [{i}] {platform}")

    page.screenshot(path="test_prof_4_final.png")
    print("\nDone!")
    page.wait_for_timeout(3000)
    browser.close()
