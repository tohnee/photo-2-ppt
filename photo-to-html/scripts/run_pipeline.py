#!/usr/bin/env python3
"""
End-to-end closed loop: one photo in, a reconstructed slide out.

    photo.jpg  ->  extract_slide.py   ->  slide_clean.jpg
               ->  ocr_extract.py     ->  spec.json (+ overlay)
               ->  assemble_html.py   ->  slide.html      (auto mode)
               +/- assemble_pptx.py   ->  slide.pptx      (auto mode, if requested)
               ->  render_verify.py   ->  slide_render.png (optional check)

Modes:
  auto  (default)  fully hands-off; non-text regions are faithful photo crops.
  spec             stop after spec.json + overlay; hand off to the skill's
                   vector path where Claude redraws diagrams as inline SVG
                   (highest fidelity). Prints next-step guidance.

Usage:
    python run_pipeline.py photo.jpg --out-dir out --format html
    python run_pipeline.py photo.jpg --out-dir out --format both
    python run_pipeline.py photo.jpg --out-dir out --mode spec
    python run_pipeline.py photo.jpg --out-dir out --device gpu \
        --det-model PP-OCRv6_medium_det --rec-model PP-OCRv6_medium_rec
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PPTX_ASSEMBLER = os.path.normpath(
    os.path.join(HERE, "..", "..", "photo-to-pptx", "scripts", "assemble_pptx.py"))


def run(cmd, **kw):
    print("  $ " + " ".join(cmd), file=sys.stderr)
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        print(f"  ! step failed (exit {r.returncode})", file=sys.stderr)
        print("  Intermediate artifacts (slide_clean.jpg, spec.json) are preserved "
              "in the output directory — retry the failed step manually:", file=sys.stderr)
        sys.exit(r.returncode)


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
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    clean = os.path.join(args.out_dir, "slide_clean.jpg")
    spec = os.path.join(args.out_dir, "spec")
    py = sys.executable

    print("[1/4] extract", file=sys.stderr)
    run([py, os.path.join(HERE, "extract_slide.py"), args.photo,
         "--output", clean, "--ratio", args.ratio])

    print("[2/4] ocr (PP-StructureV3 / PP-OCRv6)", file=sys.stderr)
    ocr_cmd = [py, os.path.join(HERE, "ocr_extract.py"), clean, "--out", spec]
    for flag, val in (("--device", args.device), ("--det-model", args.det_model),
                      ("--rec-model", args.rec_model), ("--lang", args.lang)):
        if val:
            ocr_cmd += [flag, val]
    run(ocr_cmd)

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
        run(cmd)
    if args.format in ("pptx", "both"):
        if not os.path.isfile(PPTX_ASSEMBLER):
            print(f"  ! pptx assembler not found at {PPTX_ASSEMBLER} "
                  "(is photo-to-pptx installed?)", file=sys.stderr)
            sys.exit(3)
        out_pptx = os.path.join(args.out_dir, "slide.pptx")
        cmd = [py, PPTX_ASSEMBLER, spec + ".json", "--out", out_pptx]
        if args.no_white_balance:
            cmd.append("--no-white-balance")
        run(cmd)

    print("[4/4] verify", file=sys.stderr)
    if args.verify and args.format in ("html", "both"):
        rv = os.path.join(HERE, "render_verify.py")
        if os.path.isfile(rv):
            run([py, rv, os.path.join(args.out_dir, "slide.html"),
                 "--ref", clean], env={**os.environ,
                 "PLAYWRIGHT_BROWSERS_PATH": "/opt/pw-browsers"})
    else:
        print("  (skipped; pass --verify to render-check HTML)", file=sys.stderr)

    print("\n[done] auto mode. Outputs in:", os.path.abspath(args.out_dir),
          file=sys.stderr)


if __name__ == "__main__":
    main()
