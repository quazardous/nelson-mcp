#!/usr/bin/env python3
"""Download pysqlite3 wheel for bundling into the .oxt.

LO's Python on Windows lacks sqlite3, and LO's custom python312.dll
is missing symbols needed by CPython's official _sqlite3.pyd.
pysqlite3 statically links sqlite3, avoiding the symbol issue.

Usage:
    python scripts/fetch_sqlite3.py [--python-version 3.12]

Files are placed in build/sqlite3_win/pysqlite3/ ready for the build
script to copy into plugin/lib/.
"""

import argparse
import glob
import io
import os
import shutil
import sys
import urllib.request
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "build", "sqlite3_win")

# Persistent wheel cache — survives `make clean` (which wipes build/), so
# repeated test builds do not re-download. Override with NELSON_WHEEL_CACHE.
CACHE_DIR = os.environ.get(
    "NELSON_WHEEL_CACHE",
    os.path.join(PROJECT_ROOT, ".cache", "wheels"),
)

# PyPI JSON API to find the wheel URL
PYPI_URL = "https://pypi.org/pypi/pysqlite3/json"


def _cached_wheel(cp_tag):
    """Return the path to a cached matching wheel, or None."""
    pattern = os.path.join(CACHE_DIR, "pysqlite3-*-%s-*win_amd64.whl" % cp_tag)
    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else None


def fetch_pysqlite3(python_version="3.12"):
    """Download pysqlite3 wheel (cached) and extract to build/sqlite3_win/."""
    marker = os.path.join(OUTPUT_DIR, "pysqlite3", "__init__.py")
    if os.path.isfile(marker):
        print("pysqlite3 already present in %s" % OUTPUT_DIR)
        return 0

    cp_tag = "cp%s" % python_version.replace(".", "")

    # ── Fast path: reuse a cached wheel, no network at all ────────────────
    whl_data = None
    cached = _cached_wheel(cp_tag)
    if cached:
        print("Using cached wheel %s" % os.path.relpath(cached, PROJECT_ROOT))
        with open(cached, "rb") as f:
            whl_data = f.read()

    # ── Slow path: resolve + download from PyPI, then cache it ────────────
    if whl_data is None:
        import json
        print("Fetching pysqlite3 wheel info from PyPI...")
        resp = urllib.request.urlopen(PYPI_URL)
        data = json.loads(resp.read())

        # Look for cp<ver>-win_amd64 wheel
        wheel_url = None
        wheel_fn = None
        for url_info in data.get("urls", []):
            fn = url_info["filename"]
            if cp_tag in fn and "win_amd64" in fn and fn.endswith(".whl"):
                wheel_url, wheel_fn = url_info["url"], fn
                break

        if not wheel_url:
            # Search all releases
            for ver, files in data.get("releases", {}).items():
                for url_info in files:
                    fn = url_info["filename"]
                    if cp_tag in fn and "win_amd64" in fn and fn.endswith(".whl"):
                        wheel_url, wheel_fn = url_info["url"], fn
                        break
                if wheel_url:
                    break

        if not wheel_url:
            print("ERROR: No pysqlite3 wheel found for %s win_amd64" % cp_tag,
                  file=sys.stderr)
            return 1

        print("Downloading %s ..." % wheel_url)
        resp = urllib.request.urlopen(wheel_url)
        whl_data = resp.read()
        print("Downloaded %.1f KB" % (len(whl_data) / 1024))

        # Save to the persistent cache for next time.
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_path = os.path.join(CACHE_DIR, wheel_fn)
        with open(cache_path, "wb") as f:
            f.write(whl_data)
        print("Cached wheel in %s" % os.path.relpath(cache_path, PROJECT_ROOT))

    # Extract pysqlite3/ directory from wheel
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pysqlite3_out = os.path.join(OUTPUT_DIR, "pysqlite3")
    if os.path.isdir(pysqlite3_out):
        shutil.rmtree(pysqlite3_out)

    with zipfile.ZipFile(io.BytesIO(whl_data)) as zf:
        for name in zf.namelist():
            if name.startswith("pysqlite3/"):
                target = os.path.join(OUTPUT_DIR, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if not name.endswith("/"):
                    with open(target, "wb") as f:
                        f.write(zf.read(name))

    # Verify
    if not os.path.isfile(marker):
        print("ERROR: pysqlite3 extraction failed", file=sys.stderr)
        return 1

    # List extracted files
    for root, dirs, files in os.walk(pysqlite3_out):
        for fn in files:
            fp = os.path.join(root, fn)
            print("  %s (%d bytes)" % (
                os.path.relpath(fp, OUTPUT_DIR), os.path.getsize(fp)))

    print("pysqlite3 ready in %s" % OUTPUT_DIR)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Fetch pysqlite3 for LO Python")
    parser.add_argument("--python-version", default="3.12",
                        help="Python minor version (default: 3.12)")
    args = parser.parse_args()
    return fetch_pysqlite3(args.python_version)


if __name__ == "__main__":
    sys.exit(main())
