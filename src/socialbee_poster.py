import os
import tempfile
import time
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


def _prepare_upload_file(url, filename, existing_local_path=None):
    """Return a local file path to upload plus whether this helper created it."""
    if existing_local_path:
        return existing_local_path, False
    return download_image(url, filename), True


def _wait_for_save_confirmation(page):
    """Wait 60 seconds after saving to let SocialBee finish processing."""
    print("  Waiting 60 seconds for SocialBee to finish processing...")
    page.wait_for_timeout(60000)


def _count_media_in_scope(scope):
    """Return the visible media count inside a page/locator scope."""
    selectors = (
        ".post-media-item:visible, .media-preview-item:visible, .uploaded-media .media-item:visible, .post-media .media-item:visible",
        ".uploaded-media video:visible, .uploaded-media img:visible, .post-media video:visible, .post-media img:visible",
        "video[src]:visible",
    )
    for selector in selectors:
        try:
            count = scope.locator(selector).count()
        except Exception:
            continue
        if count > 0:
            return count
    return 0


def _is_add_media_prompt_visible(scope):
    """Return True when a composer/variation scope shows an empty media prompt."""
    selectors = (
        "text=Add a photo or video",
        "button:has-text('Add a photo or video')",
    )
    for selector in selectors:
        try:
            if scope.locator(selector).first.is_visible(timeout=750):
                return True
        except Exception:
            pass
    return False


def _composer_media_count(page):
    """Return the visible media count in the active composer, using the first stable selector match."""
    return _count_media_in_scope(page)


def _find_remove_media_button(page):
    """Return the first visible remove/delete button scoped to uploaded media."""
    selectors = (
        ".post-media-item button[aria-label*='Remove' i]:visible, .media-preview-item button[aria-label*='Remove' i]:visible, .uploaded-media .media-item button[aria-label*='Remove' i]:visible, .post-media .media-item button[aria-label*='Remove' i]:visible",
        ".post-media-item button[title*='Remove' i]:visible, .media-preview-item button[title*='Remove' i]:visible, .uploaded-media .media-item button[title*='Remove' i]:visible, .post-media .media-item button[title*='Remove' i]:visible",
        ".post-media-item button[aria-label*='Delete' i]:visible, .media-preview-item button[aria-label*='Delete' i]:visible, .uploaded-media .media-item button[aria-label*='Delete' i]:visible, .post-media .media-item button[aria-label*='Delete' i]:visible",
        ".post-media-item button[title*='Delete' i]:visible, .media-preview-item button[title*='Delete' i]:visible, .uploaded-media .media-item button[title*='Delete' i]:visible, .post-media .media-item button[title*='Delete' i]:visible",
        ".post-media-item button:has-text('Remove'):visible, .media-preview-item button:has-text('Remove'):visible, .uploaded-media .media-item button:has-text('Remove'):visible, .post-media .media-item button:has-text('Remove'):visible",
    )
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=750):
                return locator
        except Exception:
            pass
    return None


def _clear_existing_composer_media(page):
    """Remove stale media from the active SocialBee composer before uploading a new selection."""
    media_count = _composer_media_count(page)
    if media_count <= 0:
        if _is_add_media_prompt_visible(page):
            print("  Composer media state is already clean")
        return

    print(f"  Clearing {media_count} stale media item(s) from the composer...")
    for _ in range(8):
        if media_count <= 0:
            break
        remove_button = _find_remove_media_button(page)
        if remove_button is None:
            raise RuntimeError(
                f"Composer already contains {media_count} media item(s), but no remove button was found."
            )
        remove_button.click()
        page.wait_for_timeout(1500)
        refreshed = _composer_media_count(page)
        if refreshed >= media_count:
            page.wait_for_timeout(1500)
            refreshed = _composer_media_count(page)
        if refreshed >= media_count and refreshed > 0:
            raise RuntimeError("Could not clear the existing SocialBee composer media.")
        media_count = refreshed

    final_count = _composer_media_count(page)
    if final_count != 0:
        raise RuntimeError(f"Composer still has {final_count} media item(s) after cleanup.")
    print("  Composer media cleared")


def _wait_for_exact_media_count(page, expected_count, timeout_ms=20000):
    """Wait until the composer shows the expected number of attached media items."""
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_count = _composer_media_count(page)
    while time.monotonic() < deadline:
        last_count = _composer_media_count(page)
        if last_count == expected_count:
            return last_count
        page.wait_for_timeout(500)
    return last_count


def _wait_for_scope_media(scope, minimum_count=1, timeout_ms=20000):
    """Wait until a scoped composer/variation shows media attachments."""
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_count = _count_media_in_scope(scope)
    while time.monotonic() < deadline:
        last_count = _count_media_in_scope(scope)
        if last_count >= minimum_count:
            return last_count
        time.sleep(0.5)
    return last_count


def _resolve_active_variation_scope(page, label=""):
    """Find the currently expanded variation container.

    Strategy:
    1. Prefer anchoring on a visible post-type dropdown (Feed Post / TikTok
       Public ▾) — but tolerate platforms that don't render one (some
       Instagram variations).
    2. Fall back to the visible editor (`.ql-editor`) and walk up to its
       enclosing container that also has a file input.
    """
    anchors = []
    try:
        dropdown = page.locator("button.share-location-button:visible").last
        if dropdown.count() > 0:
            try:
                dropdown.wait_for(state="visible", timeout=3000)
                anchors.append(dropdown)
            except Exception:
                pass
    except Exception:
        pass

    try:
        editor = page.locator(".ql-editor:visible").last
        if editor.count() > 0:
            anchors.append(editor)
    except Exception:
        pass

    candidates = (
        "xpath=ancestor::*[.//input[@type='file'] and (.//*[contains(@class,'ql-editor')] or .//*[@contenteditable='true'])][1]",
        "xpath=ancestor::*[.//input[@type='file']][1]",
        "xpath=ancestor::*[.//*[contains(@class,'ql-editor')] or .//*[@contenteditable='true']][1]",
    )
    for anchor in anchors:
        for selector in candidates:
            try:
                scope = anchor.locator(selector).first
                if scope.count() > 0:
                    return scope
            except Exception:
                pass

    print(f"  [{label}] Variation scope fallback to page-level selectors")
    return page


def _get_scope_editor(scope, label=""):
    """Return the editor for the active composer/variation scope."""
    selectors = (
        ".ql-editor:visible",
        "[contenteditable='true']:visible",
    )
    for selector in selectors:
        try:
            editor = scope.locator(selector).last
            if editor.count() > 0:
                editor.wait_for(state="visible", timeout=5000)
                return editor
        except Exception:
            pass
    raise RuntimeError(f"[{label}] No visible editor found for the active variation.")


def _get_scope_file_input(scope, label=""):
    """Return the file input for the active composer/variation scope."""
    try:
        inputs = scope.locator("input[type='file']")
        if inputs.count() > 0:
            return inputs.last
    except Exception:
        pass
    raise RuntimeError(f"[{label}] No file input found for the active variation.")


def _read_editor_text(editor):
    """Read current editor text safely."""
    for reader in (editor.inner_text, editor.text_content):
        try:
            value = reader()
        except Exception:
            continue
        if value is not None:
            return str(value).strip()
    return ""


def _activate_variation(page, variant_index, platform_name, screenshot_dir=None):
    """Expand a specific variation row and return its scoped container."""
    print(f"  [{platform_name}] Activating variation row {variant_index}...")
    rows = page.locator("[ng-click*='activateVariant']")
    row = rows.nth(variant_index)
    row.wait_for(state="visible", timeout=5000)
    try:
        row.scroll_into_view_if_needed()
    except Exception:
        pass
    try:
        row.click()
    except Exception:
        row.click(force=True)
    page.wait_for_timeout(2500)
    scope = _resolve_active_variation_scope(page, platform_name)
    _get_scope_editor(scope, platform_name)
    if screenshot_dir:
        page.screenshot(path=os.path.join(screenshot_dir, f"variation_{platform_name.lower()}_active.png"))
    return scope


def _ensure_variation_caption_and_media(page, variant_index, platform_name, caption, upload_path, screenshot_dir=None):
    """Ensure one active variation has the expected caption and media.

    Treats the visibility of the "Add a photo or video" prompt as the
    authoritative signal that the variation is missing media. SocialBee's
    media-thumbnail class names vary, so a count-based check on its own
    was unreliable and led the recovery upload to fire on variations that
    already had media (causing duplicate uploads, e.g. two photos on the
    Facebook variation).
    """
    scope = _activate_variation(page, variant_index, platform_name, screenshot_dir=screenshot_dir)
    editor = _get_scope_editor(scope, platform_name)
    editor_text = _read_editor_text(editor)
    add_prompt = _is_add_media_prompt_visible(scope)
    media_count = _count_media_in_scope(scope)
    has_media = (not add_prompt) and (media_count > 0 or _scope_has_media_dom(scope))
    print(
        f"  [{platform_name}] Before fill: editor_chars={len(editor_text)} "
        f"media_count={media_count} add_prompt={add_prompt} has_media={has_media}"
    )

    if not editor_text:
        editor.click()
        page.wait_for_timeout(300)
        editor.fill(caption)
        page.wait_for_timeout(500)
        editor_text = _read_editor_text(editor)

    if not has_media:
        print(f"  [{platform_name}] No media detected \u2014 uploading...")
        file_input = _get_scope_file_input(scope, platform_name)
        file_input.set_input_files(upload_path)
        page.wait_for_timeout(5000)
        # Wait for the add-prompt to disappear before falling back to the
        # count check, so we trust SocialBee's own "empty" indicator.
        for _ in range(20):
            if not _is_add_media_prompt_visible(scope):
                break
            page.wait_for_timeout(500)
        has_media = not _is_add_media_prompt_visible(scope)

    final_text = _read_editor_text(editor)
    final_add_prompt = _is_add_media_prompt_visible(scope)
    final_media_count = _count_media_in_scope(scope)
    print(
        f"  [{platform_name}] After fill: editor_chars={len(final_text)} "
        f"media_count={final_media_count} add_prompt={final_add_prompt}"
    )
    if not final_text:
        raise RuntimeError(f"[{platform_name}] Caption is still empty after variation fill.")
    if final_add_prompt:
        raise RuntimeError(f"[{platform_name}] Media prompt still visible after variation fill.")

    if screenshot_dir:
        page.screenshot(path=os.path.join(screenshot_dir, f"variation_{platform_name.lower()}_verified.png"))
    return scope


def _scope_has_media_dom(scope):
    """Loose check: returns True if the active scope contains a thumbnail-like img/video preview."""
    selectors = (
        "img[src*='blob:']:visible",
        "img[src*='data:image']:visible",
        "video:visible",
        ".item-wrap img:visible",
        "[class*='preview'] img:visible",
    )
    for selector in selectors:
        try:
            if scope.locator(selector).count() > 0:
                return True
        except Exception:
            pass
    return False


def _enable_tiktok_content_disclosure(scope, platform_name):
    """Enable the TikTok content disclosure toggle when it is visible and inactive."""
    try:
        disclosure = scope.locator("[ng-click*='updateContentDisclosure']:visible").last
        if disclosure.count() == 0 or not disclosure.is_visible(timeout=1500):
            print(f"  [{platform_name}] Content disclosure toggle not visible")
            return
        classes = disclosure.get_attribute("class") or ""
        if "inactive" in classes:
            disclosure.click()
            print(f"  [{platform_name}] Content disclosure enabled")
        else:
            print(f"  [{platform_name}] Content disclosure already active")
    except Exception as exc:
        print(f"  [{platform_name}] Content disclosure toggle skipped: {exc}")


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

                # Fill each variation using scoped helpers so checks/uploads
                # target the active variation, not the first one on the page.
                page.wait_for_timeout(2000)
                try:
                    rows = page.locator("[ng-click*='activateVariant']").all()
                    variant_count = len(rows)
                    print(f"  Found {variant_count} variation(s), filling each (scoped)...")
                    _video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
                    is_video_post = any(
                        os.path.splitext(p)[1].lower() in _video_exts for p in local_paths
                    )
                    for i in range(variant_count):
                        platform_label = f"var{i}"
                        try:
                            _ensure_variation_caption_and_media(
                                page,
                                i,
                                platform_label,
                                caption,
                                local_paths,
                                screenshot_dir=_ss_dir,
                            )
                        except Exception as ve:
                            print(f"  Variation [{i}] fill failed: {ve}")

                        if is_video_post:
                            try:
                                _set_variation_post_type(page, "Reel", _ss_dir, f"variation_{i}")
                            except Exception as re:
                                print(f"  Variation [{i}] post-type switch failed: {re}")

                    # Re-activate first variation (typically Facebook) to clear
                    # any aggregate warning indicator before saving.
                    if variant_count > 0:
                        try:
                            _activate_variation(page, 0, "var0", screenshot_dir=_ss_dir)
                            page.wait_for_timeout(5000)
                            page.screenshot(path=os.path.join(_ss_dir, "06_back_to_facebook.png"))
                            print("  First variation (Facebook) re-activated after fills")
                        except Exception as ae:
                            print(f"  Could not re-activate variation 0: {ae}")
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


def post_to_socialbee(caption, image_url, filename, category, schedule_date, schedule_time, result_queue, local_path=None):
    """Run the full SocialBee posting flow in a thread. Puts result in result_queue."""
    import traceback
    upload_path = None
    should_cleanup = False

    try:
        from playwright.sync_api import sync_playwright

        print("[1/8] Preparing image...")
        upload_path, should_cleanup = _prepare_upload_file(image_url, filename, existing_local_path=local_path)
        print(f"  Using file: {upload_path}")

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
            file_input.set_input_files(upload_path)
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

                # Fill each variation using scoped helpers so checks/uploads
                # target the active variation, not the first one on the page.
                page.wait_for_timeout(2000)
                try:
                    rows = page.locator("[ng-click*='activateVariant']").all()
                    variant_count = len(rows)
                    print(f"  Found {variant_count} variation(s), filling each (scoped)...")
                    for i in range(variant_count):
                        platform_label = f"var{i}"
                        try:
                            _ensure_variation_caption_and_media(
                                page,
                                i,
                                platform_label,
                                caption,
                                upload_path,
                            )
                        except Exception as ve:
                            print(f"  Variation [{i}] fill failed: {ve}")

                    # Re-activate first variation (typically Facebook) to clear
                    # any aggregate warning indicator before saving.
                    if variant_count > 0:
                        try:
                            _activate_variation(page, 0, "var0")
                        except Exception as ae:
                            print(f"  Could not re-activate variation 0: {ae}")
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
        if upload_path and should_cleanup:
            try:
                os.unlink(upload_path)
            except Exception:
                pass


def _set_variation_post_type(page, post_type, screenshot_dir=None, label="", scope=None):
    """Switch the visible variation's post type dropdown (Feed Post/Story/Reel)."""
    try:
        target = scope if scope is not None else page
        dropdown_btn = target.locator("button.share-location-button:visible").last
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


def post_to_socialbee_story(caption, image_url, filename, category, schedule_date, schedule_time, result_queue, local_path=None):
    """Post as Story to Facebook + Instagram on SocialBee (no TikTok). Uses Chrome."""
    import traceback
    upload_path = None
    should_cleanup = False
    screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright

        print("[1/8] Preparing image...")
        upload_path, should_cleanup = _prepare_upload_file(image_url, filename, existing_local_path=local_path)
        print(f"  Using file: {upload_path}")

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
            file_input.set_input_files(upload_path)
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
        if upload_path and should_cleanup:
            try:
                os.unlink(upload_path)
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
