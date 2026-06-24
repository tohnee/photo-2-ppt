#!/usr/bin/env python3
"""Download/cache optional benchmark backends for the photo-to-html skill.

This script is intentionally import-lazy: it can be committed and inspected on
machines without PaddleOCR, Transformers, or MinerU installed. It prepares the
model caches used by the fully automated PP-OCRv6 and MinerU2.5-Pro benchmark
chains so first-run network latency never pollutes evaluation numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_PADDLE_DET = "PP-OCRv6_medium_det"
DEFAULT_PADDLE_REC = "PP-OCRv6_medium_rec"
DEFAULT_MINERU_MODEL = "opendatalab/MinerU2.5-Pro-2604-1.2B"


def _run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("$ " + " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True, env=env)


def warm_paddleocr(det_model: str, rec_model: str, engine: str, device: str | None,
                   work_dir: Path) -> dict:
    """Instantiate PaddleOCR once to force lazy model downloads."""
    code = f"""
from paddleocr import PaddleOCR
ocr = PaddleOCR(
    text_detection_model_name={det_model!r},
    text_recognition_model_name={rec_model!r},
    engine={engine!r},
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    {('device='+repr(device)+',') if device else ''}
)
print('paddleocr-ready')
"""
    t0 = time.time()
    _run([sys.executable, "-c", code])
    return {
        "backend": "paddleocr",
        "det_model": det_model,
        "rec_model": rec_model,
        "engine": engine,
        "device": device,
        "elapsed_sec": round(time.time() - t0, 3),
    }


def warm_mineru(model: str, backend: str, trust_remote_code: bool = True) -> dict:
    """Download/cache MinerU2.5-Pro via the selected backend."""
    t0 = time.time()
    if backend == "transformers":
        code = f"""
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
model = Qwen2VLForConditionalGeneration.from_pretrained(
    {model!r}, dtype='auto', device_map='auto', trust_remote_code={trust_remote_code!r}
)
processor = AutoProcessor.from_pretrained(
    {model!r}, use_fast=True, trust_remote_code={trust_remote_code!r}
)
print('mineru-transformers-ready')
"""
        _run([sys.executable, "-c", code])
    elif backend == "vllm":
        code = f"""
from vllm import LLM
from mineru_vl_utils import MinerULogitsProcessor
llm = LLM(model={model!r}, logits_processors=[MinerULogitsProcessor])
print('mineru-vllm-ready')
"""
        _run([sys.executable, "-c", code])
    else:
        raise ValueError(f"unknown MinerU backend: {backend}")
    return {
        "backend": "mineru",
        "model": model,
        "engine": backend,
        "elapsed_sec": round(time.time() - t0, 3),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="benchmark_models_manifest.json",
                    help="write a small manifest recording what was warmed")
    ap.add_argument("--skip-paddle", action="store_true")
    ap.add_argument("--skip-mineru", action="store_true")
    ap.add_argument("--paddle-det", default=DEFAULT_PADDLE_DET)
    ap.add_argument("--paddle-rec", default=DEFAULT_PADDLE_REC)
    ap.add_argument("--paddle-engine", default="transformers",
                    choices=["paddle", "onnx", "openvino", "tensorrt", "transformers"])
    ap.add_argument("--paddle-device", default=None)
    ap.add_argument("--mineru-model", default=DEFAULT_MINERU_MODEL)
    ap.add_argument("--mineru-backend", default="transformers", choices=["transformers", "vllm"])
    args = ap.parse_args(argv)

    records = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hf_home": os.environ.get("HF_HOME"),
        "transformers_cache": os.environ.get("TRANSFORMERS_CACHE"),
        "records": [],
    }
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_paddle:
        records["records"].append(
            warm_paddleocr(args.paddle_det, args.paddle_rec, args.paddle_engine,
                           args.paddle_device, out.parent)
        )
    if not args.skip_mineru:
        records["records"].append(
            warm_mineru(args.mineru_model, args.mineru_backend)
        )

    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
