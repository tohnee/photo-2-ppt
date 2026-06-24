#!/usr/bin/env python3
"""Run the fully automated PP-OCRv6 vs MinerU2.5-Pro benchmark chain.

Input can be a single image or a directory. Each image is first normalized by
extract_slide.py so both backends see the same cleaned slide. The Paddle chain
uses run_pipeline.py in spec/auto mode and can render HTML for visual metrics.
The MinerU chain runs MinerU2.5-Pro and records content metrics automatically.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def run(cmd: list[str]) -> float:
    print("$ " + " ".join(cmd), file=sys.stderr)
    t0 = time.time()
    subprocess.run(cmd, check=True)
    return time.time() - t0


def images_from(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.suffix.lower() in IMG_EXTS)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="image file or directory of images")
    ap.add_argument("--out-dir", default="benchmark_out")
    ap.add_argument("--reference-text-dir", default=None,
                    help="optional directory containing <stem>.txt ground truth")
    ap.add_argument("--reference-image-dir", default=None,
                    help="optional directory containing clean <stem>.png/.jpg ground truth")
    ap.add_argument("--skip-paddle", action="store_true")
    ap.add_argument("--skip-mineru", action="store_true")
    ap.add_argument("--paddle-det", default="PP-OCRv6_medium_det")
    ap.add_argument("--paddle-rec", default="PP-OCRv6_medium_rec")
    ap.add_argument("--paddle-device", default=None)
    ap.add_argument("--mineru-backend", choices=["transformers", "vllm"], default="transformers")
    ap.add_argument("--mineru-model", default="opendatalab/MinerU2.5-Pro-2604-1.2B")
    args = ap.parse_args(argv)

    here = Path(__file__).resolve().parent
    out_root = Path(args.out_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    refs_txt = Path(args.reference_text_dir).resolve() if args.reference_text_dir else None
    refs_img = Path(args.reference_image_dir).resolve() if args.reference_image_dir else None

    summary = {"schema_version": 1, "samples": []}
    for image in images_from(Path(args.input).resolve()):
        sample_dir = out_root / image.stem
        sample_dir.mkdir(parents=True, exist_ok=True)
        clean = sample_dir / "slide_clean.jpg"
        sample = {"id": image.stem, "input": str(image), "chains": {}}

        run([sys.executable, str(here / "extract_slide.py"), str(image), "--output", str(clean)])
        ref_text = refs_txt / f"{image.stem}.txt" if refs_txt and (refs_txt / f"{image.stem}.txt").exists() else None
        ref_image = None
        if refs_img:
            for ext in (".png", ".jpg", ".jpeg"):
                cand = refs_img / f"{image.stem}{ext}"
                if cand.exists():
                    ref_image = cand
                    break

        if not args.skip_paddle:
            pdir = sample_dir / "paddle_ocrv6"
            pdir.mkdir(exist_ok=True)
            cmd = [sys.executable, str(here / "run_pipeline.py"), str(image),
                   "--out-dir", str(pdir), "--format", "html", "--verify",
                   "--det-model", args.paddle_det, "--rec-model", args.paddle_rec]
            if args.paddle_device:
                cmd += ["--device", args.paddle_device]
            elapsed = run(cmd)
            eval_cmd = [sys.executable, str(here / "evaluate_reconstruction.py"),
                        "--candidate-spec", str(pdir / "spec.json"),
                        "--out", str(pdir / "metrics.json")]
            if ref_text:
                eval_cmd += ["--reference-text", str(ref_text)]
            if ref_image and (pdir / "slide_render.png").exists():
                eval_cmd += ["--reference-image", str(ref_image),
                             "--rendered-image", str(pdir / "slide_render.png")]
            run(eval_cmd)
            sample["chains"]["paddle_ocrv6"] = {
                "elapsed_sec": round(elapsed, 3),
                "metrics": str(pdir / "metrics.json"),
                "spec": str(pdir / "spec.json"),
                "html": str(pdir / "slide.html"),
            }

        if not args.skip_mineru:
            mdir = sample_dir / "mineru25_pro"
            mdir.mkdir(exist_ok=True)
            elapsed = run([sys.executable, str(here / "mineru_extract.py"), str(clean),
                           "--out", str(mdir / "spec"), "--model", args.mineru_model,
                           "--backend", args.mineru_backend])
            eval_cmd = [sys.executable, str(here / "evaluate_reconstruction.py"),
                        "--candidate-spec", str(mdir / "spec.json"),
                        "--out", str(mdir / "metrics.json")]
            if ref_text:
                eval_cmd += ["--reference-text", str(ref_text)]
            run(eval_cmd)
            sample["chains"]["mineru25_pro"] = {
                "elapsed_sec": round(elapsed, 3),
                "metrics": str(mdir / "metrics.json"),
                "spec": str(mdir / "spec.json"),
                "markdown": str(mdir / "spec.md"),
            }

        summary["samples"].append(sample)

    (out_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {out_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
