---
name: photo-to-html
description: "Reconstruct a presentation slide from a photo as a pixel-faithful, self-contained HTML file (vector text + inline SVG diagrams + optional embedded raster crops). Use this skill whenever a user uploads a photo of a slide (projector screen, conference TV, monitor, PDF screenshot) and wants a high-fidelity / lossless / archival reconstruction in HTML — including phrasing like '像素级重建', '高精度还原', 'HTML无损保存', 'rebuild this slide as HTML', 'vectorize this slide photo', or 'archive this conference slide'. Also use when the user wants a web-viewable, zoomable, text-searchable version of a slide rather than an editable .pptx (for .pptx output, use photo-to-pptx instead; the extraction and analysis stages are shared). Handles perspective correction, color sampling, math notation, technical diagram redraw as SVG, and screenshot-based verification."
license: Proprietary
---

# Photo-to-HTML Slide Reconstruction

Turn a photograph of a slide into a **single self-contained HTML file** that reproduces the slide at near-pixel fidelity. Compared to the sibling `photo-to-pptx` skill, HTML output is the *archival/lossless* path: text is real selectable text, diagrams are resolution-independent inline SVG, and the file renders identically in any browser with zero dependencies.

**When to choose HTML over PPTX**: user says 无损/像素级/高精度/archive/web view, or the slide contains math notation, dense technical diagrams, or fine geometry that PowerPoint primitives reproduce poorly. When the user wants to *edit* the deck afterwards, prefer `photo-to-pptx`.

## The pipeline at a glance

1. **Extract** — perspective-correct the slide out of the photo (`scripts/extract_slide.py`)
1.5. **OCR / structure** — machine-read text, coordinates, formula LaTeX, table HTML with PP-StructureV3 (text layer = **PP-OCRv5**) → `spec.json` (`scripts/ocr_extract.py`)
2. **Inventory** — enumerate every element: text (verbatim), diagrams, icons, colors, coordinates. *The spec does most of this for you;* your remaining job is the visual reasoning OCR can't do — classifying and redrawing figures.
3. **Rebuild** — one fixed-canvas HTML file per slide; vector first, raster crop only as fallback
4. **Verify** — headless-Chromium screenshot, compare side-by-side with the original, fix, repeat

Stages 1–2 are identical in spirit to `photo-to-pptx` — if that skill is installed, its `references/extraction_edge_cases.md` and `references/svg_icon_library.md` apply here verbatim.

## Two ways to run it

**Auto (closed loop) — "one image in, one HTML/PPT out", no LLM in the loop.** Stage 1.5 reads the slide; the assembler positions selectable text and embeds every non-text region as a faithful, white-balanced photo crop. Best for **batch archival** of many conference slides where you don't need vector-editable diagrams.

```bash
# First-time setup (downloads ~1.7 GB of PP-StructureV3 model weights into models/):
bash scripts/setup_paddle.sh

# Then run the pipeline:
python scripts/run_pipeline.py photo.jpg --out-dir out --format html   # html | pptx | both
```

### Offline model bundle

The `setup_paddle.sh` script pre-downloads all PPStructureV3 sub-models
(PP-OCRv5, PP-DocLayout, PP-FormulaNet, SLANeXt, etc.) into
`photo-to-html/models/` (~1.7 GB). Once present, the OCR stage runs 100%
offline — no network access needed.

**Using the bundled models:**

```bash
export PH2H_MODELS_DIR=$(pwd)/photo-to-html/models
python scripts/ocr_extract.py slide_clean.jpg --out slide/spec
```

**Verifying integrity:**

```bash
python scripts/download_paddle_models.py --verify models/
# -> verify: OK — 11 model directories, all checksums match.
```

**Re-downloading from scratch (e.g., after paddleocr upgrade):**

```bash
bash scripts/setup_paddle.sh
# or manually:
python scripts/download_paddle_models.py --out-dir models/
```

Detailed offline distribution guide: [references/offline_model_distribution.md](references/offline_model_distribution.md)

This is the path to reach for first when the request is "just archive these slides faithfully." It is faithful **by construction** — non-text regions are the real pixels — but diagrams stay raster.

**Vector (highest fidelity) — the spec feeds the manual rebuild below.** Stop after the spec, then redraw `figure`-type blocks as resolution-independent inline SVG (Stages 2–4). Reach for this when a slide's *structure is the content* (the EDA architecture diagram, the GCRP routing schematic) and you want crisp, zoomable, editable vector output.

```bash
python scripts/run_pipeline.py photo.jpg --out-dir out --mode spec     # -> out/spec.json + out/spec.overlay.png
```

Then continue with Stages 2–4: text/formulas/tables are pre-transcribed with coordinates in the spec; open `spec.overlay.png` to see which regions were classed as figures and need an SVG redraw. **Mixed is normal and best**: trust the spec for text/formula/table, redraw the few figures that matter, let auto-mode crops stand in for irregular instance-dense figures the vector-vs-raster tree says to crop anyway.

Full details, the spec schema, model mirrors (BOS/HF/ModelScope), and troubleshooting live in `references/ocr_integration.md`.

---

## Fully automated benchmark mode (PP-OCRv6 vs MinerU2.5-Pro)

This skill is designed to run without human intervention. For current-model
comparisons, use the benchmark setup and runner instead of hand-editing outputs:

```bash
# 1) Install runtime packages and warm/download model caches. This installs the
#    Python libraries, then downloads model weights into the configured cache so
#    first-run network time is not counted in benchmark latency.
bash scripts/setup_benchmark.sh cpu
# GPU users can run: PH2H_MINERU_BACKEND=vllm bash scripts/setup_benchmark.sh gpu

# 2) Run both chains on one image or a directory of images.
python scripts/run_benchmark.py data/slides --out-dir benchmark_out

# 3) Optional supervised evaluation with ground-truth text and/or clean renders.
python scripts/run_benchmark.py data/photos \
  --reference-text-dir data/gt_text \
  --reference-image-dir data/gt_images \
  --out-dir benchmark_out
```

The runner executes the same deterministic pre-processing for both backends:
`extract_slide.py` first writes `slide_clean.jpg`; the Paddle chain then runs
PP-OCRv6 through `run_pipeline.py` and renders HTML for visual metrics, while
the MinerU2.5-Pro chain writes Markdown plus a normalized content spec via
`scripts/mineru_extract.py`. `scripts/evaluate_reconstruction.py` records block
counts, text similarity/edit distance when ground truth is available, and image
MSE/MAE/PSNR when a rendered image and reference image are available.

Important benchmarking rule: `pip install` installs code, not the large model
weights. `scripts/download_benchmark_models.py` intentionally warms the
PP-OCRv6 and MinerU2.5-Pro caches before evaluation so the benchmark is
repeatable, offline-capable after warmup, and not polluted by first-use download
latency. Pin `HF_HOME`/`TRANSFORMERS_CACHE` in CI or Docker for fully
reproducible runs.

---

## Stage 1: Extract

```bash
python scripts/extract_slide.py <photo.jpg> --output slide_clean.jpg
```

Detects the bright screen, 4-point perspective transform, CLAHE contrast recovery, forces 16:9. View the result before proceeding — a skewed or cropped extraction poisons every later measurement.

---

## Stage 1.5: OCR / structure (the machine-read spec)

```bash
python scripts/ocr_extract.py out/slide_clean.jpg --out out/spec
# force a tier:  --det-model PP-OCRv5_server_det --rec-model PP-OCRv5_server_rec --device gpu
```

Runs PP-StructureV3 — layout analysis + table-structure + formula→LaTeX, with **PP-OCRv5** (PaddleOCR ≥ 3.7.0) as the text detection/recognition layer — and writes `spec.json` plus a `spec.overlay.png` showing detected blocks. Coordinates are in **cleaned-image pixels**, the same space as every Stage 2 measurement (`scale = 1280 / cleaned_width`), so they drop straight onto the canvas with no extra transform.

Why PP-StructureV3 rather than bare PP-OCRv5: v5 is the text layer only (det+rec — strings + boxes, tiny and fast, beating much larger VLMs at pure text, but no formulas/tables/reading-order). PP-StructureV3 wraps it and adds exactly the structure a faithful rebuild needs. The block `type` is normalized to `title | text | caption | formula | table | figure`; figures are what you redraw.

Weights download on first use from HuggingFace/BOS/ModelScope — hosts the sandbox allowlist usually blocks — so run `setup_paddle.sh` once on open network (set `PADDLE_PDX_MODEL_SOURCE=BOS` if in mainland China). See `references/ocr_integration.md`.

---

## Stage 2: Inventory (the spec)

View the cleaned image and write a structured inventory **before any HTML**:

- **Canvas mapping**: note the cleaned image's pixel size. All layout coordinates will be measured in cleaned-image pixels and scaled to the 1280×720 canvas (`scale = 1280 / cleaned_width`). When unsure of a position, crop and view that region.
- **Verbatim text** — every title, bullet, label, legend, footnote, page number. Transcribe math exactly (subscripts, superscripts, script letters, set notation).
- **Color palette** — sample real hex values from the image (title color, header-bar fill, card fill, border, body text, accents). Never guess defaults.
- **Every visual element**, classified by the vector-vs-raster decision tree (below).
- **Connectors** — arrows (single/double/dashed), return paths of feedback loops, dimension arrows in technical figures.

## The vector-vs-raster decision tree

For each non-text visual, ask in order:

```
1. Is it geometric AND regular (rects, lines, polygons, simple curves,
   charts, block diagrams, logic symbols, layouts whose structure is
   the content)?
      → Redraw as inline SVG.            [default for most slides]

1b. Is it geometric but IRREGULAR / instance-dense — random net routes,
    scattered elements whose *exact positions and topology ARE the
    content*, hand-placed examples you'd have to measure one by one?
      → Crop from the cleaned image (scripts/crop_region.py
        --white-balance). A redraw can only approximate such figures;
        every approximation is a visible detail mismatch.

2. Is it a smooth gradient/false-color field (heatmap, warpage surface,
   FEM/CFD render)?
      → If used as a small thumbnail where only the gist matters:
        stylized SVG gradient. If the actual field pattern matters or a
        first SVG attempt reads "cartoonish": crop it.

3. Is it continuous-tone content that can't be redrawn at all
   (photograph, screenshot, lit 3D render, dense scatter plot)?
      → Crop + embed as base64 data-URI. Keep crops rectangular,
        aligned to the element's bbox.

4. Is it a third-party logo / org mark?
      → Crop with background keying: crop_region.py --key-light 232
        gives the *original* mark on a transparent background — better
        than any hand-drawn approximation. Fall back to a simplified
        placeholder mark + text name only if keying fails (busy bg).
```

**Escalation rule (applies during Stage 4 too)**: if a vector redraw of a
complex region still mismatches the original after ONE fix iteration, stop
polishing the SVG and replace it with a crop. Vector-vs-raster is a fidelity
decision, not a pride decision — the crop *is* the original.

**Blending crops into a vector page** (all in `crop_region.py`):
`--white-balance` kills the photo color cast (rectangular diagram crops);
`--flat-field` removes vignetting/illumination gradients; `--key-light N`
makes light backgrounds transparent (logos/marks) — it flat-fields first,
because global luminance keying fails on vignetted corners.

Crops keep the output a *single file* — never reference external image files. Rule 1 vs 1b is the judgment call that matters: regular structure (a grid of pads, a feedback loop) redraws perfectly; irregular instance data (which pin connects where, exact trunk offsets) does not. Read `references/vector_vs_raster.md` for worked examples and the escalation rule.

**Icons carry meaning** — the critical lesson inherited from `photo-to-pptx`: technical icons (transistors, logic gates, wafers, chips, heatmaps) encode domain semantics. Hand-draw small inline SVGs that preserve the semantics; never substitute generic look-alikes. Audit icon choices in the inventory, before coding.

---

## Stage 3: Rebuild

Copy `references/html_canvas_template.html` as the starting point. Conventions it establishes (do not deviate without reason):

- **Fixed canvas**: `.slide{position:relative;width:1280px;height:720px;overflow:hidden}`. Everything inside is `position:absolute` with coordinates derived from cleaned-image measurements. Absolute positioning, not flex/grid for the page — fidelity beats responsiveness here, and it makes the verify-fix loop local (moving one element never reflows another).
- **CSS variables** for the sampled palette in `:root`.
- **Inline SVG** for every diagram, each with its own local `viewBox` and positioned with `style="position:absolute;left:..;top:.."`. Local coordinates keep each diagram independently debuggable.
- **System font stack** for body text; serif math stack (`"STIX Two Math","Cambria Math","Times New Roman"`) for math. No webfonts — self-containment.
- One HTML file per slide; multi-slide jobs get an `index.html` linking them.

**Math notation** is a classic failure point: naive `<sub><sup>` after a closing brace renders side-by-side, not stacked. Use the stacked-script flexbox pattern, Unicode script letters (𝒢 𝒮 𝒩…), and italic-serif conventions in `references/math_notation.md`.

**Layout patterns** (header-bar sections, bordered cards, dashed containers with interrupting titles, step→arrow→step chains, feedback-loop return paths, legends, footers) are catalogued with copy-paste CSS in `references/layout_and_css_patterns.md`.

**Technical diagram redraw recipes** (channel routing, dimension arrows, trunk/envelope boxes, mini heatmaps, waveforms, wafer maps, 3D cubes) are in `references/svg_diagram_patterns.md`.

Build order (same rationale as photo-to-pptx — errors localize):
title → top row → left column → middle → right column → bottom strip → footer. Complete each region (shapes + text + icons + arrows) before the next.

---

## Stage 4: Verify — the screenshot loop

Never ship unrendered HTML. Screenshot with headless Chromium:

```bash
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python scripts/render_verify.py slide.html
# writes slide_render.png (1280×720) and, with --ref slide_clean.jpg,
# a side-by-side comparison sheet slide_compare.png
```

View the render (and the comparison sheet) and check, in this order:

1. **Clipping/overflow** — content cut at slide bottom or hidden behind banners/panels (the #1 defect; fix by compacting paddings/fonts or moving panels up, never by letting it clip)
2. **Collisions** — panels overlapping text, captions colliding with footers
3. **Math** — sub/sup stacking, script letters rendering as tofu (font fallback)
4. **Icons** — blobs, missing arrowheads (usually SVG arc `sweep-flag` or fill mistakes)
5. **Color drift** — compare against the sampled palette, not memory
6. **Text fidelity** — re-read every label against the cleaned image once
7. **Detail mismatch in complex figures** — compare redrawn diagrams
   element-by-element against the original (the `--ref` comparison sheet
   makes this fast). Topology wrong / elements missing / positions
   approximated? → escalation rule: replace that SVG with a crop now.
8. **Crop seams** — embedded crops showing a gray tile edge or halo
   against the page background → re-crop with `--white-balance` /
   `--flat-field`, or `--key-light` for marks.

Expect 2–4 real defects on the first render. Fix all, re-render, then stop — don't chase sub-pixel alignment.

If Playwright/Chromium is unavailable, fall back to `wkhtmltoimage` (older WebKit: avoid flex/grid-dependent layout — another reason the template uses absolute positioning) or deliver with a note that the user should eyeball it in a browser.

---

## Quick troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `{gᵢ}` superscript appears beside subscript | naive `<sub><sup>` | stacked-script flexbox pattern (`math_notation.md`) |
| Bottom rows of a panel vanish | panel taller than remaining space, `overflow:hidden` clips | compact row padding/font, move panel up; verify with crop screenshot |
| Diagram fine alone, wrong on page | viewBox aspect ≠ element width/height | keep `width/height` attrs equal to viewBox dims (or same ratio) |
| Script letters (𝒢) render as boxes | missing math font in renderer | the serif math font-stack; worst case use `<i>G</i>` + note |
| Raster crop looks muddy next to crisp vector | expected (photo source) | shrink display size of crop, or redraw after all (rule 1) |
| Icon is a solid blob | filled path that should be stroked | `fill="none" stroke=...`; see svg library in photo-to-pptx |

## Bundled scripts

- `scripts/run_pipeline.py` — **closed-loop orchestrator**: extract → ocr → assemble → verify (`--mode auto|spec`, `--format html|pptx|both`, `--verify`). Auto-detects `photo-to-html/models/` for offline OCR.
- `scripts/extract_slide.py` — Stage 1 (identical to photo-to-pptx's; opencv + Pillow)
- `scripts/ocr_extract.py` — Stage 1.5: PP-StructureV3 (PP-OCRv5 text layer) → `spec.json` + overlay
- `scripts/assemble_html.py` — auto-mode HTML assembler: `spec.json` → single self-contained HTML (selectable text + faithful base64 crops; LaTeX/table-HTML kept as `data-*`)
- `scripts/assemble_pptx.py` — auto-mode PPTX assembler: `spec.json` → editable `.pptx` (native TextBox + Table; formulas/figures as picture crops)
- `scripts/setup_paddle.sh` — one-time `paddlepaddle` + `paddleocr>=3.7.0` install and PP-OCRv5 weight prefetch
- `scripts/download_paddle_models.py` — pre-download + verify offline model bundle (`--verify models/`)
- `scripts/crop_region.py` — crop a bbox from the cleaned image → base64 data-URI / `<img>` tag on stdout
- `scripts/render_verify.py` — Stage 4 screenshot + optional side-by-side sheet (playwright; falls back to wkhtmltoimage)
- `scripts/setup_benchmark.sh` — install PP-OCRv6 + MinerU2.5-Pro benchmark dependencies and warm model caches
- `scripts/download_benchmark_models.py` — pre-download/warm PP-OCRv6 and MinerU2.5-Pro model weights for reproducible benchmark runs
- `scripts/mineru_extract.py` — run MinerU2.5-Pro on a cleaned slide and emit Markdown plus a normalized content spec
- `scripts/evaluate_reconstruction.py` — compute automated content and optional rendered-image metrics
- `scripts/run_benchmark.py` — end-to-end no-human PP-OCRv6 vs MinerU2.5-Pro benchmark orchestrator

## Reference files

- `references/ocr_integration.md` — **Stage 1.5 + auto/vector modes, spec schema, model mirrors, troubleshooting**
- `references/html_canvas_template.html` — the canvas scaffold; **always start from this** (vector path)
- `references/vector_vs_raster.md` — hybrid decision tree, worked examples
- `references/layout_and_css_patterns.md` — slide-layout CSS cookbook
- `references/svg_diagram_patterns.md` — technical-diagram SVG recipes
- `references/math_notation.md` — math typesetting in plain HTML/CSS

## Dependencies

### Prerequisites (must be on the machine before setup)

| Requirement | Version | Notes |
| --- | --- | --- |
| **Python** | 3.9 – 3.12 | PaddlePaddle 3.x has no wheel for 3.13+; PaddleOCR 3.7 drops 3.8. `python3 --version` to check. |
| **pip** | ≥ 21 | Bundled with Python; `setup_paddle.sh` upgrades it. |
| **bash** | any | For `setup_paddle.sh`. macOS/Linux ship it; on Windows use WSL or Git Bash. |
| **git-lfs** | any | Only needed if cloning from GitHub — the 1.7 GB model weights are LFS-tracked. Install from https://git-lfs.com, then `git lfs install`. |
| **Network access** | — | First-time setup fetches ~500 MB of pip packages + 1.7 GB of model weights. After that, OCR runs 100% offline. |

On **Apple Silicon**, confirm `file $(which python3)` reports `arm64` — a
Rosetta/x86 Python will pull the x86 wheel and run emulated (slow).

### One-shot install (handles everything else)

```bash
# Rebuild + verify (vector path, always needed):
pip install opencv-python Pillow numpy playwright python-pptx --break-system-packages
# Chromium binaries usually pre-installed at /opt/pw-browsers in the Claude environment

# OCR closed loop (Stage 1.5) — run once on open network; the sandbox allowlist
# blocks the model-weight hosts, so do this on your own machine/server:
bash scripts/setup_paddle.sh          # CPU   (installs paddlepaddle>=3.3 + paddleocr>=3.7.0 + python-pptx + PP-OCRv5 weights)
bash scripts/setup_paddle.sh gpu      # CUDA build
bash scripts/setup_paddle.sh mac      # Apple Silicon (MPS) build
```

`setup_paddle.sh` installs: `paddlepaddle>=3.3`, `paddleocr>=3.7.0,<4`,
`opencv-python`, `Pillow`, `numpy`, `python-pptx>=0.6.23`, and pre-downloads
the 11 PP-StructureV3 sub-models (~1.7 GB) into `photo-to-html/models/`.

### PP-OCRv6 (optional, user-downloaded)

The bundled weights use **PP-OCRv5_server** (PP-StructureV3's default text
layer). To try the newer **PP-OCRv6** (tiny/small/medium), download the
weights yourself — `ocr_extract.py` auto-detects them. See
[references/offline_model_distribution.md §7](references/offline_model_distribution.md)
for download commands and priority order.

**Offline mode**: once `setup_paddle.sh` has finished, the bundled `models/` directory (1.7 GB, 11 sub-models) lets `ocr_extract.py` and `assemble_pptx.py` run with **zero network access**. The orchestrator auto-detects `photo-to-html/models/` and exports `PH2H_MODELS_DIR` to every subprocess; you can also point at a custom location with `--models-dir <path>` or `export PH2H_MODELS_DIR=<path>`.
