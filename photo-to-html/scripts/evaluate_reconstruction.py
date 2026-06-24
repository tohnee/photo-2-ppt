#!/usr/bin/env python3
"""Evaluate OCR/spec content and optional rendered-image reconstruction quality."""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
from pathlib import Path


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def spec_text(spec: dict) -> str:
    parts = []
    for b in spec.get("blocks", []):
        if b.get("text"):
            parts.append(str(b["text"]))
        elif b.get("latex"):
            parts.append(str(b["latex"]))
        elif b.get("html"):
            parts.append(str(b["html"]))
    return "\n".join(parts)


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(a=normalize_text(a), b=normalize_text(b)).ratio()


def levenshtein(a: str, b: str) -> int:
    a, b = normalize_text(a), normalize_text(b)
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def image_metrics(ref: Path, pred: Path) -> dict:
    from PIL import Image
    import numpy as np

    r = Image.open(ref).convert("RGB")
    p = Image.open(pred).convert("RGB").resize(r.size, Image.LANCZOS)
    ra = np.asarray(r).astype("float32")
    pa = np.asarray(p).astype("float32")
    mse = float(np.mean((ra - pa) ** 2))
    psnr = 99.0 if mse == 0 else 20 * math.log10(255.0 / math.sqrt(mse))
    mae = float(np.mean(np.abs(ra - pa)))
    return {"mse": round(mse, 4), "mae": round(mae, 4), "psnr": round(psnr, 4)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-spec", required=True)
    ap.add_argument("--reference-spec")
    ap.add_argument("--reference-text")
    ap.add_argument("--reference-image")
    ap.add_argument("--rendered-image")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    candidate = json.loads(Path(args.candidate_spec).read_text(encoding="utf-8"))
    cand_text = spec_text(candidate)
    metrics = {
        "candidate_spec": str(Path(args.candidate_spec).resolve()),
        "block_count": len(candidate.get("blocks", [])),
        "block_types": {},
        "text_chars": len(normalize_text(cand_text)),
    }
    for b in candidate.get("blocks", []):
        t = b.get("type", "unknown")
        metrics["block_types"][t] = metrics["block_types"].get(t, 0) + 1

    ref_text = None
    if args.reference_spec:
        ref_text = spec_text(json.loads(Path(args.reference_spec).read_text(encoding="utf-8")))
    if args.reference_text:
        ref_text = Path(args.reference_text).read_text(encoding="utf-8")
    if ref_text is not None:
        dist = levenshtein(ref_text, cand_text)
        denom = max(1, len(normalize_text(ref_text)))
        metrics["text_similarity"] = round(ratio(ref_text, cand_text), 6)
        metrics["text_edit_distance"] = dist
        metrics["cer_like"] = round(dist / denom, 6)

    if args.reference_image and args.rendered_image:
        metrics["image"] = image_metrics(Path(args.reference_image), Path(args.rendered_image))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
