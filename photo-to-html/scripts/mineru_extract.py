#!/usr/bin/env python3
"""Run MinerU2.5-Pro on one cleaned slide image and emit benchmark artifacts.

MinerU2.5-Pro is a document-parsing VLM. Its public utility API returns parsed
content (usually Markdown/JSON-like text) rather than the exact slide-level bbox
contract consumed by assemble_html.py. This wrapper therefore records the raw
MinerU output plus a normalized, content-oriented spec with a single full-canvas
``text`` block. The benchmark harness evaluates that output on content metrics
and keeps visual reconstruction metrics for bbox-aware engines such as
PP-StructureV3/PP-OCRv6.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def run_mineru_transformers(image: Path, model_name: str, image_analysis: bool) -> str:
    from PIL import Image
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
    from mineru_vl_utils import MinerUClient

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_name, dtype="auto", device_map="auto", trust_remote_code=True
    )
    processor = AutoProcessor.from_pretrained(
        model_name, use_fast=True, trust_remote_code=True
    )
    client = MinerUClient(
        backend="transformers",
        model=model,
        processor=processor,
        image_analysis=image_analysis,
    )
    return str(client.two_step_extract(Image.open(image)))


def run_mineru_vllm(image: Path, model_name: str, image_analysis: bool) -> str:
    from PIL import Image
    from vllm import LLM
    from mineru_vl_utils import MinerUClient, MinerULogitsProcessor

    llm = LLM(model=model_name, logits_processors=[MinerULogitsProcessor])
    client = MinerUClient(
        backend="vllm-engine",
        vllm_llm=llm,
        image_analysis=image_analysis,
    )
    return str(client.two_step_extract(Image.open(image)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", help="cleaned slide image")
    ap.add_argument("--out", required=True, help="output prefix; writes .json and .md")
    ap.add_argument("--model", default="opendatalab/MinerU2.5-Pro-2604-1.2B")
    ap.add_argument("--backend", choices=["transformers", "vllm"], default="transformers")
    ap.add_argument("--image-analysis", action="store_true")
    args = ap.parse_args(argv)

    image = Path(args.image).resolve()
    out_prefix = Path(args.out).resolve()
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    if args.backend == "transformers":
        markdown = run_mineru_transformers(image, args.model, args.image_analysis)
    else:
        markdown = run_mineru_vllm(image, args.model, args.image_analysis)
    elapsed = time.time() - t0

    width, height = _image_size(image)
    scale = 1280.0 / width if width else 1.0
    spec = {
        "source_image": str(image),
        "image_size": {"width": width, "height": height},
        "canvas": {"width": 1280, "height": round(height * scale)},
        "scale": scale,
        "ocr": {
            "engine": "MinerU2.5-Pro",
            "model": args.model,
            "backend": args.backend,
            "elapsed_sec": round(elapsed, 3),
            "schema_source": "mineru_markdown_full_canvas",
        },
        "blocks": [{
            "id": "mineru_b0",
            "type": "text",
            "raw_label": "markdown",
            "bbox": [0, 0, width, height],
            "text": markdown,
            "reading_order": 0,
        }],
        "markdown": markdown,
    }

    out_prefix.with_suffix(".md").write_text(markdown, encoding="utf-8")
    out_prefix.with_suffix(".json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {out_prefix.with_suffix('.json')} and {out_prefix.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
