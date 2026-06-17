#!/usr/bin/env python3
"""
Auto-mode PPTX assembler.

Turns an OCR spec (from ocr_extract.py) + the cleaned slide image into an
editable PowerPoint file, with NO LLM in the loop:

  - text / title / caption blocks  -> native PPTX TextBox (editable text,
    position/size/font-size/color preserved from the source pixels)
  - table blocks (with parseable HTML) -> native PPTX Table
  - table blocks (unparseable) / formula / figure blocks -> the original
    pixels, cropped from the cleaned image and embedded as pictures

This is the hands-off "image in, PPTX out" path. It is faithful by
construction (every non-text region is the real photo crop) and produces
fully editable text layers. For resolution-independent vector diagrams,
use the skill's vector path instead.

Offline design:
  - No LaTeX rendering (would need network/fonts); formulas are cropped.
  - No web fonts; uses only fonts bundled with PowerPoint.
  - Image crops are embedded as PNG bytes (no external file refs).

Usage:
    python assemble_pptx.py spec.json --out slide.pptx
    python assemble_pptx.py spec.json --out slide.pptx --no-white-balance
"""
import argparse
import base64
import io
import json
import os
import re
import sys
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Image helpers (shared logic with assemble_html.py, kept independent for
# offline single-file operation)
# ---------------------------------------------------------------------------

def load_image(path):
    from PIL import Image
    return Image.open(path).convert("RGB")


def white_balance(crop):
    """Gray-world WB to kill projector/photo color cast on a crop."""
    from PIL import Image
    import numpy as np
    a = np.asarray(crop).astype("float32")
    means = a.reshape(-1, 3).mean(axis=0)
    g = means.mean()
    scale = np.where(means > 1, g / np.maximum(means, 1e-6), 1.0)
    a = a * scale
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def crop_to_bytes(img, bbox, wb=True, pad=2):
    """Crop a bbox from img, apply white balance, return PNG bytes."""
    from PIL import Image
    W, H = img.size
    x1, y1, x2, y2 = bbox
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
    return buf.getvalue()


def sample_text_color(img, bbox):
    """Sample ink color from a text bbox; returns RGB tuple (r,g,b).

    Robust to thin-on-bright-background text: a percentile threshold
    collapses to the dominant background value when >80% of the bbox
    is background. Instead we threshold at 70% of the median luminance
    (light bg) or median + 30% of the headroom (dark bg), then fall
    back to sorting and taking the most extreme 5% if the threshold
    matches too few pixels.
    """
    import numpy as np
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return (26, 26, 26)
    region = img.crop((x1, y1, x2, y2))
    a = np.asarray(region).reshape(-1, 3)
    if a.size == 0:
        return (26, 26, 26)
    lum = a.mean(axis=1)
    median_lum = float(np.median(lum))
    n = len(lum)
    min_ink = max(1, n // 100)  # require at least 1% of pixels

    if median_lum >= 128:
        # light background -> ink is dark
        thr = median_lum * 0.7
        ink_pixels = a[lum <= thr]
        if ink_pixels.size < min_ink:
            n_ink = max(1, n // 20)  # darkest 5%
            order = np.argsort(lum)
            ink_pixels = a[order[:n_ink]]
    else:
        # dark background -> ink is light
        thr = median_lum + (255 - median_lum) * 0.3
        ink_pixels = a[lum >= thr]
        if ink_pixels.size < min_ink:
            n_ink = max(1, n // 20)  # lightest 5%
            order = np.argsort(lum)
            ink_pixels = a[order[-n_ink:]]

    r, g, b = ink_pixels.mean(axis=0).astype(int)
    return (int(r), int(g), int(b))


# ---------------------------------------------------------------------------
# Table HTML parsing — best-effort extraction into a 2D cell grid.
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(
    r"<(td|th)[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)


def parse_table_html(html_str: str) -> Optional[List[List[str]]]:
    """Parse a simple HTML table into a 2D list of cell texts.

    Returns None if the string is not a parseable table. Handles colspan/
    rowspan poorly (ignores them) — this is a best-effort path; the crop
    fallback covers anything we can't parse.
    """
    if not html_str or "<table" not in html_str.lower():
        return None
    rows: List[List[str]] = []
    for row_match in _ROW_RE.finditer(html_str):
        row_cells: List[str] = []
        row_content = row_match.group(1)
        for cell_match in _CELL_RE.finditer(row_content):
            cell_html = cell_match.group(2)
            text = _TAG_RE.sub("", cell_html).strip()
            # collapse whitespace
            text = re.sub(r"\s+", " ", text)
            row_cells.append(text)
        if row_cells:
            rows.append(row_cells)
    if not rows:
        return None
    # normalize column count to the widest row
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")
    return rows


# ---------------------------------------------------------------------------
# PPTX building
# ---------------------------------------------------------------------------

# PowerPoint EMU per inch / per point
_EMU_PER_INCH = 914400
_EMU_PER_PT = 12700
# Default slide size: 16:9 widescreen (13.333" x 7.5")
_DEFAULT_SLIDE_W_EMU = int(13.333 * _EMU_PER_INCH)
_DEFAULT_SLIDE_H_EMU = int(7.5 * _EMU_PER_INCH)


def _px_to_emu(px: float, canvas_px: int, slide_emu: int) -> int:
    """Map a pixel coordinate on the canvas to EMU on the slide."""
    if canvas_px <= 0:
        return 0
    return int(round(px * slide_emu / canvas_px))


def _pt_to_emu(pt: float) -> int:
    return int(round(pt * _EMU_PER_PT))


def _rgb_to_pptx(rgb: Tuple[int, int, int]):
    """Convert (r,g,b) to a python-pptx RGBColor."""
    from pptx.dml.color import RGBColor
    return RGBColor(*rgb)


def _add_text_box(slide, spec, block, img, slide_w_emu, slide_h_emu):
    """Add a text box for a text/title/caption block."""
    from pptx.util import Pt, Emu
    from pptx.enum.text import PP_ALIGN

    bb = block["bbox"]
    canvas = spec.get("canvas", {})
    canvas_w = canvas.get("width", 1280)
    canvas_h = canvas.get("height", 720)

    left = _px_to_emu(bb[0], canvas_w, slide_w_emu)
    top = _px_to_emu(bb[1], canvas_h, slide_h_emu)
    width = _px_to_emu(bb[2] - bb[0], canvas_w, slide_w_emu)
    height = _px_to_emu(bb[3] - bb[1], canvas_h, slide_h_emu)

    # guard against zero-size boxes
    width = max(width, _pt_to_emu(1))
    height = max(height, _pt_to_emu(1))

    txBox = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    # disable autosize to preserve layout fidelity
    tf.auto_size = None

    text = block.get("text", "") or ""
    # split on newlines to preserve line breaks
    lines = text.split("\n") if text else [""]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = line

        # font size: derive from bbox height. 0.72 reads well for cap height.
        font_pt = max(6.0, (bb[3] - bb[1]) * 0.72 * spec.get("scale", 1.0))
        # clamp to a sane range
        font_pt = min(max(font_pt, 6.0), 200.0)
        run.font.size = Pt(font_pt)

        # weight
        if block["type"] == "title":
            run.font.bold = True

        # color — sample from the source image
        try:
            rgb = sample_text_color(img, bb)
            run.font.color.rgb = _rgb_to_pptx(rgb)
        except Exception:
            pass

    return txBox


def _add_table(slide, spec, block, img, slide_w_emu, slide_h_emu, wb):
    """Add a native PPT table from parseable HTML; return True on success."""
    rows = parse_table_html(block.get("html", ""))
    if not rows:
        return False

    from pptx.util import Pt, Emu, Inches

    bb = block["bbox"]
    canvas = spec.get("canvas", {})
    canvas_w = canvas.get("width", 1280)
    canvas_h = canvas.get("height", 720)

    left = _px_to_emu(bb[0], canvas_w, slide_w_emu)
    top = _px_to_emu(bb[1], canvas_h, slide_h_emu)
    width = max(_px_to_emu(bb[2] - bb[0], canvas_w, slide_w_emu), _pt_to_emu(1))
    height = max(_px_to_emu(bb[3] - bb[1], canvas_h, slide_h_emu), _pt_to_emu(1))

    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    table_shape = slide.shapes.add_table(n_rows, n_cols,
                                         Emu(left), Emu(top),
                                         Emu(width), Emu(height))
    table = table_shape.table

    # Sample ink color once from the whole table bbox; cheaper than
    # per-cell sampling and tables usually have uniform ink color.
    try:
        ink_rgb = sample_text_color(img, bb)
    except Exception:
        ink_rgb = (26, 26, 26)

    # populate cells
    row_h_px = (bb[3] - bb[1]) / max(n_rows, 1)
    for ri, row in enumerate(rows):
        for ci, cell_text in enumerate(row):
            if ci >= n_cols:
                break
            cell = table.cell(ri, ci)
            cell.text = cell_text
            # font size: derive from row height (0.6 factor accounts for
            # cell padding and cap-height vs full-line-height ratio)
            row_h_pt = max(8.0, row_h_px * 0.6)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(min(max(row_h_pt, 6.0), 60.0))
                    try:
                        run.font.color.rgb = _rgb_to_pptx(ink_rgb)
                    except Exception:
                        pass

    return True


def _add_picture_crop(slide, spec, block, img, slide_w_emu, slide_h_emu, wb):
    """Embed a cropped region as a picture on the slide."""
    from pptx.util import Emu

    bb = block["bbox"]
    canvas = spec.get("canvas", {})
    canvas_w = canvas.get("width", 1280)
    canvas_h = canvas.get("height", 720)

    left = _px_to_emu(bb[0], canvas_w, slide_w_emu)
    top = _px_to_emu(bb[1], canvas_h, slide_h_emu)
    width = max(_px_to_emu(bb[2] - bb[0], canvas_w, slide_w_emu), _pt_to_emu(1))
    height = max(_px_to_emu(bb[3] - bb[1], canvas_h, slide_h_emu), _pt_to_emu(1))

    png_bytes = crop_to_bytes(img, bb, wb=wb)
    if not png_bytes:
        return None

    stream = io.BytesIO(png_bytes)
    pic = slide.shapes.add_picture(stream, Emu(left), Emu(top),
                                   Emu(width), Emu(height))
    return pic


def build_pptx(spec, img, out_path: str, wb: bool = True):
    """Build a PPTX file from the spec + cleaned image."""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    # set slide size to match the spec canvas aspect ratio
    canvas = spec.get("canvas", {})
    canvas_w = canvas.get("width", 1280)
    canvas_h = canvas.get("height", 720)

    # use 13.333" x 7.5" (16:9) as the default, but adjust to match the
    # spec's aspect ratio so coordinates map 1:1
    if canvas_w > 0 and canvas_h > 0:
        aspect = canvas_w / canvas_h
        slide_w_in = 13.333
        slide_h_in = slide_w_in / aspect
        # clamp to reasonable bounds
        slide_h_in = max(5.0, min(slide_h_in, 12.0))
        prs.slide_width = Inches(slide_w_in)
        prs.slide_height = Inches(slide_h_in)

    slide_w_emu = prs.slide_width
    slide_h_emu = prs.slide_height

    # use a blank layout (index 6 in the default template is usually blank)
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # set white background
    from pptx.dml.color import RGBColor
    from pptx.oxml.ns import qn
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    n_text = n_table = n_picture = 0
    for block in spec.get("blocks", []):
        bb = block.get("bbox")
        if not bb:
            continue
        t = block.get("type", "text")

        if t in ("text", "title", "caption"):
            txt = block.get("text", "") or ""
            if not txt.strip():
                continue
            _add_text_box(slide, spec, block, img, slide_w_emu, slide_h_emu)
            n_text += 1

        elif t == "table":
            # try native table first; fall back to crop
            if _add_table(slide, spec, block, img, slide_w_emu, slide_h_emu, wb):
                n_table += 1
            else:
                _add_picture_crop(slide, spec, block, img,
                                  slide_w_emu, slide_h_emu, wb)
                n_picture += 1

        else:
            # formula, figure, unknown -> picture crop
            _add_picture_crop(slide, spec, block, img,
                              slide_w_emu, slide_h_emu, wb)
            n_picture += 1

    prs.save(out_path)
    return n_text, n_table, n_picture


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("spec", help="spec.json from ocr_extract.py")
    ap.add_argument("--out", default="slide.pptx")
    ap.add_argument("--no-white-balance", action="store_true")
    ap.add_argument("--title", default="Reconstructed slide",
                    help="presentation title (metadata only)")
    args = ap.parse_args()

    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    except FileNotFoundError:
        print(f"Error: spec file not found: {args.spec}", file=sys.stderr)
        sys.exit(1)

    img_path = spec["source_image"]
    if not os.path.isfile(img_path):
        alt = os.path.join(os.path.dirname(os.path.abspath(args.spec)),
                           os.path.basename(img_path))
        img_path = alt if os.path.isfile(alt) else img_path
    img = load_image(img_path)

    wb = not args.no_white_balance
    try:
        n_text, n_table, n_picture = build_pptx(spec, img, args.out, wb=wb)
    except ImportError as e:
        print(f"Error: python-pptx is not installed ({e}). "
              "Run: pip install python-pptx", file=sys.stderr)
        sys.exit(2)

    # set presentation core properties (title metadata)
    try:
        from pptx import Presentation
        prs = Presentation(args.out)
        cp = prs.core_properties
        cp.title = args.title
        prs.save(args.out)
    except Exception:
        pass

    print(f"\u2713 Wrote {args.out}  "
          f"({n_text} text, {n_table} table, {n_picture} picture blocks)")


if __name__ == "__main__":
    main()
