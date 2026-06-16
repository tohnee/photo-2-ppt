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

### What to exclude from version control

The model weights are binary blobs. **Never commit them to git.** Keep the
`models/` directory listed in `.gitignore`:

```
photo-to-html/models/
*.pdmodel
*.pdiparams
```

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