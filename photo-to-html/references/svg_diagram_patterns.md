# SVG recipes for technical-diagram redraw

Patterns proven on real conference slides (EDA / routing / multi-physics).
Each SVG lives in its own local `viewBox` and is positioned absolutely.
If `photo-to-pptx` is installed, its `references/svg_icon_library.md`
(~20 engineering icons) applies here unchanged — SVG is SVG.

## General rules

- `width`/`height` attributes = viewBox dimensions (or exact same ratio);
  mismatched ratios silently letterbox and shift content.
- Stroke for outlines (`fill="none"`), fill for solids. A "blob" icon is
  almost always a path that should have been stroked.
- Arrowheads: explicit triangles (`<path d="M.. l-3.5 6 h7 z"/>`), never arc
  tricks — arc `sweep-flag` mistakes are the top icon bug.
- Group repeated structures with `<g transform="translate(..)">` so rows of
  similar elements share one local origin each.
- Text inside SVG: set the math serif stack at the `svg text` CSS level.

## 1. Channel / grid routing diagram (gaps, pads, nets, pins)

Layered painter's order: frame → gap rows → pads → nets → pins on top.

```svg
<rect x="38" y="2" width="280" height="160" fill="#fff" stroke="#444" stroke-width="1.5"/>
<g fill="#cfcfcf">  <!-- gap rows -->
  <rect x="44" y="22" width="268" height="16"/> ...
</g>
<g fill="#3d3023">  <!-- pads: dark squares in a grid -->
  <rect x="78" y="6" width="34" height="34"/> ...
</g>
<g stroke="#5533cc" fill="none" stroke-linecap="round">   <!-- nets, varying width -->
  <path d="M60 30 L150 56 L230 18" stroke-width="2"/>
  <path d="M190 14 L208 96" stroke-width="7"/>            <!-- wide net -->
</g>
<g fill="#c0431f">  <!-- pins last, on top -->
  <circle cx="60" cy="30" r="4.5"/> ...
</g>
```
Net widths in the source encode wire width — reproduce the variation
(thin 1.6 → thick 8), it's semantic.

## 2. Routed channel (H trunks + V segments)

Same layering; horizontal trunks as blue `<rect>`s of varying height,
vertical routing as orange `<rect>`s, terminal pins as circles at rect ends.

## 3. Dimension arrows & brackets (w(n), w_g, offsets)

```svg
<g stroke="#222" stroke-width="1.4" fill="#222">
  <line x1="318" y1="10" x2="318" y2="130"/>
  <path d="M318 10  l-3.5 6 h7 z"/>   <!-- top arrowhead -->
  <path d="M318 130 l-3.5 -6 h7 z"/>  <!-- bottom arrowhead -->
</g>
<text x="328" y="78" font-size="20" font-style="italic">w</text>
<text x="341" y="84" font-size="14">g</text>   <!-- manual subscript: smaller, +6y -->
```
Single-direction offset arrows: one line + one head. Tiny spacing arrows inside
dashed envelopes: just two short lines with 3px heads.

## 4. Trunk-in-envelope (dashed bbox + solid bar + spacing ticks)

```svg
<g transform="translate(36,0)">
  <rect x="0" y="0" width="180" height="34" fill="none" stroke="#555"
        stroke-width="1.2" stroke-dasharray="4 3"/>
  <rect x="4" y="8" width="172" height="16" fill="#5533cc"/>
  <line x1="90" y1="1" x2="90" y2="7" stroke="#222"/>
  <line x1="90" y1="25" x2="90" y2="33" stroke="#222"/>
</g>
```

## 5. Heatmap thumbnail

```svg
<defs><linearGradient id="heat" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#1ec84a"/><stop offset=".35" stop-color="#f8e93a"/>
  <stop offset=".65" stop-color="#f59f1d"/><stop offset="1" stop-color="#e23a1e"/>
</linearGradient></defs>
<rect x="2" y="2" width="88" height="30" fill="url(#heat)" rx="2"/>
<rect x="34" y="9" width="28" height="16" fill="#c21807" opacity=".85"/>  <!-- hotspot -->
```
Gradient `id`s must be unique per page — prefix them (`#heat1`, `#warp2`) when
a slide has several.

## 6. 3D warpage / surface thumbnail

A wavy closed path filled with a blue→green→yellow→red gradient + a darker
top-edge stroke for depth:

```svg
<path d="M4 24 q14 -16 30 -6 q16 10 30 -4 q14 -12 28 0 l0 8
         q-14 8 -28 2 q-16 -8 -30 2 q-14 8 -30 2 z" fill="url(#warp)"/>
<path d="M4 24 q14 -16 30 -6 q16 10 30 -4 q14 -12 28 0" fill="none" stroke="#1e3a8a"/>
```

## 7. Signal waveform

```svg
<path d="M4 18 q5 -14 10 0 t10 0 t10 0 q5 -10 10 -2 t10 2 q5 -8 10 0 t10 0"
      fill="none" stroke="var(--primary)" stroke-width="1.6"/>
```
`q` + `t` (smooth-continue) gives an organic multi-frequency look in one path.

## 8. Chip / wafer / layout icons (most-reused engineering trio)

Chip: rounded rect + inner rect + pin stubs on all four sides.
Wafer: circle + clipped row/column grid lines.
Layout: outer rect + 4–5 colored inner rects (placement blocks) + short route stubs.
(Full versions in photo-to-pptx `svg_icon_library.md`.)

## 9. Big block arrow (between figure stages)

```svg
<path d="M22 0 h16 v20 h12 L30 44 L10 20 h12 z" fill="#4a3f35"/>
```

## 10. Stylized organization mark (logo placeholder, rule [4])

Geometric hint + live-text name. Example, a ribbon-S mark:

```svg
<path d="M6 2 H30 C18 8 14 14 28 20 H6 C16 14 18 8 6 2 Z" fill="#2b2b2b"/>
<path d="M4 20 H28 C16 26 14 32 28 38 H4 C16 32 16 26 4 20 Z" fill="#2b2b2b" opacity=".85"/>
```
Don't chase exact trademark reproduction; recognizable-at-a-glance is the bar.
