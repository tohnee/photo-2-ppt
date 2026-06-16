#!/usr/bin/env python3
"""Pre-download PPStructureV3 model weights via PaddleOCR's official API.

The script uses ``paddlex`` built-in downloader (which tries HuggingFace,
ModelScope, and AI Studio mirrors) to fetch all default sub-models used by
the ``PPStructureV3`` pipeline. Weights are written to ``--out-dir`` and
a ``manifest.json`` is generated for integrity verification.

Offline usage
-------------
Set ``PH2H_MODELS_DIR`` to ``--out-dir`` before running ``ocr_extract.py``::

    export PH2H_MODELS_DIR=$(pwd)/photo-to-html/models
    python scripts/ocr_extract.py slide_clean.jpg --out slide/spec

The ``ocr_extract.py`` script detects this variable and passes every
``*_model_dir`` kwarg to PPStructureV3, short-circuiting the network
downloader entirely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Model catalog — mappings from PaddleOCR 3.7 PPStructureV3 sub-model names
# to the *_model_dir kwargs accepted by PPStructureV3.__init__().
# ---------------------------------------------------------------------------

MODEL_TO_KWARG = {
    "PP-OCRv5_server_det": "text_detection_model_dir",
    "PP-OCRv5_server_rec": "text_recognition_model_dir",
    "PP-DocLayout_plus-L": "layout_detection_model_dir",
    "PP-DocBlockLayout": "region_detection_model_dir",
    "SLANet_plus": "wireless_table_structure_recognition_model_dir",
    "SLANeXt_wired": "wired_table_structure_recognition_model_dir",
    "PP-FormulaNet_plus-L": "formula_recognition_model_dir",
    "PP-LCNet_x1_0_textline_ori": "textline_orientation_model_dir",
    "PP-LCNet_x1_0_table_cls": "table_classification_model_dir",
    "RT-DETR-L_wired_table_cell_det": "wired_table_cells_detection_model_dir",
    "RT-DETR-L_wireless_table_cell_det": "wireless_table_cells_detection_model_dir",
}

MODEL_NAMES = list(MODEL_TO_KWARG.keys())


# ---------------------------------------------------------------------------
# download helpers
# ---------------------------------------------------------------------------

def _download_models_into(out_dir: Path) -> dict:
    """Use PaddleOCR's built-in downloader to fetch all default models.

    Instructs ``paddlex`` to download and cache the standard PPStructureV3
    sub-models into ``out_dir``. Returns a manifest dict.
    """
    import os as _os
    _os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(out_dir.parent))

    from paddleocr import PPStructureV3
    import time as _time

    print("Triggering model download via PPStructureV3 pipeline creation...",
          file=sys.stderr)
    t0 = _time.time()
    PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
    )
    elapsed = _time.time() - t0
    print(f"  Pipeline created in {elapsed:.1f}s", file=sys.stderr)

    cache_dir = Path(_os.environ["PADDLE_PDX_CACHE_HOME"]) / "official_models"
    if not cache_dir.is_dir():
        raise RuntimeError(
            f"Expected model cache at {cache_dir} but it does not exist. "
            "The pipeline may have downloaded models to a different location."
        )

    import shutil
    for model_dir in sorted(cache_dir.iterdir()):
        if model_dir.is_dir():
            dest = out_dir / model_dir.name
            if not dest.exists():
                shutil.copytree(model_dir, dest)
                print(f"  Copied {model_dir.name} -> {dest}", file=sys.stderr)
    return _generate_manifest(out_dir)


def _generate_manifest(out_dir: Path) -> dict:
    """Walk out_dir and compute SHA256 for every file."""
    import hashlib as _hashlib
    manifest_models = []
    total_bytes = 0
    for model_dir in sorted(out_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        files_info = {}
        model_bytes = 0
        for fpath in sorted(model_dir.rglob("*")):
            if fpath.is_file():
                sz = fpath.stat().st_size
                model_bytes += sz
                sha = _hashlib.sha256(fpath.read_bytes()).hexdigest()
                rel = str(fpath.relative_to(model_dir))
                files_info[rel] = {"size_bytes": sz, "sha256": sha}
        total_bytes += model_bytes
        manifest_models.append({
            "name": model_dir.name,
            "local_path": str(model_dir),
            "total_size_bytes": model_bytes,
            "files": files_info,
        })
    return {
        "schema_version": 2,
        "tool": "photo-to-html download_paddle_models",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_size_bytes": total_bytes,
        "model_count": len(manifest_models),
        "models": manifest_models,
    }


def verify_only(out_dir: Path) -> int:
    """Verify manifest.json against the on-disk model tree."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest.json missing in {out_dir}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for model in manifest.get("models", []):
        root = Path(model["local_path"])
        for file_name, info in model["files"].items():
            fp = root / file_name
            if not fp.exists():
                errors.append(f"MISSING: {fp}")
                continue
            if fp.stat().st_size != info["size_bytes"]:
                errors.append(f"SIZE: {fp} ({fp.stat().st_size} != {info['size_bytes']})")
                continue
            actual_sha = hashlib.sha256(fp.read_bytes()).hexdigest()
            if actual_sha != info["sha256"]:
                errors.append(f"SHA256: {fp}")

    if errors:
        print(f"verify: {len(errors)} issues:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"verify: OK — {len(manifest['models'])} model directories, all checksums match.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--out-dir",
                    default=str(Path(__file__).resolve().parent.parent / "models"),
                    help="where to write the portable model tree (default: photo-to-html/models/)")
    ap.add_argument("--verify", metavar="DIR",
                    help="verify an existing model directory instead of downloading")
    ap.add_argument("--manifest-only", action="store_true",
                    help="skip downloads and only emit manifest.json for the current tree")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()

    if args.verify:
        return verify_only(Path(args.verify).resolve())

    out_dir.mkdir(parents=True, exist_ok=True)

    if args.manifest_only:
        manifest = _generate_manifest(out_dir)
    else:
        manifest = _download_models_into(out_dir)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("-" * 72)
    print(f"Wrote manifest: {manifest_path}")
    print(f"Total: {manifest['total_size_bytes'] / 1024 / 1024:.1f} MB "
          f"across {manifest['model_count']} models")
    print(f"To use offline: export PH2H_MODELS_DIR={out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())