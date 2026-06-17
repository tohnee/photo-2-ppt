#!/usr/bin/env python3
"""
Stage 1.5 — OCR / structure extraction.

Runs PaddleOCR PP-StructureV3 (text layer powered by PP-OCRv5) on a *cleaned*
slide image (the output of extract_slide.py) and emits a structured spec:

    <out>.json    a normalized layout spec (text + bbox + LaTeX + table HTML)
    <out>.overlay.png   the cleaned image with detected blocks drawn on top

The spec is the contract consumed by assemble_html.py / assemble_pptx.py
(auto mode) and by the skill's Stage 2/3 rebuild (vector mode). Coordinates are
in *cleaned-image pixels*, matching the skill's `scale = 1280 / cleaned_width`
convention exactly — no extra transform needed downstream.

Usage:
    python ocr_extract.py slide_clean.jpg --out spec
    python ocr_extract.py slide_clean.jpg --out spec --device gpu
    python ocr_extract.py slide_clean.jpg --out spec \
        --det-model PP-OCRv5_server_det --rec-model PP-OCRv5_server_rec

Why PP-StructureV3 and not bare PP-OCRv5:
    PP-OCRv5 is detection+recognition only — text strings + boxes, no formulas,
    tables, or reading order. PP-StructureV3 orchestrates PP-OCRv5 for the text
    layer and adds layout analysis, table-structure recognition, and formula
    recognition (LaTeX), and exposes fine-grained per-block coordinates. That
    coordinate detail is exactly what a faithful slide rebuild needs.

NOTE on first run: model weights download from HuggingFace / the PaddlePaddle
model server. Run `setup_paddle.sh` once in an environment with open network
access (the Claude sandbox allowlist usually blocks these hosts).
"""
import argparse
import json
import os
import sys
from pathlib import Path


# Map PP-StructureV3 block labels -> the spec's coarse types.
# (PP-StructureV3 emits labels like 'text', 'paragraph_title', 'doc_title',
#  'table', 'formula', 'figure', 'image', 'chart', 'seal', 'header', 'footer',
#  'figure_title', 'table_title', 'reference', 'algorithm', ... )
LABEL_MAP = {
    "doc_title": "title",
    "paragraph_title": "title",
    "title": "title",
    "abstract": "text",
    "text": "text",
    "content": "text",
    "reference": "text",
    "footer": "text",
    "header": "text",
    "footnote": "text",
    "figure_title": "caption",
    "table_title": "caption",
    "chart_title": "caption",
    "caption": "caption",
    "formula": "formula",
    "table": "table",
    "figure": "figure",
    "image": "figure",
    "chart": "figure",
    "seal": "figure",
    "algorithm": "figure",
}


def _to_type(label: str) -> str:
    if not label:
        return "text"
    key = label.strip().lower()
    if key in LABEL_MAP:
        return LABEL_MAP[key]
    # Unknown labels are explicitly marked so downstream can handle them.
    # We no longer guess — "fig"/"image"/"chart" substrings are unreliable.
    return "unknown"


def _norm_bbox(b):
    """Accept [x1,y1,x2,y2] or polygon [[x,y],...] -> [x1,y1,x2,y2] ints."""
    if b is None:
        return None
    flat = []
    if isinstance(b[0], (list, tuple)):
        xs = [p[0] for p in b]
        ys = [p[1] for p in b]
        flat = [min(xs), min(ys), max(xs), max(ys)]
    else:
        flat = list(b[:4])
    return [int(round(v)) for v in flat]


def parse_structure_result(res_json: dict):
    """Defensively pull a flat block list out of a PP-StructureV3 result dict.

    Schema has shifted across 3.x point releases, so we try several known
    shapes in priority order and fall back to raw OCR if needed.
    """
    root = res_json.get("res", res_json) if isinstance(res_json, dict) else {}
    blocks = []

    # 1) Preferred: parsing_res_list (has label + content + bbox per block)
    plist = root.get("parsing_res_list")
    if plist:
        for i, it in enumerate(plist):
            label = (it.get("block_label") or it.get("label") or "text")
            bbox = _norm_bbox(it.get("block_bbox") or it.get("bbox"))
            content = it.get("block_content")
            if content is None:
                content = it.get("content", "")
            t = _to_type(label)
            blk = {"id": f"b{i}", "type": t, "raw_label": label, "bbox": bbox,
                   "reading_order": i}
            if t == "formula":
                blk["latex"] = str(content).strip()
                blk["text"] = str(content).strip()
            elif t == "table":
                blk["html"] = str(content)
            else:
                blk["text"] = str(content).strip()
            blocks.append(blk)
        return blocks, "parsing_res_list"

    # 2) Fallback: overall_ocr_res (plain text lines, no structure)
    ocr = root.get("overall_ocr_res") or root.get("ocr_res") or {}
    texts = ocr.get("rec_texts") or ocr.get("rec_text")
    boxes = ocr.get("rec_boxes") or ocr.get("rec_polys") or ocr.get("dt_polys")
    if texts and boxes:
        for i, (tx, bx) in enumerate(zip(texts, boxes)):
            blocks.append({"id": f"b{i}", "type": "text", "raw_label": "text",
                           "bbox": _norm_bbox(bx), "text": str(tx).strip(),
                           "reading_order": i})
        return blocks, "overall_ocr_res"

    # Nothing matched — surface diagnostic info before raising
    print("ERROR: PP-StructureV3 returned an unrecognized result schema.",
          file=sys.stderr)
    print("  Top-level keys:", list(root.keys()), file=sys.stderr)
    raise RuntimeError(
        f"Unknown PP-StructureV3 schema. Top keys: {list(root.keys())}. "
        "Check ocr_extract.py parse_structure_result() and report this output."
    )


def build_structure(device, det_model, rec_model, lang):
    """Build a PP-StructureV3 pipeline, preferring local weights when
    ``PH2H_MODELS_DIR`` is set. Returns a PPStructureV3 instance.

    Model resolution priority for text det/rec:
        1. If ``--det-model`` / ``--rec-model`` names a directory present in
           ``$PH2H_MODELS_DIR``, use that directory (offline, no download).
        2. Else if ``$PH2H_MODELS_DIR`` contains a PP-OCRv6 variant, use it
           (v6 is opt-in; users who downloaded v6 weights get them by default).
        3. Else if ``$PH2H_MODELS_DIR`` contains PP-OCRv5_server, use it.
        4. Else fall back to PaddleOCR's online downloader with the
           ``*_model_name`` kwarg (requires network on first use).
    """
    from paddleocr import PPStructureV3
    kwargs: dict = {}
    if device:
        kwargs["device"] = device

    # ---- local-weights mode: resolve model directories explicitly -----------
    local_root = os.environ.get("PH2H_MODELS_DIR")
    if local_root and os.path.isdir(local_root):
        resolved = _resolve_local_models(Path(local_root), det_model, rec_model)
        if not resolved:
            print(
                f"WARNING: PH2H_MODELS_DIR={local_root} exists but contains no "
                "recognized model directories. Falling back to PaddleOCR's "
                "online downloader.",
                file=sys.stderr,
            )
        else:
            for key, path in resolved.items():
                kwargs[key] = str(path)
            print(f"[ocr] using local weights from {local_root} "
                  f"({len(resolved)} model dirs)", file=sys.stderr)

            # If user requested a specific det/rec model via CLI but it is NOT
            # in the local bundle, pass the name through so PaddleOCR downloads
            # it on first use (instead of silently using the bundled v5).
            if det_model and "text_detection_model_dir" not in resolved:
                kwargs["text_detection_model_name"] = det_model
                print(f"[ocr] det model '{det_model}' not in local bundle; "
                      "will download on first use (needs network).",
                      file=sys.stderr)
            if rec_model and "text_recognition_model_dir" not in resolved:
                kwargs["text_recognition_model_name"] = rec_model
                print(f"[ocr] rec model '{rec_model}' not in local bundle; "
                      "will download on first use (needs network).",
                      file=sys.stderr)
    else:
        # ---- online mode: pass user picks as *_model_name ------------------
        if det_model:
            kwargs["text_detection_model_name"] = det_model
        if rec_model:
            kwargs["text_recognition_model_name"] = rec_model

    if lang:
        kwargs["lang"] = lang

    # Keep doc-orientation / unwarp off: input is already perspective-corrected
    # by extract_slide.py, and re-warping a slide tends to hurt.
    kwargs.setdefault("use_doc_orientation_classify", False)
    kwargs.setdefault("use_doc_unwarping", False)
    return PPStructureV3(**kwargs)


def _resolve_local_models(root: "Path", det_model: str = None,
                          rec_model: str = None) -> dict:
    """Walk ``root`` looking for PaddleOCR 3.7-compatible model directories.

    The ``root`` directory is expected to contain one sub-directory per
    PaddleOCR model name, mirroring the layout of ``paddlex``'s official
    model cache (``$PADDLE_PDX_CACHE_HOME/official_models/``)::

        <root>/
            PP-OCRv5_server_det/          # default text detection (v5)
                inference.json  inference.pdiparams  ...
            PP-OCRv5_server_rec/          # default text recognition (v5)
                inference.json  inference.pdiparams  ...
            PP-OCRv6_medium_det/          # optional v6 text detection
                inference.json  inference.pdiparams  ...
            PP-OCRv6_medium_rec/          # optional v6 text recognition
                inference.json  inference.pdiparams  ...
            PP-DocLayout_plus-L/
                ...
            PP-DocBlockLayout/
                ...
            SLANet_plus/
                ...
            SLANeXt_wired/
                ...
            RT-DETR-L_wired_table_cell_det/
                ...
            RT-DETR-L_wireless_table_cell_det/
                ...
            PP-FormulaNet_plus-L/
                ...
            PP-LCNet_x1_0_textline_ori/
                ...
            PP-LCNet_x1_0_table_cls/
                ...

    For text_detection and text_recognition, both PP-OCRv5 (server/mobile)
    and PP-OCRv6 (tiny/small/medium) directories are recognized. Priority
    for each kwarg (first match wins):

        1. CLI-specified model name (``--det-model`` / ``--rec-model``)
        2. PP-OCRv6 variants (medium > small > tiny) — newer, opt-in
        3. PP-OCRv5_server (the PP-StructureV3 default)
        4. PP-OCRv5_mobile (fallback)

    Returns a dict mapping PaddleOCR ``*_model_dir`` kwarg to a path string.
    Missing models are simply omitted from the dict.
    """
    # Map kwarg -> ordered list of candidate model directory names.
    # For text det/rec, CLI override comes first, then v6 (opt-in), then
    # v5_server (PP-StructureV3 default), then v5_mobile.
    v6_det_candidates = ["PP-OCRv6_medium_det", "PP-OCRv6_small_det",
                         "PP-OCRv6_tiny_det"]
    v6_rec_candidates = ["PP-OCRv6_medium_rec", "PP-OCRv6_small_rec",
                         "PP-OCRv6_tiny_rec"]

    det_candidates = []
    if det_model:
        det_candidates.append(det_model)
    det_candidates.extend(v6_det_candidates)
    det_candidates.extend(["PP-OCRv5_server_det", "PP-OCRv5_mobile_det"])

    rec_candidates = []
    if rec_model:
        rec_candidates.append(rec_model)
    rec_candidates.extend(v6_rec_candidates)
    rec_candidates.extend(["PP-OCRv5_server_rec", "PP-OCRv5_mobile_rec"])

    kwarg_to_candidates = {
        "text_detection_model_dir": det_candidates,
        "text_recognition_model_dir": rec_candidates,
        "layout_detection_model_dir": ["PP-DocLayout_plus-L"],
        "region_detection_model_dir": ["PP-DocBlockLayout"],
        "wireless_table_structure_recognition_model_dir": ["SLANet_plus"],
        "wired_table_structure_recognition_model_dir": ["SLANeXt_wired"],
        "formula_recognition_model_dir": ["PP-FormulaNet_plus-L"],
        "textline_orientation_model_dir": ["PP-LCNet_x1_0_textline_ori"],
        "table_classification_model_dir": ["PP-LCNet_x1_0_table_cls"],
        "wired_table_cells_detection_model_dir": ["RT-DETR-L_wired_table_cell_det"],
        "wireless_table_cells_detection_model_dir": ["RT-DETR-L_wireless_table_cell_det"],
    }

    out: dict = {}
    for kwarg, candidates in kwarg_to_candidates.items():
        for model_name in candidates:
            if not model_name:
                continue
            candidate = root / model_name
            if not candidate.is_dir():
                continue
            # PaddleOCR 3.7+ ships models as `inference.json` (structure) +
            # `inference.pdiparams` (weights). Legacy 2.x used
            # `inference.pdmodel` + `inference.pdiparams`. Accept either.
            has_weights = (candidate / "inference.pdiparams").is_file()
            has_structure = (candidate / "inference.json").is_file() or \
                            (candidate / "inference.pdmodel").is_file()
            if has_weights and has_structure:
                out[kwarg] = str(candidate)
                break  # first match wins (highest priority)
    return out


def draw_overlay(image_path, blocks, out_path):
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return
    colors = {"title": (200, 30, 120), "text": (40, 120, 220),
              "formula": (30, 170, 30), "table": (0, 140, 200),
              "figure": (160, 60, 200), "caption": (120, 120, 120)}
    for b in blocks:
        bb = b.get("bbox")
        if not bb:
            continue
        c = colors.get(b["type"], (80, 80, 80))
        cv2.rectangle(img, (bb[0], bb[1]), (bb[2], bb[3]), c, 2)
        cv2.putText(img, f'{b["id"]}:{b["type"]}', (bb[0] + 2, max(bb[1] - 4, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)
    cv2.imwrite(out_path, img)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="cleaned slide image (output of extract_slide.py)")
    ap.add_argument("--out", default="spec", help="output prefix (writes <out>.json, <out>.overlay.png)")
    ap.add_argument("--device", default=None, help="cpu | gpu | gpu:0  (default: paddle auto)")
    ap.add_argument("--det-model", default=None,
                    help="force text detection model, e.g. PP-OCRv5_server_det")
    ap.add_argument("--rec-model", default=None,
                    help="force text recognition model, e.g. PP-OCRv5_server_rec")
    ap.add_argument("--lang", default=None, help="recognition language hint (e.g. ch, en)")
    ap.add_argument("--no-overlay", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.image):
        print(f"Error: image not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    from PIL import Image
    with Image.open(args.image) as im:
        W, H = im.size

    try:
        pipeline = build_structure(args.device, args.det_model, args.rec_model, args.lang)
    except ImportError:
        print("Error: paddleocr is not installed. Run setup_paddle.sh first "
              "(needs open network for model download).", file=sys.stderr)
        sys.exit(2)

    print(f"Running PP-StructureV3 on {args.image} ({W}x{H}) ...", file=sys.stderr)
    import time
    t0 = time.time()
    results = pipeline.predict(args.image)
    print(f"  PP-StructureV3 done in {time.time() - t0:.1f}s.", file=sys.stderr)

    blocks, source = [], "none"
    try:
        for res in results:                       # usually a single-page result
            rj = res.json if hasattr(res, "json") else res
            bl, src = parse_structure_result(rj)
            blocks.extend(bl); source = src
    except RuntimeError:
        print("Schema parse failed — saving raw result for debugging.", file=sys.stderr)
        try:
            import pprint
            raw = results[0].json if hasattr(results[0], "json") else results[0]
            pprint.pprint(raw, stream=sys.stderr)
        except Exception:
            pass
        raise

    # renumber reading order across all results
    for i, b in enumerate(blocks):
        b["reading_order"] = i

    scale = 1280.0 / W if W else 1.0
    # Canvas matches the detected image ratio; 1280 is canonical width for backward compat.
    canvas_w, canvas_h = 1280, round(720 * (H / W)) if W else 720
    spec = {
        "source_image": os.path.abspath(args.image),
        "image_size": {"width": W, "height": H},
        "canvas": {"width": canvas_w, "height": canvas_h},
        "scale": round(scale, 6),
        "ocr": {"engine": "PP-StructureV3", "text_backbone": "PP-OCRv5",
                "schema_source": source,
                "det_model": args.det_model, "rec_model": args.rec_model},
        "blocks": blocks,
    }

    json_path = f"{args.out}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print(f"\u2713 Wrote {json_path}  ({len(blocks)} blocks, source={source})")

    if not args.no_overlay:
        overlay_path = f"{args.out}.overlay.png"
        draw_overlay(args.image, blocks, overlay_path)
        print(f"\u2713 Wrote {overlay_path}")


if __name__ == "__main__":
    main()
