"""Build script: PyInstaller + bundle Chromium + package zip."""
import os
import sys
import glob
import json
import shutil
import subprocess
import tempfile

DIST_NAME = "Content Creation Automation Marketing"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_DIR, "dist", DIST_NAME)
SPEC_FILE = os.path.join(PROJECT_DIR, f"{DIST_NAME}.spec")
LOCAL_UPLOAD_FIELDS = {
    "Collection Categ System": "collection-category",
    "Tips Educational Photos": "tips-and-education",
    "Quotes Photos": "quotes-photos",
}


def find_playwright_chromium():
    """Find Playwright's installed Chromium directory."""
    base = os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright")
    if not os.path.isdir(base):
        print(f"ERROR: Playwright browsers not found at {base}")
        print("  Run: playwright install chromium")
        sys.exit(1)

    # Find latest chromium-* folder
    chromium_dirs = sorted(glob.glob(os.path.join(base, "chromium-*")), reverse=True)
    if not chromium_dirs:
        print("ERROR: No chromium-* folder in ms-playwright/")
        sys.exit(1)

    chrome_win = os.path.join(chromium_dirs[0], "chrome-win64")
    if not os.path.isdir(chrome_win):
        # Try chrome-win (older naming)
        chrome_win = os.path.join(chromium_dirs[0], "chrome-win")
    if not os.path.isdir(chrome_win):
        print(f"ERROR: chrome-win64 not found in {chromium_dirs[0]}")
        sys.exit(1)

    print(f"Found Chromium: {chrome_win}")
    return chrome_win


def runtime_data_dirs():
    """Return data dirs used by current and previous packaged layouts."""
    return [
        os.path.join(DIST_DIR, "data"),
        os.path.join(DIST_DIR, "_internal", "data"),
    ]


def backup_runtime_data():
    """Preserve packaged runtime data before PyInstaller refreshes dist."""
    backup_root = tempfile.mkdtemp(prefix="sb_dist_data_")
    backups = {}
    for index, data_dir in enumerate(runtime_data_dirs()):
        if os.path.isdir(data_dir):
            dst = os.path.join(backup_root, f"data_{index}")
            shutil.copytree(data_dir, dst)
            backups[data_dir] = dst
    return backup_root, backups


def restore_runtime_data(backups):
    """Restore runtime data after PyInstaller rebuilds the app folder."""
    for data_dir, backup_dir in backups.items():
        if os.path.isdir(data_dir):
            shutil.rmtree(data_dir)
        os.makedirs(os.path.dirname(data_dir), exist_ok=True)
        shutil.copytree(backup_dir, data_dir)


def ensure_local_upload_manifest(data_dir):
    """Ensure every local upload queue exists and stays separate."""
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "tips_reels"), exist_ok=True)
    for folder_name in LOCAL_UPLOAD_FIELDS.values():
        os.makedirs(os.path.join(data_dir, "local_uploads", folder_name), exist_ok=True)

    manifest_path = os.path.join(data_dir, "local_upload_manifest.json")
    manifest = {"version": 1, "categories": {}}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh) or {}
            if isinstance(loaded, dict):
                manifest = loaded
        except Exception as exc:
            print(f"  WARNING: could not read {manifest_path}: {exc}")

    categories = manifest.get("categories")
    if not isinstance(categories, dict):
        categories = {}
    for source_field in LOCAL_UPLOAD_FIELDS:
        if not isinstance(categories.get(source_field), list):
            categories[source_field] = []

    manifest["version"] = 1
    manifest["categories"] = categories
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=True, indent=2)


def main():
    print("=" * 60)
    print(f"Building {DIST_NAME} - Plug-and-Play Edition")
    print("=" * 60)
    backup_root, data_backups = backup_runtime_data()

    # Step 1: Run PyInstaller
    print("\n[1/5] Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", SPEC_FILE, "--noconfirm"],
        cwd=PROJECT_DIR,
    )
    if result.returncode != 0:
        print("ERROR: PyInstaller failed!")
        sys.exit(1)
    standalone_exe = os.path.join(PROJECT_DIR, "dist", f"{DIST_NAME}.exe")
    if os.path.exists(standalone_exe):
        os.remove(standalone_exe)
        print(f"  Removed stray top-level exe: {standalone_exe}")

    # Step 2: Copy Chromium
    print("\n[2/5] Bundling Chromium...")
    chromium_src = find_playwright_chromium()
    chromium_dst = os.path.join(DIST_DIR, "chromium")
    if os.path.exists(chromium_dst):
        shutil.rmtree(chromium_dst)
    shutil.copytree(chromium_src, chromium_dst)
    print(f"  Copied to {chromium_dst}")

    # Step 3: Copy config/runtime files to dist root
    print("\n[3/5] Copying config/runtime files...")
    for fname in ["config.json", ".env", "config.json.example", ".env.example"]:
        src = os.path.join(PROJECT_DIR, fname)
        dst = os.path.join(DIST_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  {fname} -> dist/")
        else:
            print(f"  WARNING: {fname} not found, skipping")

    # Step 4: Create data directory
    print("\n[4/5] Restoring data directories...")
    restore_runtime_data(data_backups)
    for data_dir in runtime_data_dirs():
        ensure_local_upload_manifest(data_dir)
        print(f"  {data_dir}")

    # Step 5: Create zip
    print("\n[5/5] Creating zip archive...")
    zip_path = os.path.join(PROJECT_DIR, "dist", DIST_NAME)
    shutil.make_archive(zip_path, "zip", os.path.join(PROJECT_DIR, "dist"), DIST_NAME)
    zip_file = zip_path + ".zip"
    size_mb = os.path.getsize(zip_file) / (1024 * 1024)
    print(f"  Created: {zip_file} ({size_mb:.1f} MB)")

    print("\n" + "=" * 60)
    print("BUILD COMPLETE!")
    print(f"  Folder: {DIST_DIR}")
    print(f"  Zip:    {zip_file}")
    print("=" * 60)
    shutil.rmtree(backup_root, ignore_errors=True)


if __name__ == "__main__":
    main()
