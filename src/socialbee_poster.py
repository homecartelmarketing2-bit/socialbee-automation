import os
import tempfile
import requests
from src.config import BRAVE_PATH, BRAVE_USER_DATA


def download_image(url, filename):
    """Download image to a temp file and return the path."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    ext = os.path.splitext(filename)[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="sb_")
    tmp.write(resp.content)
    tmp.close()
    return tmp.name


def post_to_socialbee(caption, image_url, filename, category, schedule_date, schedule_time, result_queue):
    """Run the full SocialBee posting flow in a thread. Puts result in result_queue."""
    import traceback
    local_path = None

    try:
        from playwright.sync_api import sync_playwright

        # Download image first
        print("[1/8] Downloading image...")
        local_path = download_image(image_url, filename)
        print(f"  Saved to: {local_path}")

        with sync_playwright() as p:
            print("[2/8] Launching Brave browser...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir=BRAVE_USER_DATA,
                executable_path=BRAVE_PATH,
                headless=False,
                channel=None,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.pages[0] if browser.pages else browser.new_page()

            # Navigate to SocialBee poster
            print("[3/8] Navigating to SocialBee...")
            page.goto("https://app.socialbee.com/poster", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # 1. Click "Create post"
            print("[4/8] Clicking 'Create post'...")
            create_btn = page.locator("button:has-text('Create post')").first
            create_btn.wait_for(state="visible", timeout=10000)
            create_btn.click()
            page.wait_for_timeout(3000)

            # 2. FIRST: Click "Select None." to deselect ALL profiles
            print("[5/8] Deselecting all profiles first...")
            try:
                select_none = page.locator("button:has-text('Select None')").first
                select_none.wait_for(state="visible", timeout=5000)
                select_none.click()
                page.wait_for_timeout(1500)
                print("  Clicked 'Select None' — all profiles deselected")
            except Exception as e:
                print(f"  'Select None' not found: {e}")

            # 3. TikTok popup: click "Proceed" to confirm deselecting TikTok
            try:
                tiktok_text = page.locator("text=TikTok").first
                if tiktok_text.is_visible(timeout=3000):
                    proceed_btn = page.locator("button:has-text('Proceed')").first
                    if proceed_btn.is_visible(timeout=3000):
                        proceed_btn.click()
                        page.wait_for_timeout(2000)
                        print("  Clicked 'Proceed' — TikTok deselected")
            except Exception:
                pass

            # 4. Select Facebook + homecartel Instagram profiles
            print("  Selecting Facebook profile...")
            try:
                fb = page.locator("img.account-image[src*='graph.facebook.com']").first
                fb.wait_for(state="visible", timeout=5000)
                fb.click()
                page.wait_for_timeout(500)
                print("  Selected Facebook profile")
            except Exception as e:
                print(f"  WARNING: Could not find Facebook profile: {e}")

            print("  Selecting homecartel Instagram profile...")
            try:
                ig = page.locator("img.account-image[src*='39373932_264858911021104']").first
                ig.wait_for(state="visible", timeout=5000)
                ig.click()
                page.wait_for_timeout(500)
                print("  Selected homecartel Instagram profile")
            except Exception as e:
                print(f"  WARNING: Could not find homecartel IG profile: {e}")

            # 4. Paste caption
            print("[6/8] Pasting caption...")
            editor = page.locator(".ql-editor").first
            editor.wait_for(state="visible", timeout=10000)
            editor.click()
            page.wait_for_timeout(500)

            # Use fill for speed, then verify
            editor.fill(caption)
            page.wait_for_timeout(500)

            # 5. Upload image
            print("[7/8] Uploading image...")
            file_input = page.locator("input[type='file']").first
            file_input.set_input_files(local_path)
            # Wait for image preview to appear
            page.wait_for_timeout(5000)
            print("  Image uploaded")

            # 6. Set category
            if category:
                print(f"  Setting category: {category}")
                try:
                    cat_dropdown = page.locator("#status-category").first
                    cat_dropdown.click()
                    page.wait_for_timeout(500)

                    search_input = page.locator("input.ui-select-search:visible").first
                    search_input.fill(category)
                    page.wait_for_timeout(1000)

                    cat_option = page.locator(".ui-select-choices-row:visible").first
                    cat_option.click()
                    page.wait_for_timeout(500)
                    print(f"  Category set: {category}")
                except Exception as e:
                    print(f"  Category selection skipped: {e}")

            # 7. Schedule handling
            if schedule_date and schedule_time:
                print(f"[7/8] Setting schedule: {schedule_date} {schedule_time}")
                try:
                    from datetime import datetime
                    target_dt = datetime.strptime(f"{schedule_date} {schedule_time}", "%Y-%m-%d %H:%M")
                    target_day = target_dt.day
                    target_month = target_dt.strftime("%B")
                    target_year = str(target_dt.year)

                    # Convert 24h to 12h format
                    hour_24 = target_dt.hour
                    if hour_24 == 0:
                        hour_12, meridian = 12, "AM"
                    elif hour_24 < 12:
                        hour_12, meridian = hour_24, "AM"
                    elif hour_24 == 12:
                        hour_12, meridian = 12, "PM"
                    else:
                        hour_12, meridian = hour_24 - 12, "PM"
                    minute = target_dt.minute

                    # Click "Post at a specific time"
                    post_specific = page.locator("text=Post at a specific time").first
                    post_specific.click()
                    page.wait_for_timeout(500)

                    # Click "+ Add a posting time"
                    add_time_btn = page.locator("button:has-text('Add a posting time')").first
                    add_time_btn.wait_for(state="visible", timeout=5000)
                    add_time_btn.click()
                    page.wait_for_timeout(2000)

                    # Wait for the schedule modal
                    modal = page.locator(".specific-schedule-modal")
                    modal.wait_for(state="visible", timeout=5000)

                    # Navigate calendar to correct month/year
                    max_nav = 24
                    for _ in range(max_nav):
                        cur_month_el = modal.locator("button.current span").first
                        cur_year_el = modal.locator("button.current span").nth(1)
                        cur_month = cur_month_el.inner_text(timeout=2000)
                        cur_year = cur_year_el.inner_text(timeout=2000)

                        if cur_month == target_month and cur_year == target_year:
                            break

                        cur_dt = datetime.strptime(f"{cur_month} {cur_year}", "%B %Y")
                        tgt_dt = datetime.strptime(f"{target_month} {target_year}", "%B %Y")
                        if tgt_dt > cur_dt:
                            modal.locator("button.next").first.click()
                        else:
                            modal.locator("button.previous").first.click()
                        page.wait_for_timeout(500)

                    # Click the target day in the calendar
                    day_cells = modal.locator("td[role='gridcell'] span:not(.is-other-month)").all()
                    clicked_day = False
                    for cell in day_cells:
                        try:
                            txt = cell.inner_text(timeout=500).strip()
                            if txt == str(target_day):
                                cell.click()
                                clicked_day = True
                                break
                        except Exception:
                            continue

                    if not clicked_day:
                        modal.locator(f"td[role='gridcell'] span:text-is('{target_day}')").first.click()

                    page.wait_for_timeout(500)

                    # Set hour
                    hour_input = modal.locator("input#hour")
                    hour_input.click(click_count=3)
                    hour_input.fill(str(hour_12))
                    page.wait_for_timeout(300)

                    # Set minute
                    minute_input = modal.locator("input#minute")
                    minute_input.click(click_count=3)
                    minute_input.fill(str(minute).zfill(2))
                    page.wait_for_timeout(300)

                    # Set AM/PM
                    if meridian == "AM":
                        am_btn = modal.locator("button:has-text('AM')").first
                        am_btn.click()
                    else:
                        pm_btn = modal.locator("button:has-text('PM')").first
                        pm_btn.click()
                    page.wait_for_timeout(300)

                    # Click Apply
                    apply_btn = modal.locator("button:has-text('Apply')").first
                    apply_btn.click()
                    page.wait_for_timeout(1000)

                    print(f"  Schedule set: {target_month} {target_day}, {target_year} at {hour_12}:{str(minute).zfill(2)} {meridian}")
                except Exception as e:
                    print(f"  Schedule setting failed: {e}")
                    print("  Post will be saved without schedule (check SocialBee manually)")

            # 8. Save post
            print("[8/8] Saving post...")
            save_btn = page.locator("button.submit-button:has-text('Save post')").first
            save_btn.wait_for(state="visible", timeout=10000)
            save_btn.click()
            page.wait_for_timeout(5000)

            # Dismiss TikTok popup again if it appears after save
            try:
                tiktok_text = page.locator("text=TikTok").first
                if tiktok_text.is_visible(timeout=3000):
                    proceed_btn = page.locator("button:has-text('Proceed')").first
                    if proceed_btn.is_visible(timeout=2000):
                        proceed_btn.click()
                        page.wait_for_timeout(1000)
                        print("  Clicked 'Proceed' on TikTok popup (after save)")
            except Exception:
                pass

            print("Post saved! Closing browser...")
            browser.close()

        result_queue.put(("success", "Post created successfully!"))

    except Exception as e:
        error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
        print(f"ERROR: {error_msg}")
        result_queue.put(("error", str(e)))

    finally:
        if local_path:
            try:
                os.unlink(local_path)
            except Exception:
                pass
