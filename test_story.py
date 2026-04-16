"""
Test Story flow — focus on IG variation row issue.
Uses Chrome profile (must be logged in first via Setup Login Chrome - Story).
Does NOT save the post.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from src.config import CHROME_PATH, CHROME_USER_DATA_STORY

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def shot(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"ts_{name}.png")
    page.screenshot(path=path)
    print(f"  >> {name}.png")


def run_test():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        print("Launching Chrome...")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_STORY,
            executable_path=CHROME_PATH,
            headless=False,
            channel=None,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.new_page()
        for p_old in browser.pages:
            if p_old != page:
                try:
                    p_old.close()
                except:
                    pass

        print("Navigating to SocialBee poster...")
        page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(5000)
        shot(page, "01_loaded")

        # Create post
        print("Clicking 'Create post'...")
        create_btn = page.locator("button:has-text('Create post')").first
        create_btn.wait_for(state="visible", timeout=15000)
        create_btn.click()
        page.wait_for_timeout(5000)
        shot(page, "02_create_post")

        # Select None
        try:
            select_none = page.locator("button:has-text('Select None')").first
            if select_none.is_visible(timeout=3000):
                select_none.click()
                page.wait_for_timeout(1500)
                try:
                    proceed = page.locator("button:has-text('Proceed')").first
                    if proceed.is_visible(timeout=3000):
                        proceed.click()
                        page.wait_for_timeout(2000)
                except:
                    pass
        except:
            pass

        # Select FB + IG
        print("Selecting FB + IG...")
        try:
            page.locator("img.account-image[src*='graph.facebook.com']").first.click()
            page.wait_for_timeout(500)
            print("  FB OK")
        except Exception as e:
            print(f"  FB: {e}")
        try:
            page.locator("img.account-image[src*='39373932_264858911021104']").first.click()
            page.wait_for_timeout(500)
            print("  IG OK")
        except Exception as e:
            print(f"  IG: {e}")

        page.wait_for_timeout(1000)

        # Caption
        editor = page.locator(".ql-editor").first
        editor.wait_for(state="visible", timeout=15000)
        editor.click()
        editor.fill("TEST STORY - will cancel")
        page.wait_for_timeout(500)

        # Customize
        print("Clicking 'Customize for each profile'...")
        customize_btn = page.locator("button:has-text('Customize for each profile')").first
        customize_btn.wait_for(state="visible", timeout=5000)
        customize_btn.click()
        page.wait_for_timeout(3000)
        shot(page, "03_customized")

        # Inspect variant rows BEFORE any clicking
        variant_rows = page.locator("[ng-click*='activateVariant']")
        count = variant_rows.count()
        print(f"\n=== BEFORE: {count} variant rows ===")
        for i in range(count):
            row = variant_rows.nth(i)
            txt = row.inner_text().strip().replace("\n", " ")
            print(f"  Row[{i}]: '{txt[:80]}'")

        # === FB (row 0) ===
        print("\n=== FB: clicking row 0 ===")
        variant_rows.nth(0).click()
        page.wait_for_timeout(3000)
        shot(page, "04_fb_expanded")

        dropdown = page.locator("button.share-location-button:visible").first
        dropdown.wait_for(state="visible", timeout=5000)
        print(f"  Dropdown: '{dropdown.inner_text().strip()}'")
        dropdown.click()
        page.wait_for_timeout(1500)
        shot(page, "05_fb_dropdown")

        page.locator("li.dropdown-item:visible").filter(has_text="Story").first.click()
        page.wait_for_timeout(1500)
        shot(page, "06_fb_story_done")
        print(f"  FB now: '{page.locator('button.share-location-button:visible').first.inner_text().strip()}'")

        # Re-inspect variant rows AFTER FB Story is set
        page.wait_for_timeout(2000)
        variant_rows2 = page.locator("[ng-click*='activateVariant']")
        count2 = variant_rows2.count()
        print(f"\n=== AFTER FB Story: {count2} variant rows ===")
        for i in range(count2):
            row = variant_rows2.nth(i)
            try:
                txt = row.inner_text().strip().replace("\n", " ")
                is_vis = row.is_visible(timeout=1000)
                print(f"  Row[{i}]: visible={is_vis} '{txt[:80]}'")
            except Exception as e:
                print(f"  Row[{i}]: error={e}")

        # === IG (row 0 now — FB expanded, IG is the only collapsed row left) ===
        print("\n=== IG: clicking row 0 (after FB expanded, IG shifts to index 0) ===")
        try:
            row1 = variant_rows2.nth(0)
            row1.wait_for(state="visible", timeout=5000)
            txt1 = row1.inner_text().strip().replace("\n", " ")
            print(f"  Row 1 text: '{txt1[:80]}'")
            row1.click()
            page.wait_for_timeout(3000)
            shot(page, "07_ig_expanded")

            # Check dropdown
            dropdown2 = page.locator("button.share-location-button:visible").first
            dropdown2.wait_for(state="visible", timeout=5000)
            print(f"  IG Dropdown: '{dropdown2.inner_text().strip()}'")
            dropdown2.click()
            page.wait_for_timeout(1500)
            shot(page, "08_ig_dropdown")

            items = page.locator("li.dropdown-item:visible").all()
            print(f"  Items: {[i.inner_text().strip() for i in items]}")

            page.locator("li.dropdown-item:visible").filter(has_text="Story").first.click()
            page.wait_for_timeout(1500)
            shot(page, "09_ig_story_done")
            print(f"  IG now: '{page.locator('button.share-location-button:visible').first.inner_text().strip()}'")
        except Exception as e:
            print(f"  IG ERROR: {e}")
            shot(page, "07_ig_error")

            # Debug: try all variant rows
            print("\n  === DEBUG: trying to find IG row ===")
            all_rows = page.locator("[ng-click*='activateVariant']").all()
            print(f"  Total rows now: {len(all_rows)}")
            for i, r in enumerate(all_rows):
                try:
                    txt = r.inner_text().strip().replace("\n", " ")
                    vis = r.is_visible(timeout=500)
                    print(f"    [{i}] vis={vis} '{txt[:80]}'")
                except:
                    print(f"    [{i}] error reading")

            # Also look for IG-specific elements
            ig_imgs = page.locator("img[src*='instagram'], img[src*='39373932']").all()
            print(f"  IG images found: {len(ig_imgs)}")

            # Try clicking the last variant row instead
            if len(all_rows) > 1:
                print(f"\n  Trying last row (index {len(all_rows)-1})...")
                all_rows[-1].click()
                page.wait_for_timeout(3000)
                shot(page, "07b_last_row_clicked")

        shot(page, "10_final")
        print("\n=== Closing in 15s ===")
        page.wait_for_timeout(15000)

        try:
            page.locator("text=Cancel").first.click()
            page.wait_for_timeout(2000)
        except:
            pass

        browser.close()
        print("Done.")


if __name__ == "__main__":
    run_test()
