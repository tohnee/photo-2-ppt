# OCR integration (PP-OCRv6 / PP-StructureV3) — Stage 1.5

This skill gained an automated OCR/structure stage between **Extract** (Stage 1)
and **Inventory** (Stage 2). It replaces error-prone by-eye transcription with a
machine-read spec that carries exact text, coordinates, formula LaTeX, and table
HTML — then either assembles the slide automatically, or feeds the skill's vector
rebuild.

```
photo.jpg --extract_slide.py--> slide_clean.jpg --ocr_extract.py--> spec.json
                                                                       |
                          auto mode ------------------------------------+--------> slide.html / slide.pptx
                          (assemble_html.py / assemble_pptx.py)         |
                          vector mode (the skill) <----------------------+
                          (Claude redraws figures as inline SVG)
```

## Why PP-StructureV3 (not bare PP-OCRv6)

PP-OCRv6 is the **text layer** only — detection + recognition. It is tiny
(1.5M–34.5M params), fast (~5.2× CPU speedup vs PP-OCRv5), and beats much larger
VLMs at pure text. But it has no notion of formulas, tables, or reading order.

`PP-StructureV3` runs PP-OCRv6 underneath for text and adds layout analysis,
table-structure recognition, and formula→LaTeX, and — importantly here — exposes
**per-block coordinates** (finer than the PaddleOCR-VL series). Those coordinates
map straight onto this skill's `scale = 1280 / cleaned_width` canvas convention.

## The spec schema (the contract)

`ocr_extract.py` writes `<out>.json`. All coordinates are **cleaned-image
pixels** (same space as every measurement in Stage 2).

```jsonc
{
  "source_image": "/abs/path/slide_clean.jpg",
  "image_size": { "width": 1600, "height": 900 },
  "canvas":     { "width": 1280, "height": 720 },
  "scale": 0.8,                       // 1280 / image width
  "ocr": { "engine": "PP-StructureV3", "text_backbone": "PP-OCRv6",
           "schema_source": "parsing_res_list" },
  "blocks": [
    { "id": "b0", "type": "title",   "bbox": [x1,y1,x2,y2], "text": "...", "reading_order": 0 },
    { "id": "b1", "type": "text",    "bbox": [...], "text": "...",  "reading_order": 1 },
    { "id": "b3", "type": "formula", "bbox": [...], "latex": "\\mathcal{G}(n)\\in G", "reading_order": 3 },
    { "id": "b4", "type": "table",   "bbox": [...], "html": "<table>...</table>",     "reading_order": 4 },
    { "id": "b2", "type": "figure",  "bbox": [...], "reading_order": 2 }
  ]
}
```

`type` is the coarse class the rebuild cares about:
`title | text | caption | formula | table | figure`. The original PP-StructureV3
label is kept in `raw_label` for finer decisions.

## Two modes

### auto — hands-off, faithful, raster diagrams
`run_pipeline.py photo.jpg --mode auto --format html|pptx|both`

- text/title/caption → real, selectable, positioned text (color + size sampled).
- formula/table/figure → the **original pixels** cropped from the cleaned image
  (white-balanced) and embedded. Faithful by construction; nothing approximated.
- Recognized table HTML / formula LaTeX are kept as `data-*` attrs (searchable,
  reusable by the vector path).

This is the literal "one image in, one HTML/PPT out" closed loop. Best when you
have many slides to archive and don't need vector-editable diagrams.

### vector — highest fidelity (the skill does the rebuild)
`run_pipeline.py photo.jpg --mode spec` → stops after `spec.json` + overlay.

Then proceed with the normal skill Stages 2–4, but **the spec does Stage 2 for
you**: every text/formula/table block is already transcribed with coordinates.
Your remaining job is the part only visual reasoning can do — redraw the
`figure`-type blocks as inline SVG (the EDA architecture diagram, the GCRP
routing schematic, etc.). Open `<out>.overlay.png` to see exactly which regions
were classified as figures and need redrawing.

Rule of thumb: text/formula/table → trust the spec; figures → your call via the
vector-vs-raster decision tree (a complex schematic that the tree says to crop is
already cropped for you in auto mode).

## Running it

One-time setup (open network — sandbox allowlist blocks model hosts):
```bash
bash scripts/setup_paddle.sh          # or: bash scripts/setup_paddle.sh gpu
```

Per slide:
```bash
# full auto closed loop
python scripts/run_pipeline.py photo.jpg --out-dir out --format both --verify

# or step by step
python scripts/extract_slide.py photo.jpg --output out/slide_clean.jpg
python scripts/ocr_extract.py   out/slide_clean.jpg --out out/spec
python scripts/assemble_html.py out/spec.json --out out/slide.html
```

Force specific PP-OCRv6 text models (sizes: tiny / small / medium):
```bash
python scripts/ocr_extract.py out/slide_clean.jpg --out out/spec \
    --det-model PP-OCRv6_medium_det --rec-model PP-OCRv6_medium_rec --device gpu
```

## Model source / mirrors

First instantiation downloads weights. Pick the source via env var if HuggingFace
is slow or blocked:
```bash
export PADDLE_PDX_MODEL_SOURCE=BOS          # Baidu BOS (fast in CN)
# or HF (default) / MODELSCOPE
```
Models also live at https://huggingface.co/collections/PaddlePaddle/pp-ocrv6
and the ModelScope mirror.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: paddleocr` | not installed | `bash scripts/setup_paddle.sh` (open network) |
| Hangs / fails on first run | weight download blocked | set `PADDLE_PDX_MODEL_SOURCE`, retry on open network |
| `schema_source: unknown` warning | PP-StructureV3 result keys shifted in a point release | check printed top-level keys; extend `parse_structure_result()` in `ocr_extract.py` |
| Text blocks merged/over-split | layout analysis granularity | adjust block-level post-merge in Stage 2, or fall back to vector mode |
| Faint/wrong text color | thin antialiased glyphs sampled light | usually fine on real slides; else set color by hand in vector mode |
| Formula/table looks raster in HTML | expected in auto mode | use vector mode to render LaTeX (`data-latex`) / native `<table>` (`data-table-html-b64`) |
| Diagram topology wrong | only happens if you let auto-mode crop stand in for a redraw you wanted vectorized | switch that block to vector mode SVG |

## Files

- `scripts/setup_paddle.sh` — one-time install + model prefetch
- `scripts/ocr_extract.py` — PP-StructureV3 (PP-OCRv6) → `spec.json` + overlay
- `scripts/assemble_html.py` — spec → self-contained HTML (auto mode)
- `scripts/run_pipeline.py` — extract → ocr → assemble → verify orchestrator
- `../photo-to-pptx/scripts/assemble_pptx.py` — same spec → editable .pptx
