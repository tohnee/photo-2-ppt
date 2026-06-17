#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# photo-to-html — PaddlePaddle + PaddleOCR one-shot setup
#
# Installs the runtime Python packages and (by default) pre-downloads the
# PP-OCRv5 + PP-StructureV3 model weights into ``photo-to-html/models/`` so
# the OCR stage can run 100% offline afterwards.
#
#   Usage (run in an environment with open network access):
#       bash scripts/setup_paddle.sh                # CPU + auto mirror
#       bash scripts/setup_paddle.sh gpu            # CUDA build
#       bash scripts/setup_paddle.sh mac            # Apple Silicon (MPS) build
#       bash scripts/setup_paddle.sh cpu --mirror baidu_bos   # explicit mirror
#
#   Environment overrides:
#       PADDLE_EXTRA_INSTALL_ARGS   extra flags for ``pip install`` (e.g. --index-url)
#       PADDLE_PIP_BIN              which ``pip`` binary to use (default: `python -m pip`)
#       PADDLE_PYTHON_BIN           which Python to use (default: ``python3`` -> ``python``)
#       PADDLE_SKIP_MODELS=1        skip the model-weight pre-download step
#       PADDLE_MIRROR               hugginface | modelscope | baidu_bos | auto (default)
#
# Requires Python 3.9–3.12. On Apple Silicon you MUST run this under a
# native arm64 Python — a Rosetta/x86 Python will pull the x86 wheel and
# run emulated (slow).
# -----------------------------------------------------------------------------

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/.." && pwd)"
MODELS_DIR="${PROJECT_ROOT}/models"

# ---- detect Python ---------------------------------------------------------
if [[ -n "${PADDLE_PYTHON_BIN:-}" ]]; then
    PY="${PADDLE_PYTHON_BIN}"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "ERROR: no Python interpreter found." >&2
    exit 2
fi
PIP="${PADDLE_PIP_BIN:-$PY -m pip}"

echo "=== photo-to-html setup (mode: ${1:-cpu}) ==="
echo "    Python: $($PY --version 2>&1) at $(command -v $PY)"
echo "    pip:    ${PIP}"
echo "    project: ${PROJECT_ROOT}"
echo "    models:  ${MODELS_DIR}"
echo

# ---- platform & mode detection --------------------------------------------
MODE="${1:-cpu}"
shift || true  # remaining args (--mirror, --force, etc.) forwarded

EXTRA_PIP_ARGS=( ${PADDLE_EXTRA_INSTALL_ARGS:-} )
PY_VERSION="$($PY -c 'import sys;print("%d.%d" % sys.version_info[:2])')"

case "${MODE}" in
    cpu)
        # Standard CPU wheel from PyPI — works everywhere.
        PADDLE_PKG="paddlepaddle>=3.3"
        ;;
    gpu|cuda)
        # Nvidia CUDA build. Users with a custom CUDA toolkit (cu123/cu124/cu126)
        # may want to set PADDLE_EXTRA_INSTALL_ARGS with an explicit --index-url
        # pointing at https://www.paddlepaddle.org.cn/packages/stable/cu126/.
        PADDLE_PKG="paddlepaddle-gpu>=3.3"
        # Offer a sensible default when running in mainland China.
        if [[ "${#EXTRA_PIP_ARGS[@]}" -eq 0 ]]; then
            EXTRA_PIP_ARGS+=( --index-url "https://www.paddlepaddle.org.cn/packages/stable/cu126/" )
            EXTRA_PIP_ARGS+=( --trusted-host "www.paddlepaddle.org.cn" )
        fi
        ;;
    mac|apple|mps|arm64)
        # Apple Silicon — MPS-capable wheels are on PyPI since 3.x.
        if [[ "$(uname -s)" != "Darwin" ]]; then
            echo "WARNING: '${MODE}' mode requested but this box is not Darwin." >&2
            echo "    Falling back to CPU wheel." >&2
        fi
        PADDLE_PKG="paddlepaddle>=3.3"
        ;;
    *)
        echo "Unknown mode '${MODE}'. Use: cpu | gpu | mac" >&2
        exit 2
        ;;
esac

echo "Target Paddle package: ${PADDLE_PKG}"
if [[ "${#EXTRA_PIP_ARGS[@]}" -gt 0 ]]; then
    echo "Extra pip install flags: ${EXTRA_PIP_ARGS[*]}"
fi
echo

# ---- 1) upgrade pip/setuptools -------------------------------------------------
echo "[1/4] upgrading pip & setuptools …"
$PIP install --quiet --upgrade pip setuptools wheel

# ---- 2) install PaddlePaddle (CPU/GPU/Apple Silicon) --------------------------
echo "[2/4] installing ${PADDLE_PKG} …"
# PyPI's x86_64 wheels cover most Linux/Windows; for very new CUDA toolkits
# we fall back to the Paddle custom index.
if ! $PIP install --upgrade "${EXTRA_PIP_ARGS[@]}" "${PADDLE_PKG}"; then
    echo
    echo "Direct install failed. Trying the public PaddlePaddle index …" >&2
    $PIP install --upgrade \
        --index-url "https://pypi.org/simple/" \
        "${PADDLE_PKG}"
fi

# ---- 3) install PaddleOCR + image libraries ------------------------------------
echo "[3/4] installing paddleocr>=3.7.0 and imaging libraries …"
$PIP install --upgrade "paddleocr>=3.7.0,<4"
$PIP install --upgrade opencv-python Pillow numpy
# python-pptx is required by assemble_pptx.py for offline .pptx rebuild.
$PIP install --upgrade "python-pptx>=0.6.23"

# ---- 4) pre-download weights (PP-OCRv5 + PP-StructureV3) ----------------------
if [[ "${PADDLE_SKIP_MODELS:-0}" == "1" ]]; then
    echo
    echo "[4/4] (skipped model pre-download; PADDLE_SKIP_MODELS=1)"
else
    echo "[4/4] pre-downloading model weights into ${MODELS_DIR} …"
  export PADDLE_PDX_CACHE_HOME="${MODELS_DIR}/.cache"
  mkdir -p "${PADDLE_PDX_CACHE_HOME}"
  "$PY" "${HERE}/download_paddle_models.py" --out-dir "${MODELS_DIR}" || {
        echo
        echo "Model-weight pre-download failed (see above). This usually" >&2
        echo "means network access to HuggingFace / Baidu BOS / ModelScope" >&2
        echo "is blocked on this machine. You can:" >&2
        echo
        echo "  1. Re-run with an explicit mirror:  PADDLE_MIRROR=baidu_bos bash $0" >&2
        echo "  2. Run the downloader manually:      $PY ${HERE}/download_paddle_models.py --out-dir ${MODELS_DIR}" >&2
        echo "  3. Pre-download weights on a machine with open network and" >&2
        echo "     copy the resulting ${MODELS_DIR} here. Set" >&2
        echo "     PH2H_MODELS_DIR=${MODELS_DIR} before running ocr_extract.py." >&2
        exit 3
    }
fi

echo
echo "=== setup complete ==="
echo "Runtime: paddleocr>=3.7.0 with ${PADDLE_PKG}."
if [[ "${PADDLE_SKIP_MODELS:-0}" != "1" ]]; then
    echo "Offline weights: ${MODELS_DIR} (manifest: ${MODELS_DIR}/manifest.json)"
fi
echo
echo "Smoke test (on-demand):"
echo "    export PH2H_MODELS_DIR=${MODELS_DIR}"
echo "    ${PY} ${PROJECT_ROOT}/scripts/ocr_extract.py slide_clean.jpg --out slide/spec"
