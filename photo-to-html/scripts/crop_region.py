#!/usr/bin/env python3
"""
crop_region.py — Crop a region from the cleaned slide image and emit it as a
base64 data-URI <img> tag, ready to paste into the reconstruction HTML.

Used for decision-tree rules [1b]/[3]: content that can't (or shouldn't) be
redrawn as SVG — photos, screenshots, complex renders, and *irregular dense
diagrams* whose exact topology IS the content (random net routes, scattered
instance-specific geometry). When one vector iteration fails to match such a
region, stop polishing and crop.

Usage:
    python crop_region.py slide_clean.jpg --bbox 120,340,560,610
    python crop_region.py slide_clean.jpg --bbox 510,128,888,316 --white-balance
    python crop_region.py slide_clean.jpg --bbox 90,1000,420,1340 --key-light 232

Blending options (make photo crops sit naturally on a vector page):
    --white-balance     per-channel levels (p88 -> 253): removes the photo's
                        color cast so the crop background approaches page white.
                        Default choice for rectangular diagram crops.
    --flat-field        divide by a Gaussian-blurred background estimate:
                        removes vignetting / uneven illumination. Use when
                        --white-balance leaves a visible brightness gradient.
                        Caution: distorts large solid color fields (> blur
                        radius); fine for line art, logos, thin geometry.
    --key-light N       transparent background via luminance keying (alpha=0
                        above N, ramp over ~22 levels). Automatically
                        flat-fields first — global keying FAILS on vignetted
                        corners otherwise (lesson learned the hard way).
                        Keyed alpha is computed on the flattened image but
                        colors are taken from the original, preserving the
                        mark's true color. For dark logos/marks on light
                        slides. Forces PNG. Typical N: 230-235 after
                        flat-fielding.

--bbox is x0,y0,x1,y1 in cleaned-image pixel coordinates. The printed <img>
tag carries the matching position/size on the target canvas (--canvas-width).

Dependencies: Pillow, numpy
"""

import argparse
import base64
import io
import sys

from typing import Optional
import numpy as np
from PIL import Image, ImageFilter


def white_balance(im: Image.Image, p: float = 88, target: float = 253) -> Image.Image:
    arr = np.asarray(im).astype(np.float32)
    for c in range(3):
        hi = np.percentile(arr[..., c], p)
        if hi > 1:
            arr[..., c] = np.clip(arr[..., c] * (target / hi), 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def flat_field(im: Image.Image, radius: Optional[int] = None) -> Image.Image:
    """Divide by a blurred background estimate -> flat, even background."""
    rgb = im.convert("RGB")
    r = radius or max(im.size) // 8
    bg = np.asarray(rgb.filter(ImageFilter.GaussianBlur(r))).astype(np.float32)
    arr = np.asarray(rgb).astype(np.float32)
    norm = np.clip(arr / np.maximum(bg, 1) * 250.0, 0, 255)
    return Image.fromarray(norm.astype(np.uint8))


def key_light(im: Image.Image, thresh: int, ramp: float = 22.0) -> Image.Image:
    """Flat-field, key alpha on flattened luminance, keep original colors."""
    orig = np.asarray(im.convert("RGB")).astype(np.float32)
    flat = np.asarray(flat_field(im)).astype(np.float32)
    lum = 0.299 * flat[..., 0] + 0.587 * flat[..., 1] + 0.114 * flat[..., 2]
    alpha = np.clip((thresh - lum) / ramp, 0, 1) * 255
    return Image.fromarray(np.dstack([orig, alpha]).astype(np.uint8)).convert("RGBA")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--bbox", required=True, help="x0,y0,x1,y1 cleaned-image px")
    ap.add_argument("--max-width", type=int, default=800)
    ap.add_argument("--canvas-width", type=int, default=1280)
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--white-balance", action="store_true")
    ap.add_argument("--flat-field", action="store_true")
    ap.add_argument("--key-light", type=int, default=0,
                    help="luminance threshold for transparency (e.g. 232)")
    args = ap.parse_args()

    try:
        x0, y0, x1, y1 = (int(v) for v in args.bbox.split(","))
    except ValueError:
        print("error: --bbox must be x0,y0,x1,y1", file=sys.stderr)
        return 1

    im = Image.open(args.image).convert("RGB")
    W, H = im.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        print("error: empty bbox after clamping", file=sys.stderr)
        return 1

    crop = im.crop((x0, y0, x1, y1))
    if crop.width > args.max_width:
        nh = round(crop.height * args.max_width / crop.width)
        crop = crop.resize((args.max_width, nh), Image.LANCZOS)

    # --key-light already calls flat_field() internally; do not --flat-field separately
    _applied_flat = False
    if args.key_light:
        crop = key_light(crop, args.key_light)
        _applied_flat = True
    elif args.flat_field:
        crop = flat_field(crop)
        _applied_flat = True
    if args.white_balance and not _applied_flat:
        crop = white_balance(crop)

    buf = io.BytesIO()
    if args.png or args.key_light:
        crop.save(buf, "PNG", optimize=True)
        mime = "image/png"
    else:
        crop.save(buf, "JPEG", quality=args.quality, optimize=True)
        mime = "image/jpeg"
    b64 = base64.b64encode(buf.getvalue()).decode()

    scale = args.canvas_width / W
    dl, dt = round(x0 * scale), round(y0 * scale)
    dw, dh = round((x1 - x0) * scale), round((y1 - y0) * scale)

    print(f"<!-- crop {x0},{y0},{x1},{y1} of {W}x{H}; {len(b64)//1024} KiB -->")
    print(f'<img style="position:absolute;left:{dl}px;top:{dt}px;'
          f'width:{dw}px;height:{dh}px" src="data:{mime};base64,{b64}" alt="">')
    return 0


if __name__ == "__main__":
    sys.exit(main())
