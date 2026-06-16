#!/usr/bin/env python3
"""
Auto-mode HTML assembler.

Turns an OCR spec (from ocr_extract.py) + the cleaned slide image into a single
self-contained HTML file, with NO LLM in the loop:

  - text / title / caption blocks  -> real, selectable, absolutely-positioned
    HTML text (color + font-size estimated from the source pixels)
  - formula / table / figure blocks -> the original pixels, cropped from the
    cleaned image and embedded as base64 (faithful; nothing to approximate)

This is the hands-off "image in, HTML out" path. It is faithful by
construction (every non-text region is the real photo crop) but the diagrams
stay raster. For resolution-independent vector SVG diagrams, use the skill's
vector path instead (see references/ocr_integration.md): same spec, but Claude
redraws figures as inline SVG.

Recognized table HTML and formula LaTeX are preserved as data-* attributes so
the output stays text-searchable and the vector path can reuse them.

Usage:
    python assemble_html.py spec.json --out slide.html
    python assemble_html.py spec.json --out slide.html --no-white-balance
"""
import argparse
import base64
import html
import io
import json
import os
import sys


def load_image(path):
    from PIL import Image
    return Image.open(path).convert("RGB")


def white_balance(crop):
    """Gray-world WB to kill projector/photo color cast on a crop."""
    from PIL import Image
    import numpy as np
    a = np.asarray(crop).astype("float32")
    means = a.reshape(-1, 3).mean(axis=0)
    # Avoid division by zero: if any channel mean is near zero, skip that channel
    # by using a large multiplier (essentially leaving it unchanged).
    g = means.mean()
    scale = np.where(means > 1, g / np.maximum(means, 1e-6), 1.0)
    a = a * scale
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def crop_datauri(img, bbox, wb=True, pad=2):
    from PIL import Image
    W, H = img.size
    x1, y1, x2, y2 = bbox
    # Check emptiness BEFORE padding — padding should extend valid crops, not fill empty ones
    if x2 <= x1 or y2 <= y1:
        return None
    x1 = max(0, x1 - pad); y1 = max(0, y1 - pad)
    x2 = min(W, x2 + pad); y2 = min(H, y2 + pad)
    crop = img.crop((x1, y1, x2, y2))
    if wb:
        try:
            crop = white_balance(crop)
        except Exception:
            pass
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def sample_text_color(img, bbox):
    """
    Sample the ink color from a text bbox. Detects whether the bbox background
    is light or dark, then samples the contrasting pixels accordingly.
    Falls back to dark (#1a1a1a) on all-error.
    """
    import numpy as np
    x1, y1, x2, y2 = bbox
    region = img.crop((x1, y1, x2, y2))
    a = np.asarray(region).reshape(-1, 3)
    if a.size == 0:
        return "#1a1a1a"
    # Median luminance of the whole region as a proxy for background brightness
    lum = a.mean(axis=1)
    median_lum = float(np.median(lum))
    # Light background: sample the darkest 20% (ink is dark)
    # Dark background: sample the brightest 20% (ink is light)
    if median_lum >= 128:
        thr = np.percentile(lum, 20)
        ink_pixels = a[lum <= thr]
    else:
        thr = np.percentile(lum, 80)
        ink_pixels = a[lum >= thr]
    if ink_pixels.size == 0:
        ink_pixels = a
    r, g, b = ink_pixels.mean(axis=0).astype(int)
    return f"#{r:02x}{g:02x}{b:02x}"


def esc(s):
    return html.escape(s or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="spec.json from ocr_extract.py")
    ap.add_argument("--out", default="slide.html")
    ap.add_argument("--no-white-balance", action="store_true")
    ap.add_argument("--title", default="Reconstructed slide")
    ap.add_argument("--lang", default=None,
                    help="HTML lang attribute, e.g. en / zh / ja (default: infer from spec or fallback to en)")
    args = ap.parse_args()

    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    except FileNotFoundError:
        print(f"Error: spec file not found: {args.spec}", file=sys.stderr)
        sys.exit(1)

    img_path = spec["source_image"]
    if not os.path.isfile(img_path):
        # spec may have been moved; try alongside the spec file
        alt = os.path.join(os.path.dirname(os.path.abspath(args.spec)),
                           os.path.basename(img_path))
        img_path = alt if os.path.isfile(alt) else img_path
    img = load_image(img_path)

    scale = spec.get("scale") or (1280.0 / spec["image_size"]["width"])
    wb = not args.no_white_balance

    els = []
    for b in spec["blocks"]:
        bb = b.get("bbox")
        if not bb:
            continue
        x = bb[0] * scale; y = bb[1] * scale
        w = (bb[2] - bb[0]) * scale; h = (bb[3] - bb[1]) * scale
        pos = f"left:{x:.1f}px;top:{y:.1f}px;width:{w:.1f}px;height:{h:.1f}px;"
        t = b["type"]

        if t in ("text", "title", "caption"):
            txt = b.get("text", "")
            if not txt.strip():
                continue
            color = sample_text_color(img, bb)
            # font-size: most of the line height is cap height; 0.72 reads well
            fs = max(8.0, h * 0.72)
            weight = "700" if t == "title" else "400"
            # let long titles/text wrap but keep single-line look when it fits
            els.append(
                f'<div class="t" style="{pos}color:{color};font-size:{fs:.1f}px;'
                f'font-weight:{weight};">{esc(txt)}</div>')
        else:
            uri = crop_datauri(img, bb, wb=wb)
            if not uri:
                continue
            data_attr = ""
            if t == "formula" and b.get("latex"):
                data_attr = f' data-latex="{esc(b["latex"])}" title="{esc(b["latex"])}"'
            elif t == "table" and b.get("html"):
                # stash recognized table HTML for the vector path / search
                tbl = base64.b64encode(b["html"].encode()).decode()
                data_attr = f' data-table-html-b64="{tbl}"'
            els.append(
                f'<img class="r {t}" style="{pos}"{data_attr} '
                f'src="{uri}" alt="{esc(b.get("text", t))}">')

    page_bg = "#ffffff"
    body = "\n      ".join(els)
    # Resolve lang: explicit --lang wins; otherwise infer from canvas size hints or default to 'en'
    lang = args.lang
    if not lang:
        canvas = spec.get("canvas", {})
        # Heuristic: CJK canvas likely implies CJK content
        if canvas.get("height", 720) / canvas.get("width", 1280) >= 0.7:
            lang = "zh"   # most CJK slides are portrait 4:3 at these dims
        else:
            lang = "en"
    _canvas_w = spec.get("canvas", {}).get("width", 1280)
    _canvas_h = spec.get("canvas", {}).get("height", 720)
    doc = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(args.title)}</title>
<style>
  :root {{ --canvas-w: {_canvas_w}px; --canvas-h: {_canvas_h}px; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#3a3a3a; display:flex; justify-content:center; padding:24px; }}
  .slide {{
    position:relative; width:var(--canvas-w); height:var(--canvas-h);
    background:{page_bg}; overflow:hidden;
    box-shadow:0 8px 40px rgba(0,0,0,.5);
    font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",
                "Noto Sans CJK SC",Roboto,Arial,sans-serif;
  }}
  .slide .t {{ position:absolute; line-height:1.05; white-space:pre-wrap;
               overflow:hidden; display:flex; align-items:center; }}
  .slide .r {{ position:absolute; object-fit:contain; }}
  /* selectable text sits above raster crops */
  .slide .t {{ z-index:2; }}
  .slide .r {{ z-index:1; }}
</style>
</head>
<body>
  <div class="slide">
      {body}
  </div>
</body>
</html>
"""
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    n_text = sum(1 for b in spec["blocks"] if b["type"] in ("text", "title", "caption"))
    n_raster = len(spec["blocks"]) - n_text
    print(f"\u2713 Wrote {args.out}  ({n_text} text, {n_raster} raster blocks)")


if __name__ == "__main__":
    main()
