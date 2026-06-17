#!/usr/bin/env python3
"""
End-to-end closed loop: one photo in, a reconstructed slide out.

    photo.jpg  ->  extract_slide.py   ->  slide_clean.jpg
               ->  ocr_extract.py     ->  spec.json (+ overlay)
               ->  assemble_html.py   ->  slide.html      (auto mode, html)
               ->  assemble_pptx.py   ->  slide.pptx      (auto mode, pptx)
               ->  render_verify.py   ->  slide_render.png (optional check)

Modes:
  auto  (default)  fully hands-off; non-text regions are faithful photo crops.
  spec             stop after spec.json + overlay; hand off to the skill's
                   vector path where Claude redraws diagrams as inline SVG
                   (highest fidelity). Prints next-step guidance.

Usage:
    python run_pipeline.py photo.jpg --out-dir out --format html
    python run_pipeline.py photo.jpg --out-dir out --format pptx
    python run_pipeline.py photo.jpg --out-dir out --format both
    python run_pipeline.py photo.jpg --out-dir out --mode spec
    python run_pipeline.py photo.jpg --out-dir out --device gpu \
        --det-model PP-OCRv5_server_det --rec-model PP-OCRv5_server_rec

Offline model bundle:
    If photo-to-html/models/ exists alongside this script, PH2H_MODELS_DIR
    is set automatically so ocr_extract.py uses local weights without any
    network access. Override with --models-dir or PH2H_MODELS_DIR env var.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(HERE, ".."))
DEFAULT_MODELS_DIR = os.path.join(PROJECT_ROOT, "models")


def run(cmd, env=None, **kw):
    print("  $ " + " ".join(cmd), file=sys.stderr)
    r = subprocess.run(cmd, env=env, **kw)
    if r.returncode != 0:
        print(f"  ! step failed (exit {r.returncode})", file=sys.stderr)
        print("  Intermediate artifacts (slide_clean.jpg, spec.json) are preserved "
              "in the output directory — retry the failed step manually:", file=sys.stderr)
        sys.exit(r.returncode)


def resolve_models_dir(cli_models_dir):
    """Determine the models directory to use, in priority order:
    1. --models-dir CLI flag
    2. PH2H_MODELS_DIR env var
    3. photo-to-html/models/ alongside this script
    Returns None if no local model bundle is available.
    """
    if cli_models_dir:
        return cli_models_dir if os.path.isdir(cli_models_dir) else None
    env_val = os.environ.get("PH2H_MODELS_DIR")
    if env_val and os.path.isdir(env_val):
        return env_val
    if os.path.isdir(DEFAULT_MODELS_DIR):
        return DEFAULT_MODELS_DIR
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--mode", choices=["auto", "spec"], default="auto")
    ap.add_argument("--format", choices=["html", "pptx", "both"], default="html")
    ap.add_argument("--ratio", default="16:9", choices=["16:9", "4:3", "auto"])
    ap.add_argument("--device", default=None)
    ap.add_argument("--det-model", default=None)
    ap.add_argument("--rec-model", default=None)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--no-white-balance", action="store_true")
    ap.add_argument("--verify", action="store_true", help="render HTML to PNG at the end")
    ap.add_argument("--models-dir", default=None,
                    help="path to offline model bundle (default: auto-detect photo-to-html/models/)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    clean = os.path.join(args.out_dir, "slide_clean.jpg")
    spec = os.path.join(args.out_dir, "spec")
    py = sys.executable

    # Resolve offline models directory and propagate to child processes
    models_dir = resolve_models_dir(args.models_dir)
    child_env = os.environ.copy()
    if models_dir:
        child_env["PH2H_MODELS_DIR"] = models_dir
        print(f"[offline] using models from {models_dir}", file=sys.stderr)
    else:
        print("[online] no local model bundle found; OCR will download weights "
              "on first use (requires network)", file=sys.stderr)

    print("[1/4] extract", file=sys.stderr)
    run([py, os.path.join(HERE, "extract_slide.py"), args.photo,
         "--output", clean, "--ratio", args.ratio], env=child_env)

    print("[2/4] ocr (PP-StructureV3 / PP-OCRv5)", file=sys.stderr)
    ocr_cmd = [py, os.path.join(HERE, "ocr_extract.py"), clean, "--out", spec]
    for flag, val in (("--device", args.device), ("--det-model", args.det_model),
                      ("--rec-model", args.rec_model), ("--lang", args.lang)):
        if val:
            ocr_cmd += [flag, val]
    run(ocr_cmd, env=child_env)

    if args.mode == "spec":
        print("\n[done] spec mode.", file=sys.stderr)
        print(f"  spec:    {spec}.json", file=sys.stderr)
        print(f"  overlay: {spec}.overlay.png", file=sys.stderr)
        print("  Next (vector path): open the cleaned image + overlay, and rebuild\n"
              "  per the skill — text/formulas/tables are pre-extracted in the spec;\n"
              "  redraw figure-type blocks as inline SVG for full vector fidelity.",
              file=sys.stderr)
        return

    print("[3/4] assemble", file=sys.stderr)
    if args.format in ("html", "both"):
        out_html = os.path.join(args.out_dir, "slide.html")
        cmd = [py, os.path.join(HERE, "assemble_html.py"), spec + ".json",
               "--out", out_html]
        if args.no_white_balance:
            cmd.append("--no-white-balance")
        run(cmd, env=child_env)
    if args.format in ("pptx", "both"):
        out_pptx = os.path.join(args.out_dir, "slide.pptx")
        pptx_assembler = os.path.join(HERE, "assemble_pptx.py")
        if not os.path.isfile(pptx_assembler):
            print(f"  ! pptx assembler not found at {pptx_assembler}",
                  file=sys.stderr)
            sys.exit(3)
        cmd = [py, pptx_assembler, spec + ".json", "--out", out_pptx]
        if args.no_white_balance:
            cmd.append("--no-white-balance")
        run(cmd, env=child_env)

    print("[4/4] verify", file=sys.stderr)
    if args.verify and args.format in ("html", "both"):
        rv = os.path.join(HERE, "render_verify.py")
        if os.path.isfile(rv):
            run([py, rv, os.path.join(args.out_dir, "slide.html"),
                 "--ref", clean], env=child_env)
    else:
        print("  (skipped; pass --verify to render-check HTML)", file=sys.stderr)

    print("\n[done] auto mode. Outputs in:", os.path.abspath(args.out_dir),
          file=sys.stderr)


if __name__ == "__main__":
    main()
