# Copyright (c) David Berlioz
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI gallery indexer — interrogate untagged images via img2txt.

Runs as a sequential job: iterates gallery providers, finds images
without descriptions, resizes them, sends to an ai_images provider
that supports interrogation (e.g. CLIP via Forge), and writes back
the caption as metadata.
"""

import base64
import logging
import struct
import threading

log = logging.getLogger("nelson.ai_images.indexer")

# Max dimension for the thumbnail sent to CLIP (keeps payload small)
_THUMB_MAX = 512

# Singleton state
_stop_event = threading.Event()
_running = False


def is_running():
    """Whether the indexer is currently processing images."""
    return _running


def start_indexing(services):
    """Submit an indexing job to the sequential queue."""
    _stop_event.clear()
    job = services.jobs.enqueue(
        _run_indexer,
        kind="ai_gallery_index",
        params={"status": "queued"},
        services=services,
    )
    return job


def stop_indexing():
    """Signal the running indexer to stop after current image."""
    _stop_event.set()


def _run_indexer(services):
    """Main indexer loop — process all untagged images across galleries."""
    global _running
    _running = True
    try:
        return _run_indexer_inner(services)
    finally:
        _running = False


def _run_indexer_inner(services):
    log.warning("AI indexer started")
    gallery_svc = services.get("images")
    ai_svc = services.get("ai_images")
    if not gallery_svc or not ai_svc:
        log.warning("AI indexer: missing services (images=%s, ai_images=%s)",
                     gallery_svc is not None, ai_svc is not None)
        return {"indexed": 0, "error": "Missing images or ai_images service"}

    # Find the interrogate provider (configured or auto-detect)
    provider = None
    endpoint = ""
    cfg = services.config.proxy_for("ai_images")
    interrogate_id = cfg.get("interrogate_instance") or ""

    if interrogate_id:
        inst = ai_svc.get_instance(interrogate_id)
        if inst:
            provider = inst.provider
    if provider is None:
        for inst in ai_svc.list_instances():
            p = inst.provider
            if hasattr(p, "supports_interrogate") and p.supports_interrogate():
                provider = p
                break

    if provider is not None:
        try:
            pcfg = provider._config if hasattr(provider, "_config") else {}
            endpoint = pcfg.get("endpoint", "")
        except Exception:
            log.debug("Could not read endpoint from provider config")

    if provider is None:
        log.warning("AI indexer: no provider supports interrogation")
        return {"indexed": 0, "error": "No ai_images provider supports interrogation"}

    total = 0
    errors = 0

    for gallery_inst in gallery_svc.list_instances():
        if _stop_event.is_set():
            break

        gp = gallery_inst.provider
        wants = hasattr(gp, "wants_ai_index") and gp.wants_ai_index()
        log.warning("AI indexer: gallery '%s' wants_ai_index=%s", gallery_inst.name, wants)
        if not wants:
            continue

        # Rescan to pick up new files before checking for untagged
        if hasattr(gp, "rescan"):
            try:
                gp.rescan()
            except Exception:
                log.exception("AI indexer: rescan failed for '%s'", gallery_inst.name)

        untagged = gp.list_untagged(limit=500)
        if not untagged:
            log.warning("AI indexer: no untagged images in '%s'", gallery_inst.name)
            continue

        log.warning("AI indexer: %d untagged images in '%s'",
                    len(untagged), gallery_inst.name)

        for item in untagged:
            if _stop_event.is_set():
                log.info("Indexing stopped by user after %d images", total)
                break

            image_id = item.get("id", "")
            file_path = item.get("file_path", "")
            if not file_path:
                continue

            try:
                image_b64 = _resize_and_encode(file_path)
                if not image_b64:
                    continue

                # Acquire endpoint lock to avoid conflicts with generation
                if endpoint:
                    services.jobs.acquire_endpoint(endpoint)
                try:
                    caption, err = provider.interrogate(image_b64)
                finally:
                    if endpoint:
                        services.jobs.release_endpoint(endpoint)

                if err:
                    log.warning("Interrogate failed for %s: %s", image_id, err)
                    errors += 1
                    continue

                if caption:
                    # Parse CLIP output into description + keywords
                    meta = _parse_caption(caption)
                    gp.update_metadata(image_id, meta)
                    total += 1
                    log.debug("Indexed %s: %s", image_id, caption[:80])

            except Exception:
                log.exception("Error indexing %s", image_id)
                errors += 1

    log.info("Indexing complete: %d indexed, %d errors", total, errors)
    return {"indexed": total, "errors": errors}


def _parse_caption(caption):
    """Convert a CLIP caption into description + keywords.

    CLIP returns comma-separated tags like:
    'a woman with cat ears, anime style, digital art, ...'

    Filters out artist names and stock-photo tags that CLIP hallucinates.
    """
    parts = [p.strip() for p in caption.split(",") if p.strip()]
    if not parts:
        return {"description": caption}

    # First part is the main description, rest are keywords
    description = parts[0]
    keywords = [k for k in parts[1:] if not _is_noise_tag(k)]
    return {"description": description, "keywords": keywords}


# Tags CLIP hallucinates that are not useful as keywords
_NOISE_PATTERNS = (
    "a stock photo", "stock photo", "a jigsaw puzzle", "shutterstock",
    "an illustration", "a digital rendering", "a digital painting",
    "a screenshot", "a picture",
)


def _is_noise_tag(tag):
    """Return True if the tag is a CLIP hallucination (artist name, stock, etc)."""
    t = tag.strip().lower()
    # Known noise patterns
    for pat in _NOISE_PATTERNS:
        if t == pat or t.startswith(pat):
            return True
    # Artist names: CLIP outputs "Firstname Lastname" style tags.
    # Heuristic: 2-3 capitalized words, no common English words.
    words = tag.strip().split()
    if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words):
        # Check it's not a descriptive phrase like "Blue Sky"
        _common = {"The", "A", "An", "In", "On", "At", "By", "Of", "And",
                    "With", "From", "For", "Red", "Blue", "Green", "Black",
                    "White", "Dark", "Light", "Big", "Small", "Old", "New",
                    "High", "Low", "Art", "Style"}
        if not any(w in _common for w in words):
            return True
    return False


def _resize_and_encode(file_path):
    """Read an image, resize to thumbnail, return base64 PNG or JPEG.

    Uses stdlib only — reads raw file if dimensions are small enough,
    otherwise resamples via basic nearest-neighbor on raw pixel data.
    For JPEG/PNG under the threshold, just base64 the file as-is.
    """
    import os
    if not os.path.isfile(file_path):
        return None

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext not in ("jpg", "jpeg", "png", "bmp", "webp", "gif"):
        return None

    # Read dimensions
    w, h = _read_dimensions_quick(file_path, ext)

    # If image is already small enough, send as-is
    if 0 < w <= _THUMB_MAX and 0 < h <= _THUMB_MAX:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    # For larger images, we need to resize. Try subprocess with
    # magick/convert if available, otherwise send as-is (CLIP handles it)
    resized = _resize_with_magick(file_path, ext)
    if resized:
        return resized

    # Fallback: send original (CLIP can handle large images, just slower)
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        # Skip files larger than 10 MB
        if len(data) > 10 * 1024 * 1024:
            return None
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def _resize_with_magick(file_path, ext):
    """Resize using ImageMagick if available. Returns base64 or None."""
    import shutil
    import subprocess
    import tempfile

    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        cmd = [magick, file_path,
               "-resize", "%dx%d>" % (_THUMB_MAX, _THUMB_MAX),
               "-quality", "85", tmp_path]
        subprocess.run(cmd, capture_output=True, timeout=10)

        import os
        if os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
            with open(tmp_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            os.unlink(tmp_path)
            return data
        os.unlink(tmp_path)
    except Exception:
        log.debug("ImageMagick resize failed for %s", file_path, exc_info=True)
        try:
            import os
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
    return None


def _read_dimensions_quick(file_path, ext):
    """Quick dimension read from file header. Returns (w, h) or (0, 0)."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)

        if header[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", header[16:24])
            return (w, h)

        if header[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", header[6:10])
            return (w, h)

        if header[:2] == b"\xff\xd8":
            return _read_jpeg_dims(file_path)

    except Exception:
        log.debug("Failed to read dimensions for %s", file_path, exc_info=True)
    return (0, 0)


def _read_jpeg_dims(path):
    """Read JPEG dimensions from SOF marker."""
    try:
        with open(path, "rb") as f:
            f.read(2)
            while True:
                marker = f.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    break
                mtype = marker[1]
                if mtype in (0xC0, 0xC1, 0xC2):
                    f.read(2)
                    data = f.read(5)
                    if len(data) >= 5:
                        h, w = struct.unpack(">HH", data[1:5])
                        return (w, h)
                    break
                elif mtype in (0xD9, 0xDA):
                    break
                else:
                    seg_len = struct.unpack(">H", f.read(2))[0]
                    f.seek(seg_len - 2, 1)
    except Exception:
        log.debug("Failed to read JPEG dimensions for %s", path, exc_info=True)
    return (0, 0)
