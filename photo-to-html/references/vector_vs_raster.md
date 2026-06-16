# Vector vs Raster: the hybrid decision

The whole value of HTML reconstruction is that *almost everything on a slide is
redrawable as resolution-independent vector content*. A photographed screen is
blurry, color-cast, and moiré-prone — so a raster crop is the **last resort**,
not a convenience. Default hard toward vector.

## Decision tree (apply per visual element)

```
[1] Geometric AND regular?  structure is the content: grids, block diagrams,
    feedback loops, charts with few elements, logic & circuit symbols, tables
        → INLINE SVG (or pure HTML/CSS boxes when it's just rectangles+text)

[1b] Geometric but IRREGULAR / instance-dense?  the content is the exact
     instance data: random net topologies, hand-placed example geometry,
     dozens of elements whose individual positions matter
        → RASTER CROP (--white-balance). Redrawing means measuring every
          element; anything less is a visible detail mismatch.

[2] False-color field?  heatmaps, warpage/stress surfaces, FEM/CFD renders
        → as a small thumbnail where only the gist matters: stylized SVG
          gradient. If the field pattern itself matters, or the SVG reads
          "cartoonish" on first render: crop.

[3] Continuous-tone, genuinely un-redrawable?  photographs, screenshots,
    lit 3D renders, dense scatter plots, micrographs
        → RASTER CROP from the *cleaned* image, base64 data-URI
          (scripts/crop_region.py). Never link external files.

[4] Third-party logo / org mark?
        → CROP WITH KEYING: --key-light 232 → original mark, transparent
          background. Beats any hand-drawn approximation. Placeholder
          mark + text name only if keying fails (busy background).
```

## The escalation rule

A vector redraw of a complex region that still mismatches after **one** fix
iteration gets replaced by a crop. Symptoms that trigger it: topology
differs (lines connect different points than the original), element counts
differ, positions are "inspired by" rather than measured. The crop *is* the
original — past one iteration, polishing SVG is effort spent increasing the
divergence budget.

## Worked examples

| Element seen in photo | Route | Why |
|---|---|---|
| Empty channel template (gaps + pad grid, no nets) | [1] SVG | regular structure; redraw is *sharper than the photo* |
| Channel-routing example with specific nets/pins | [1b] crop | net topology IS the content; a redraw connects the wrong points |
| Trunk-assignment example figure (hand-placed offsets) | [1b] crop | each offset is instance data |
| Single-gap *schematic* with dimension labels (T(n), w_g) | [1] SVG | schematic, few elements, labels must be crisp text |
| Thermal heatmap thumbnail in a "THERMAL" column | [2] | gradient SVG if gist suffices; crop if the field pattern matters |
| 3D warpage surface thumbnail | [2] | same judgment; lit 3D render usually → crop |
| Sine-ish signal-integrity waveform | [1] SVG `q`/`t` path | three quadratic segments suffice |
| Conference room photo / speaker headshot | [3] crop | not redrawable |
| Dense GUI screenshot inside the slide | [3] crop | redrawing a GUI is a project of its own |
| Math formula | text, never raster | see math_notation.md |
| Org logos (OpenAI knot, university marks, …) | [4] keyed crop | original mark on transparent bg |

## Raster-crop mechanics

1. Identify the bbox in **cleaned-image pixel coordinates**. Always crop &
   view a generous window first to confirm — eyeballed coordinates are
   routinely off by 50-100px (re-locate, don't guess-adjust).
2. `python scripts/crop_region.py slide_clean.jpg --bbox x0,y0,x1,y1 --white-balance`
   prints a ready `<img>` tag with a base64 data-URI.
3. Fitting into an existing layout: when the reconstruction's layout slots
   differ slightly from original proportions, size the crop to **fit the
   slot** (preserve aspect, contain) rather than using original-coordinate
   geometry — consistency with neighbors beats absolute coordinates.
4. Stage 4 checks both directions: a crop that looks muddy where content is
   borderline-geometric → redraw; an SVG that mismatches a complex original
   → crop (escalation rule).

## Blending: making crops invisible on a vector page

| Problem | Fix |
|---|---|
| Crop tile has a gray/colored cast vs page white | `--white-balance` (per-channel levels, p88→253) |
| Brightness gradient across the crop (vignette, uneven projector) | `--flat-field` (divide by blurred bg estimate). Caution: distorts solid color fields larger than the blur radius — fine for line art / thin geometry |
| Logo/mark needs transparent background | `--key-light 232`. It flat-fields internally first — **global luminance keying fails on vignetted corners** (dark corners stay opaque as a gray box). Alpha is keyed on the flattened image; colors come from the original |
| Keyed mark has a halo | lower threshold (228) or tighten ramp; check after Stage-4 render with pixel sampling, not just eyeballing |

## Budget note

Base64 crops are the only thing that grows file size (≈1.37× the PNG bytes).
Keep crops few and small; downscale with `--max-width` — a photographed screen
has no detail beyond ~2× its display size anyway.
