#!/usr/bin/env python3
"""
render_verify.py — Stage 4 verification: screenshot the reconstruction HTML
with headless Chromium and (optionally) build a side-by-side comparison sheet
against the cleaned original.

Usage:
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python render_verify.py slide.html
    python render_verify.py slide.html --ref slide_clean.jpg
    python render_verify.py a.html b.html --width 1280 --height 720

Outputs, next to each input:
    <name>_render.png    — 1280x720 screenshot
    <name>_compare.png   — original (top) vs render (bottom), when --ref given

Falls back to wkhtmltoimage if Playwright/Chromium is unavailable
(note: wkhtmltoimage is an older WebKit — absolute-positioned layouts are
fine, modern flex/grid may not be).

Dependencies: playwright (preferred), Pillow (for the comparison sheet).
"""

import argparse
import os
import shutil
import subprocess
import sys


def shoot_playwright(paths, width, height):
    from playwright.sync_api import sync_playwright
    from pathlib import Path
    outs = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        for f in paths:
            f_abs = os.path.abspath(f)
            # Use pathlib for URI-safe path construction
            file_url = Path(f_abs).resolve().as_uri()
            page.goto(file_url)
            page.wait_for_load_state("networkidle")
            out = os.path.splitext(f_abs)[0] + "_render.png"
            page.screenshot(path=out, clip={"x": 0, "y": 0,
                                            "width": width, "height": height})
            outs.append(out)
            print("wrote", out)
        browser.close()
    return outs


def shoot_wkhtml(paths, width, height):
    outs = []
    for f in paths:
        f = os.path.abspath(f)
        out = os.path.splitext(f)[0] + "_render.png"
        subprocess.run(["wkhtmltoimage", "--width", str(width),
                        "--height", str(height), "--quality", "90", f, out],
                       check=True, capture_output=True)
        outs.append(out)
        print("wrote", out, "(wkhtmltoimage fallback)")
    return outs


def comparison_sheet(render_png, ref_img, width):
    from PIL import Image
    r = Image.open(render_png).convert("RGB")
    o = Image.open(ref_img).convert("RGB")
    o = o.resize((width, round(o.height * width / o.width)), Image.LANCZOS)
    gap = 14
    sheet = Image.new("RGB", (width, o.height + r.height + gap), "#444444")
    sheet.paste(o, (0, 0))
    sheet.paste(r, (0, o.height + gap))
    out = os.path.splitext(render_png)[0].replace("_render", "") + "_compare.png"
    sheet.save(out)
    print("wrote", out, "(original on top, render below)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="+", help="HTML file(s) to render")
    ap.add_argument("--ref", help="cleaned original image for side-by-side sheet")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    # Chromium binaries commonly live here in the Claude environment
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")

    try:
        outs = shoot_playwright(args.html, args.width, args.height)
    except Exception as e:  # playwright missing or browser absent
        if shutil.which("wkhtmltoimage"):
            print(f"playwright unavailable ({e.__class__.__name__}); "
                  "falling back to wkhtmltoimage", file=sys.stderr)
            outs = shoot_wkhtml(args.html, args.width, args.height)
        else:
            print("error: no headless renderer available "
                  "(install playwright or wkhtmltoimage)", file=sys.stderr)
            return 1

    if args.ref:
        for out in outs:
            comparison_sheet(out, args.ref, args.width)
    return 0


if __name__ == "__main__":
    sys.exit(main())
