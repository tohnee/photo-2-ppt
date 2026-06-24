#!/usr/bin/env bash
# Fully automated benchmark environment setup for PP-OCRv6 and MinerU2.5-Pro.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/.." && pwd)"
PY="${PH2H_PYTHON_BIN:-python3}"
PIP="${PH2H_PIP_BIN:-$PY -m pip}"
MODE="${1:-cpu}"
shift || true

: "${HF_HOME:=${PROJECT_ROOT}/models/hf-cache}"
: "${TRANSFORMERS_CACHE:=${HF_HOME}/transformers}"
export HF_HOME TRANSFORMERS_CACHE
mkdir -p "$HF_HOME" "$TRANSFORMERS_CACHE"

echo "=== photo-to-html benchmark setup (${MODE}) ==="
echo "Python: $($PY --version 2>&1)"
echo "HF_HOME=${HF_HOME}"
echo

$PIP install --upgrade pip setuptools wheel

case "$MODE" in
  cpu)
    $PIP install --upgrade "paddleocr[all]" transformers torch torchvision torchaudio
    ;;
  gpu|cuda)
    # Users may override indexes with PH2H_EXTRA_PIP_ARGS.
    # shellcheck disable=SC2086
    $PIP install --upgrade ${PH2H_EXTRA_PIP_ARGS:-} torch torchvision torchaudio
    $PIP install --upgrade "paddleocr[all]" transformers
    ;;
  mineru-only)
    ;;
  *)
    echo "Usage: bash scripts/setup_benchmark.sh [cpu|gpu|mineru-only]" >&2
    exit 2
    ;;
esac

# MinerU official tooling. vLLM is optional because it is platform-sensitive;
# use PH2H_MINERU_BACKEND=vllm to install the vLLM extra.
if [[ "${PH2H_MINERU_BACKEND:-transformers}" == "vllm" ]]; then
  $PIP install --upgrade "mineru-vl-utils[vllm]"
else
  $PIP install --upgrade "mineru-vl-utils[transformers]"
fi

if [[ "${PH2H_SKIP_MODEL_WARMUP:-0}" != "1" ]]; then
  "$PY" "${HERE}/download_benchmark_models.py" \
    --out "${PROJECT_ROOT}/models/benchmark_models_manifest.json" \
    --mineru-backend "${PH2H_MINERU_BACKEND:-transformers}" \
    "$@"
else
  echo "Skipping model warmup because PH2H_SKIP_MODEL_WARMUP=1"
fi

echo "=== benchmark setup complete ==="
