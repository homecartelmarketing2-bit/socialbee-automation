import os
import tempfile
import requests
from src.config import BRAVE_PATH, BRAVE_USER_DATA, BRAVE_USER_DATA_AUTO, CHROME_PATH, CHROME_USER_DATA_STORY, CHROME_USER_DATA_POST


def download_image(url, filename):
    """Download image/video to a temp file and return the path."""
    from src.config import VIDEO_EXTENSIONS
    ext = os.path.splitext(filename)[1] or ".jpg"
    is_video = ext.lower() in VIDEO_EXTENSIONS
    timeout = 300 if is_video else 60  # 5 min for videos, 1 min for images
    resp = requests.get(url, timeout=timeout, stream=is_video)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="sb_")
    if is_video:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            tmp.write(chunk)
    else:
        tmp.write(resp.content)
    tmp.close()
    return tmp.name


def _wait_for_save_confirmation(page):
    """Wait 60 seconds after saving to let SocialBee finish processing."""
    print("  Waiting 60 seconds for SocialBee to finish processing...")
    page.wait_for_timeout(60000)


def post_to_socialbee_multiple(caption, image_urls, filenames, category, schedule_date, schedule_time, result_queue):
    """Post multiple images to SocialBee. image_urls and filenames are lists."""
    import traceback
    local_paths = []

    try:
        from playwright.sync_api import sync_playwright

        # Download all images
        print(f"[1/8] Downloading {len(image_urls)} images...")
        for i, (url, fname) in enumerate(zip(image_urls, filenames)):
            path = download_image(url, fname)
            local_paths.append(path)
            print(f"  Image {i+1} saved to: {path}")

        with sync_playwright() as p:
            print("[2/8] Launching Chrome browser...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir=CHROME_USER_DATA_POST,
                executable_path=CHROME_PATH,
                headless=False,
                channel=None,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.new_page()
            # Close any default tabs Chrome opened
            for p_old in browser.pages:
                if p_old != page:
                    try:
                        p_old.close()
                    except Exception:
                        pass

            print("[3/8] Navigating to SocialBee...")
            page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass  # page load timeout is OK, wait_for_timeout below covers it
            page.wait_for_timeout(3000)

            print("[4/8] Clicking 'Create post'...")
            create_btn = page.locator("button:has-text('Create post')").first
            create_btn.wait_for(state="visible", timeout=10000)
            create_btn.click()
            page.wait_for_timeout(3000)

            print("[5/8] Deselecting all profiles first...")
            try:
                select_none = page.locator("button:has-text('Select None')").first
                select_none.wait_for(state="visible", timeout=5000)
                select_none.click()
                page.wait_for_timeout(1500)
                print("  Clicked 'Select None' — all profiles deselected")
            except Exception as e:
                print(f"  'Select None' not found: {e}")

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

            # Debug screenshots folder
            import tempfile as _tmpmod
            _ss_dir = os.path.join(_tmpmod.gettempdir(), "sb_debug_screenshots")
            os.makedirs(_ss_dir, exist_ok=True)
            print(f"  Debug screenshots → {_ss_dir}")

            # Paste caption BEFORE adding TikTok (editor works in single mode)
            print("[6/8] Pasting caption...")
            editor = page.locator(".ql-editor").first
            editor.wait_for(state="visible", timeout=10000)
            editor.click()
            page.wait_for_timeout(500)
            editor.fill(caption)
            page.wait_for_timeout(500)

            # Upload ALL files BEFORE adding TikTok
            print(f"[7/8] Uploading {len(local_paths)} files...")
            file_input = page.locator("input[type='file']").first
            file_input.set_input_files(local_paths)
            # Wait longer for videos (larger files)
            page.wait_for_timeout(10000)
            print(f"  {len(local_paths)} files uploaded")
            page.screenshot(path=os.path.join(_ss_dir, "01_after_upload.png"))

            # NOW add TikTok — caption+images carry over to all variations
            print("  Selecting homecartel TikTok profile...")
            try:
                tiktok = page.locator("img.account-image[src*='tiktokcdn']").first
                tiktok.wait_for(state="visible", timeout=5000)
                tiktok.click()
                page.wait_for_timeout(1500)
                print("  Selected TikTok profile")

                # TikTok "Add TikTok profile" confirmation popup → click Proceed
                try:
                    proceed_btn = page.locator("button.btn.btn-primary-sb:has-text('Proceed')").first
                    if proceed_btn.is_visible(timeout=5000):
                        proceed_btn.click()
                        page.wait_for_timeout(3000)
                        print("  Clicked 'Proceed' — TikTok added, variations active")
                except Exception:
                    pass

                page.screenshot(path=os.path.join(_ss_dir, "02_after_tiktok_added.png"))

                # Check each variation: click it, screenshot, check editor + media
                page.wait_for_timeout(2000)
                try:
                    rows = page.locator("[ng-click*='activateVariant']").all()
                    print(f"  Found {len(rows)} variation(s), checking each...")
                    for i, row in enumerate(rows):
                        row.click()
                        page.wait_for_timeout(3000)
                        page.screenshot(path=os.path.join(_ss_dir, f"03_variation_{i}_clicked.png"))

                        # Check if editor has content
                        var_editor = page.locator(".ql-editor").first
                        var_editor.wait_for(state="visible", timeout=5000)
                        editor_text = (var_editor.inner_text() or "").strip()
                        editor_html = (var_editor.inner_html() or "").strip()

                        # Check if "Add a photo or video" is visible — means NO media attached
                        add_photo_btn = page.locator("text=Add a photo or video").first
                        no_media = False
                        try:
                            no_media = add_photo_btn.is_visible(timeout=2000)
                        except Exception:
                            no_media = False
                        has_media = not no_media

                        print(f"  Variation [{i}]: editor_text={len(editor_text)} chars, has_media={has_media} (add_photo_visible={no_media})")

                        if not editor_text:
                            print(f"  Variation [{i}] — filling caption...")
                            var_editor.click()
                            page.wait_for_timeout(300)
                            var_editor.fill(caption)
                            page.wait_for_timeout(500)
                            page.screenshot(path=os.path.join(_ss_dir, f"04_variation_{i}_caption_filled.png"))

                        if not has_media:
                            print(f"  Variation [{i}] — uploading files...")
                            page.locator("input[type='file']").first.set_input_files(local_paths)
                            page.wait_for_timeout(10000)
                            page.screenshot(path=os.path.join(_ss_dir, f"05_variation_{i}_files_uploaded.png"))
                        else:
                            print(f"  Variation [{i}] — media already present, skipping upload")

                        # If video files, switch post type to "Reel"
                        _video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
                        is_video_post = any(
                            os.path.splitext(p)[1].lower() in _video_exts for p in local_paths
                        )
                        if is_video_post:
                            _set_variation_post_type(page, "Reel", _ss_dir, f"variation_{i}")

                    # Click back to Facebook variation (first row) to clear warning icon
                    if len(rows) > 0:
                        print("  Clicking back to Facebook variation...")
                        rows[0].click()
                        page.wait_for_timeout(5000)
                        page.screenshot(path=os.path.join(_ss_dir, "06_back_to_facebook.png"))
                        print("  Facebook variation active (warning should clear)")
                except Exception as e2:
                    print(f"  Variation fill error: {e2}")
                    page.screenshot(path=os.path.join(_ss_dir, "error_variation.png"))
            except Exception as e:
                print(f"  WARNING: Could not find TikTok profile: {e}")
                page.screenshot(path=os.path.join(_ss_dir, "error_tiktok.png"))

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

            if schedule_date and schedule_time:
                print(f"[7/8] Setting schedule: {schedule_date} {schedule_time}")
                try:
                    from datetime import datetime
                    target_dt = datetime.strptime(f"{schedule_date} {schedule_time}", "%Y-%m-%d %H:%M")
                    target_day = target_dt.day
                    target_month = target_dt.strftime("%B")
                    target_year = str(target_dt.year)

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

                    post_specific = page.locator("text=Post at a specific time").first
                    post_specific.click()
                    page.wait_for_timeout(500)

                    add_time_btn = page.locator("button:has-text('Add a posting time')").first
                    add_time_btn.wait_for(state="visible", timeout=5000)
                    add_time_btn.click()
                    page.wait_for_timeout(2000)

                    modal = page.locator(".specific-schedule-modal")
                    modal.wait_for(state="visible", timeout=5000)

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

                    hour_input = modal.locator("input#hour")
                    hour_input.click(click_count=3)
                    hour_input.fill(str(hour_12))
                    page.wait_for_timeout(300)

                    minute_input = modal.locator("input#minute")
                    minute_input.click(click_count=3)
                    minute_input.fill(str(minute).zfill(2))
                    page.wait_for_timeout(300)

                    if meridian == "AM":
                        am_btn = modal.locator("button:has-text('AM')").first
                        am_btn.click()
                    else:
                        pm_btn = modal.locator("button:has-text('PM')").first
                        pm_btn.click()
                    page.wait_for_timeout(300)

                    apply_btn = modal.locator("button:has-text('Apply')").first
                    apply_btn.click()
                    page.wait_for_timeout(1000)

                    print(f"  Schedule set: {target_month} {target_day}, {target_year} at {hour_12}:{str(minute).zfill(2)} {meridian}")
                except Exception as e:
                    print(f"  Schedule setting failed: {e}")
                    print("  Post will be saved without schedule (check SocialBee manually)")

            print("[8/8] Saving post...")
            save_btn = page.locator("button.submit-button:has-text('Save post')").first
            save_btn.wait_for(state="visible", timeout=10000)
            save_btn.click()
            page.wait_for_timeout(3000)

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

            _wait_for_save_confirmation(page)
            print("Post saved successfully.")

        result_queue.put(("success", f"Before & After post created with {len(image_urls)} images!"))

    except Exception as e:
        error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
        print(f"ERROR: {error_msg}")
        result_queue.put(("error", str(e)))

    finally:
        for path in local_paths:
            try:
                os.unlink(path)
            except Exception:
                pass


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
            print("[2/8] Launching Chrome browser...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir=CHROME_USER_DATA_POST,
                executable_path=CHROME_PATH,
                headless=False,
                channel=None,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.new_page()
            # Close any default tabs Chrome opened
            for p_old in browser.pages:
                if p_old != page:
                    try:
                        p_old.close()
                    except Exception:
                        pass

            # Navigate to SocialBee poster
            print("[3/8] Navigating to SocialBee...")
            page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass  # page load timeout is OK, wait_for_timeout below covers it
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

            # 4. Select Facebook + homecartel Instagram profiles (NOT TikTok yet)
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

            # 5. Paste caption BEFORE adding TikTok (editor works in single mode)
            print("[6/8] Pasting caption...")
            editor = page.locator(".ql-editor").first
            editor.wait_for(state="visible", timeout=10000)
            editor.click()
            page.wait_for_timeout(500)
            editor.fill(caption)
            page.wait_for_timeout(500)

            # 6. Upload image BEFORE adding TikTok
            print("[7/8] Uploading image...")
            file_input = page.locator("input[type='file']").first
            file_input.set_input_files(local_path)
            page.wait_for_timeout(5000)
            print("  Image uploaded")

            # 7. NOW add TikTok — caption+image carry over to all variations
            print("  Selecting homecartel TikTok profile...")
            try:
                tiktok = page.locator("img.account-image[src*='tiktokcdn']").first
                tiktok.wait_for(state="visible", timeout=5000)
                tiktok.click()
                page.wait_for_timeout(1500)
                print("  Selected TikTok profile")

                # TikTok "Add TikTok profile" confirmation popup → click Proceed
                try:
                    proceed_btn = page.locator("button.btn.btn-primary-sb:has-text('Proceed')").first
                    if proceed_btn.is_visible(timeout=5000):
                        proceed_btn.click()
                        page.wait_for_timeout(3000)
                        print("  Clicked 'Proceed' — TikTok added, variations active")
                except Exception:
                    pass

                # Fill each variation: click it, check editor, fill if empty
                page.wait_for_timeout(2000)
                try:
                    rows = page.locator("[ng-click*='activateVariant']").all()
                    print(f"  Found {len(rows)} variation(s), checking each...")
                    for i, row in enumerate(rows):
                        row.click()
                        page.wait_for_timeout(3000)

                        # Check if editor has content
                        var_editor = page.locator(".ql-editor").first
                        var_editor.wait_for(state="visible", timeout=5000)
                        editor_text = (var_editor.inner_text() or "").strip()

                        # Check if files are uploaded
                        media_previews = page.locator(".post-media-item, .media-preview-item, .uploaded-media img, .post-media img, .media-item").all()
                        has_media = len(media_previews) > 0

                        if not editor_text or not has_media:
                            print(f"  Variation [{i}] missing content (text={bool(editor_text)}, media={has_media}) — filling...")
                            if not editor_text:
                                var_editor.click()
                                page.wait_for_timeout(300)
                                var_editor.fill(caption)
                                page.wait_for_timeout(500)
                            if not has_media:
                                page.locator("input[type='file']").first.set_input_files(local_path)
                                page.wait_for_timeout(5000)
                            print(f"  Variation [{i}] filled!")
                        else:
                            print(f"  Variation [{i}] OK (has text + media)")
                except Exception as e2:
                    print(f"  Variation fill error: {e2}")
            except Exception as e:
                print(f"  WARNING: Could not find TikTok profile: {e}")

            # 8. Set category
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
            page.wait_for_timeout(3000)

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

            _wait_for_save_confirmation(page)
            print("Post saved successfully.")

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


def _set_variation_post_type(page, post_type, screenshot_dir=None, label=""):
    """Switch the visible variation's post type dropdown (Feed Post/Story/Reel)."""
    try:
        dropdown_btn = page.locator("button.share-location-button:visible").first
        if not dropdown_btn.is_visible(timeout=3000):
            print(f"  [{label}] No post-type dropdown visible — skipping")
            return
        current = dropdown_btn.inner_text().strip()
        if post_type.lower() in current.lower():
            print(f"  [{label}] Already set to '{current}' — skipping")
            return
        print(f"  [{label}] Switching from '{current}' to '{post_type}'...")
        dropdown_btn.click()
        page.wait_for_timeout(1500)
        item = page.locator("li.dropdown-item:visible").filter(has_text=post_type).first
        item.wait_for(state="visible", timeout=5000)
        item.click()
        page.wait_for_timeout(2000)
        new_val = dropdown_btn.inner_text().strip()
        print(f"  [{label}] Post type now: '{new_val}'")
        if screenshot_dir:
            page.screenshot(path=os.path.join(screenshot_dir, f"07_{label}_set_{post_type.lower()}.png"))
    except Exception as e:
        print(f"  [{label}] Could not set post type to '{post_type}': {e}")


def _activate_variant_and_set_story(page, variant_index, platform_name, screenshot_dir):
    """Click a variation row to expand it, then switch its Feed Post dropdown to Story.
    variant_index: 0 for first row (FB), 1 for second row (IG), etc.
    """
    print(f"  [{platform_name}] Clicking variation row {variant_index} to expand...")

    # Click the variation row to expand its editor
    variant_rows = page.locator("[ng-click*='activateVariant']")
    row = variant_rows.nth(variant_index)
    row.wait_for(state="visible", timeout=5000)
    row.click()
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(screenshot_dir, f"story_{platform_name}_row_expanded.png"))

    # Now the "Feed Post" dropdown should be visible in the expanded editor
    dropdown_btn = page.locator("button.share-location-button:visible").first
    dropdown_btn.wait_for(state="visible", timeout=8000)
    btn_text = dropdown_btn.inner_text().strip()
    print(f"  [{platform_name}] Found dropdown: '{btn_text}'")

    dropdown_btn.click()
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(screenshot_dir, f"story_{platform_name}_dropdown_open.png"))

    # Pick "Story" from the visible dropdown items
    story_item = page.locator("li.dropdown-item:visible").filter(has_text="Story").first
    story_item.wait_for(state="visible", timeout=5000)
    story_item.click()
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(screenshot_dir, f"story_{platform_name}_story_selected.png"))

    # Verify it changed
    new_text = page.locator("button.share-location-button:visible").first.inner_text().strip()
    print(f"  [{platform_name}] Dropdown now says: '{new_text}'")


def post_to_socialbee_story(caption, image_url, filename, category, schedule_date, schedule_time, result_queue):
    """Post as Story to Facebook + Instagram on SocialBee (no TikTok). Uses Chrome."""
    import traceback
    local_path = None
    screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright

        print("[1/8] Downloading image...")
        local_path = download_image(image_url, filename)
        print(f"  Saved to: {local_path}")

        with sync_playwright() as p:
            print("[2/8] Launching Chrome browser...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir=CHROME_USER_DATA_STORY,
                executable_path=CHROME_PATH,
                headless=False,
                channel=None,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )

            page = browser.new_page()
            # Close any default tabs Chrome opened
            for p_old in browser.pages:
                if p_old != page:
                    try:
                        p_old.close()
                    except Exception:
                        pass

            print("[3/8] Navigating to SocialBee...")
            page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass  # page load timeout is OK, wait_for_timeout below covers it
            page.wait_for_timeout(3000)

            print("[4/8] Clicking 'Create post'...")
            create_btn = page.locator("button:has-text('Create post')").first
            create_btn.wait_for(state="visible", timeout=10000)
            create_btn.click()
            page.wait_for_timeout(3000)

            # Deselect all profiles
            print("[5/8] Deselecting all profiles first...")
            try:
                select_none = page.locator("button:has-text('Select None')").first
                select_none.wait_for(state="visible", timeout=5000)
                select_none.click()
                page.wait_for_timeout(1500)
                print("  Clicked 'Select None' — all profiles deselected")
            except Exception as e:
                print(f"  'Select None' not found: {e}")

            # TikTok popup: click "Proceed" to confirm deselecting TikTok
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

            # Select Facebook profile
            print("  Selecting Facebook profile...")
            try:
                fb = page.locator("img.account-image[src*='graph.facebook.com']").first
                fb.wait_for(state="visible", timeout=5000)
                fb.click()
                page.wait_for_timeout(500)
                print("  Selected Facebook profile")
            except Exception as e:
                print(f"  WARNING: Could not find Facebook profile: {e}")

            # Select homecartel Instagram profile
            print("  Selecting homecartel Instagram profile...")
            try:
                ig = page.locator("img.account-image[src*='39373932_264858911021104']").first
                ig.wait_for(state="visible", timeout=5000)
                ig.click()
                page.wait_for_timeout(500)
                print("  Selected homecartel Instagram profile")
            except Exception as e:
                print(f"  WARNING: Could not find homecartel IG profile: {e}")

            page.wait_for_timeout(1000)
            page.screenshot(path=os.path.join(screenshot_dir, "story_01_profiles_selected.png"))

            # Paste caption
            print("[6/8] Pasting caption...")
            editor = page.locator(".ql-editor").first
            editor.wait_for(state="visible", timeout=10000)
            editor.click()
            page.wait_for_timeout(500)
            editor.fill(caption)
            page.wait_for_timeout(500)

            # Upload image
            print("[7/8] Uploading image...")
            file_input = page.locator("input[type='file']").first
            file_input.set_input_files(local_path)
            page.wait_for_timeout(5000)
            print("  Image uploaded")
            page.screenshot(path=os.path.join(screenshot_dir, "story_02_after_upload.png"))

            # Click "Customize for each profile" to get per-platform dropdowns
            print("  Clicking 'Customize for each profile'...")
            try:
                customize_btn = page.locator("button:has-text('Customize for each profile')").first
                customize_btn.wait_for(state="visible", timeout=5000)
                customize_btn.click()
                page.wait_for_timeout(3000)
                print("  Customization enabled — per-profile dropdowns visible")
                page.screenshot(path=os.path.join(screenshot_dir, "story_03_after_customize.png"))
            except Exception as e:
                print(f"  'Customize for each profile' not found, dropdowns may already be visible: {e}")
                page.screenshot(path=os.path.join(screenshot_dir, "story_03_customize_not_found.png"))

            # Switch Facebook to Story (first collapsed row = index 0)
            try:
                _activate_variant_and_set_story(page, 0, "Facebook", screenshot_dir)
            except Exception as e:
                print(f"  WARNING: Could not set Facebook to Story: {e}")
                page.screenshot(path=os.path.join(screenshot_dir, "story_err_fb.png"))

            # Switch Instagram to Story
            # After FB is set, FB row stays expanded and IG becomes the only
            # collapsed row — so it's now at index 0 again, not index 1.
            try:
                _activate_variant_and_set_story(page, 0, "Instagram", screenshot_dir)
            except Exception as e:
                print(f"  WARNING: Could not set Instagram to Story: {e}")
                page.screenshot(path=os.path.join(screenshot_dir, "story_err_ig.png"))

            page.screenshot(path=os.path.join(screenshot_dir, "story_04_both_story_set.png"))

            # Set category
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

            # Schedule handling
            if schedule_date and schedule_time:
                print(f"  Setting schedule: {schedule_date} {schedule_time}")
                try:
                    from datetime import datetime
                    target_dt = datetime.strptime(f"{schedule_date} {schedule_time}", "%Y-%m-%d %H:%M")
                    target_day = target_dt.day
                    target_month = target_dt.strftime("%B")
                    target_year = str(target_dt.year)

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

                    post_specific = page.locator("text=Post at a specific time").first
                    post_specific.click()
                    page.wait_for_timeout(500)

                    add_time_btn = page.locator("button:has-text('Add a posting time')").first
                    add_time_btn.wait_for(state="visible", timeout=5000)
                    add_time_btn.click()
                    page.wait_for_timeout(2000)

                    modal = page.locator(".specific-schedule-modal")
                    modal.wait_for(state="visible", timeout=5000)

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

                    hour_input = modal.locator("input#hour")
                    hour_input.click(click_count=3)
                    hour_input.fill(str(hour_12))
                    page.wait_for_timeout(300)

                    minute_input = modal.locator("input#minute")
                    minute_input.click(click_count=3)
                    minute_input.fill(str(minute).zfill(2))
                    page.wait_for_timeout(300)

                    if meridian == "AM":
                        am_btn = modal.locator("button:has-text('AM')").first
                        am_btn.click()
                    else:
                        pm_btn = modal.locator("button:has-text('PM')").first
                        pm_btn.click()
                    page.wait_for_timeout(300)

                    apply_btn = modal.locator("button:has-text('Apply')").first
                    apply_btn.click()
                    page.wait_for_timeout(1000)

                    print(f"  Schedule set: {target_month} {target_day}, {target_year} at {hour_12}:{str(minute).zfill(2)} {meridian}")
                except Exception as e:
                    print(f"  Schedule setting failed: {e}")
                    print("  Post will be saved without schedule (check SocialBee manually)")

            # Save post
            print("[8/8] Saving post...")
            save_btn = page.locator("button.submit-button:has-text('Save post')").first
            save_btn.wait_for(state="visible", timeout=10000)
            save_btn.click()
            page.wait_for_timeout(3000)

            _wait_for_save_confirmation(page)
            page.screenshot(path=os.path.join(screenshot_dir, "story_05_after_save.png"))

            print("Story post saved successfully.")

        result_queue.put(("success", "Story post created successfully!"))

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


def setup_chrome_post_profile():
    """Launch Chrome with post profile so user can log in to SocialBee.
    Browser stays open until user closes it manually."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_POST,
            executable_path=CHROME_PATH,
            headless=False,
            channel=None,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        browser.close()


def setup_chrome_story_profile():
    """Launch Chrome with story profile so user can log in to SocialBee.
    Browser stays open until user closes it manually."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_STORY,
            executable_path=CHROME_PATH,
            headless=False,
            channel=None,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        browser.close()


def setup_automation_profile():
    """Launch Brave with automation profile so user can log in to SocialBee.
    Browser stays open until user closes it manually."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=BRAVE_USER_DATA_AUTO,
            executable_path=BRAVE_PATH,
            headless=False,
            channel=None,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://app.socialbee.com/poster", wait_until="domcontentloaded")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        browser.close()
