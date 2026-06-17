# Offline model distribution (photo-to-html)

The OCR stage (`scripts/ocr_extract.py`) uses PaddleOCR 3.7's PPStructureV3
pipeline, which orchestrates 11 sub-models for text detection/recognition,
layout analysis, table structure, formula recognition, and more. All weights
are pulled from HuggingFace / ModelScope / Baidu BOS on first use.

In restricted networks (air-gapped lab, corporate proxy, Claude sandbox),
that first-use pull fails. This document explains how to

1. build an offline `models/` directory once,
2. distribute it alongside the photo-to-html skill,
3. point `ocr_extract.py` at it at run time.

## 1. One-time download

On a machine with open network access, run from the project root:

```bash
# default: CPU wheel; picks fastest mirror automatically
bash scripts/setup_paddle.sh

# or if you have CUDA on the target machine:
bash scripts/setup_paddle.sh gpu

# or Apple Silicon / arm64:
bash scripts/setup_paddle.sh mac
```

`setup_paddle.sh` installs the Python packages (paddlepaddle + paddleocr
3.7.x) and then calls `scripts/download_paddle_models.py`, which writes the
following tree to `photo-to-html/models/`:

```
photo-to-html/models/
├── manifest.json
├── PP-OCRv5_server_det/          # text detection (PP-OCRv5)
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── PP-OCRv5_server_rec/          # text recognition (PP-OCRv5)
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── PP-DocLayout_plus-L/          # layout detection
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── PP-DocBlockLayout/            # region detection
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── SLANet_plus/                  # wireless table structure
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── SLANeXt_wired/                # wired table structure
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── PP-FormulaNet_plus-L/         # formula recognition → LaTeX
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── PP-LCNet_x1_0_textline_ori/   # textline orientation
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── PP-LCNet_x1_0_table_cls/      # table classification
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
├── RT-DETR-L_wired_table_cell_det/   # wired table cell detection
│   ├── inference.json
│   ├── inference.pdiparams
│   ├── inference.yml
│   └── config.json
└── RT-DETR-L_wireless_table_cell_det/  # wireless table cell detection
    ├── inference.json
    ├── inference.pdiparams
    ├── inference.yml
    └── config.json
```

Total size is roughly **1.7 GB** and takes a few minutes to download
(depending on mirror speed).

### Re-downloading / forcing a refresh

```bash
bash scripts/setup_paddle.sh
# or manually:
python scripts/download_paddle_models.py --out-dir models/
```

### Explicit mirror selection

The auto mode pings HuggingFace, then falls back to ModelScope, then
Baidu BOS. You can pin one to avoid the probe:

```bash
PADDLE_MIRROR=baidu_bos bash scripts/setup_paddle.sh          # mainland China
PADDLE_MIRROR=huggingface bash scripts/setup_paddle.sh        # EU/US
```

## 2. Distribution

Copy the entire `photo-to-html/models/` directory to the target machine.
Options:

| Method | Notes |
| ------ | ----- |
| tar + scp | `tar -cf - photo-to-html/models \| zstd -9 > models.tar.zst` (~1.5 GB compressed) |
| rsync | `rsync -av photo-to-html/models/ target:photo-to-html/models/` |
| Docker layer | `COPY --link photo-to-html/models /opt/ph2h/models` + `ENV PH2H_MODELS_DIR=/opt/ph2h/models` |

### Integrity check (on the target)

```bash
python scripts/download_paddle_models.py --verify /path/to/models
# -> verify: OK — 11 model directories, all checksums match.
```

This reads `manifest.json` and re-computes SHA256 for every file. Exit code
0 means every file is byte-identical to the download-time state.

### Version control

Model weights are binary blobs (1.7 GB total). They are tracked via
**Git LFS** so the repo stays clone-able and weights are byte-verifiable
on every clone. The `.gitattributes` at the repo root registers the
LFS filters:

```
*.pdiparams filter=lfs diff=lfs merge=lfs -text
*.pdmodel   filter=lfs diff=lfs merge=lfs -text
```

`inference.json` (model structure, ~1 MB per model) and the small
config/yml files are committed as regular git text — only the large
binary weight tensors go through LFS.

After cloning, `git lfs pull` materializes the weights on disk. The
`manifest.json` SHA256 check (`download_paddle_models.py --verify`)
catches any LFS corruption.

## 3. Pointing ocr_extract.py at the offline tree

Set the `PH2H_MODELS_DIR` environment variable before running anything:

```bash
export PH2H_MODELS_DIR=$(pwd)/photo-to-html/models
python scripts/ocr_extract.py slide_clean.jpg --out slide/spec
```

You can also set `PH2H_MODELS_DIR` as a repo-wide convention via `.env`:

```
# photo-to-html/.env
PH2H_MODELS_DIR=/absolute/path/to/photo-to-html/models
```

`ocr_extract.py` walks `$PH2H_MODELS_DIR/`, detects each model directory by
matching against the known 11 model names, and forwards them to
PPStructureV3 via the `*_model_dir` kwargs, short-circuiting its
network-facing downloader.

## 4. Smoke test after distribution

```bash
cd photo-to-html
python scripts/download_paddle_models.py --verify models
# -> verify: OK — 11 model directories, all checksums match.

# then a real image:
python scripts/extract_slide.py test_assets/example_slide.jpg \
    --output slide_clean.jpg
export PH2H_MODELS_DIR=$(pwd)/models
python scripts/ocr_extract.py slide_clean.jpg --out slide/spec
# should print "[ocr] using local weights from .../models"
```

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| `RuntimeError: No available model` | PaddleOCR 3.7 can't find weights locally and has no network | Set `PH2H_MODELS_DIR` and re-run `setup_paddle.sh` |
| `WARNING: PH2H_MODELS_DIR=... exists but contains no recognized model directories` | `models/` is incomplete (partial copy) or directory names don't match | Re-run the downloader with `--out-dir models/` |
| `verify: SHA256: …` | Bit rot in transit or bad un-tar | Re-download: `python scripts/download_paddle_models.py --out-dir models/` |
| HTTP 403 / SSL cert errors | Corporate proxy blocking HF | Use `PADDLE_MIRROR=baidu_bos` or `PADDLE_MIRROR=modelscope` |
| Apple Silicon `MPS` not available after setup | Using a Rosetta Python | Confirm `file $(which python3)` reports `arm64` |
| `429 Too Many Requests` from HuggingFace | Rapid automated runs | `--mirror modelscope` or `--mirror baidu_bos` |

## 6. Known model URLs (for reference)

The `download_paddle_models.py` script uses PaddleOCR's built-in downloader
(paddlex API), which automatically tries these mirrors in order:

```
HuggingFace:
  https://huggingface.co/PaddlePaddle/<model_name>/resolve/main/

ModelScope (aliyun):
  https://modelscope.cn/models/Paddle/<model_name>/resolve/master/

Baidu BOS (mainland China):
  https://paddleocr.bj.bcebos.com/PP-OCR/model/<model_name>/
```

If any one stops serving, re-run with `--mirror` switched to a different
host — the model identifier is stable across mirrors.

## 7. PP-OCRv6 (optional, user-downloaded)

The bundled `models/` tree ships **PP-OCRv5_server** as the text layer
because that is what PP-StructureV3's official config defaults to. If you
want to try the newer **PP-OCRv6** (tiny/small/medium) for text detection
and recognition, download the weights yourself and drop them into the
same `models/` directory — `ocr_extract.py` will pick them up automatically.

### What v6 replaces

Only the **text detection** and **text recognition** sub-models. The other
9 sub-models (layout, region, table structure, table cell detection,
formula recognition, textline orientation, table classification) stay on
their default versions — PP-StructureV3 does not yet ship v6 variants
for those.

### Downloading v6 weights

```bash
cd photo-to-html

# Pick a variant: medium (best accuracy) | small (balanced) | tiny (fastest)
VARIANT=medium   # or: small | tiny

# Option A — via huggingface_hub (recommended):
pip install huggingface_hub
python - <<EOF
from huggingface_hub import snapshot_download
import os
for task in ("det", "rec"):
    repo = f"PaddlePaddle/PP-OCRv6_${VARIANT}_{task}"
    snapshot_download(
        repo_id=repo,
        local_dir=f"models/PP-OCRv6_${VARIANT}_{task}",
        allow_patterns=["inference.json", "inference.pdiparams",
                        "inference.yml", "config.json"],
    )
    print(f"  OK: models/PP-OCRv6_${VARIANT}_{task}")
EOF

# Option B — via paddlex's own downloader (tries HF/ModelScope/BOS):
python -c "
import os
os.environ['PADDLE_PDX_CACHE_HOME'] = '$(pwd)/models/.cache'
from paddleocr import PPStructureV3
PPStructureV3(
    text_detection_model_name='PP-OCRv6_${VARIANT}_det',
    text_recognition_model_name='PP-OCRv6_${VARIANT}_rec',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
)
" 2>&1 | tail -5
# then copy from models/.cache/official_models/ to models/
cp -r models/.cache/official_models/PP-OCRv6_${VARIANT}_det models/
cp -r models/.cache/official_models/PP-OCRv6_${VARIANT}_rec models/
```

### Priority order (automatic)

Once v6 weights are on disk, `ocr_extract.py` resolves the text layer in
this order (first match wins):

1. `--det-model` / `--rec-model` CLI flag (if that directory exists)
2. `PP-OCRv6_medium_*` (if present)
3. `PP-OCRv6_small_*` (if present)
4. `PP-OCRv6_tiny_*` (if present)
5. `PP-OCRv5_server_*` (bundled default)
6. `PP-OCRv5_mobile_*` (fallback)

So: **just drop v6 weights into `models/` and re-run** — no other change
needed. If you want to force v5 even when v6 is present, pass
`--det-model PP-OCRv5_server_det --rec-model PP-OCRv5_server_rec`.

### Forcing a specific v6 variant

```bash
# Use tiny even if medium is also downloaded:
python scripts/ocr_extract.py slide_clean.jpg --out spec \
    --det-model PP-OCRv6_tiny_det --rec-model PP-OCRv6_tiny_rec
```

### Caveats

- v6 weights are **not** in the Git LFS bundle — you download them
  separately. The `manifest.json` from `setup_paddle.sh` will not list
  them; re-run `python scripts/download_paddle_models.py --manifest-only`
  to regenerate the manifest after adding v6 dirs.
- v6 has no `server` tier. For maximum accuracy on dense slides, the
  bundled v5_server may still beat v6_medium. Benchmark on your own
  images before switching permanently.