# Layout & CSS patterns for slide reconstruction

Copy-paste recipes for the structures that appear on almost every corporate /
academic slide. All assume the fixed 1280×720 absolute-positioned canvas from
`html_canvas_template.html`.

## 0. Coordinate workflow

```
scale = 1280 / cleaned_image_width
left  = round(x_px * scale);  top = round(y_px * scale)   # same scale for y (16:9 in = 16:9 out)
```
Measure from the cleaned image (crop & view regions when eyeballing isn't
enough). Don't convert iteratively from the render — always go back to source
measurements when something is off by more than a few px.

## 1. Header-bar section (colored title bar + bordered body)

```html
<div class="bar"   style="left:404px;top:192px;width:400px;font-size:11px;padding:4px 0">SECTION TITLE</div>
<div class="panel" style="left:404px;top:213px;width:400px;height:150px;border-top:none;border-radius:0 0 7px 7px"></div>
<!-- content positioned absolutely INSIDE the same coordinate space, not nested -->
```
Keeping content as siblings (not children) of the panel makes the verify-fix
loop local — you can nudge the panel without reflowing its contents.

## 2. Icon-left card (top-row capability cards)

```html
<div class="card top" style="left:172px;top:86px;width:248px;height:92px">
  <div class="ic"><svg ...></svg></div>
  <div><h4>CARD TITLE</h4><ul><li>bullet</li>...</ul></div>
</div>
```
```css
.top{display:flex;align-items:flex-start;gap:8px;padding:8px 9px}
.top .ic{flex:none;width:52px;display:flex;align-items:center;justify-content:center;padding-top:4px}
.card ul{list-style:none;font-size:9px;line-height:1.45}
.card ul li::before{content:"•";margin-right:4px}
```
(Flex *inside* a fixed-size card is fine; it's page-level flex we avoid.)

## 3. Step → arrow → step chains (workflows, feedback loops)

Use absolutely positioned fixed-width steps and `→` text arrows between them —
not SVG connector lines — exactly as in photo-to-pptx:

```html
<div class="step" style="left:858px;top:228px"><svg .../><div class="lbl">Design</div></div>
<div class="arrow" style="left:932px;top:240px">&rarr;</div>
```
```css
.step{position:absolute;width:74px;text-align:center}
.step .lbl{font-size:8.5px;font-weight:700;line-height:1.2;margin-top:2px}
```

## 4. Feedback-loop return path

A three-segment SVG polyline with an explicit triangle arrowhead:

```html
<svg style="position:absolute;left:870px;top:298px" width="346" height="26" viewBox="0 0 346 26">
  <path d="M340 2 v12 h-334 v-8" fill="none" stroke="var(--primary)" stroke-width="1.6"/>
  <path d="M6 6 l-3.6 6 h7.2 z" fill="var(--primary)"/>  <!-- arrowhead -->
</svg>
```

## 5. Dashed container with interrupting title

Put the title in a background-colored chip *overlapping* the dashed border —
in browsers (unlike PowerPoint) this renders reliably:

```html
<div class="wf" style="left:172px;top:614px;width:874px;height:90px"></div>      <!-- dashed box -->
<div class="wf-title" style="left:480px;top:608px">AUTONOMOUS WORKFLOW</div>
```
```css
.wf{position:absolute;border:1.6px dashed var(--border);border-radius:8px;background:#fcfaff}
.wf-title{position:absolute;font-weight:800;color:var(--primary);background:#fcfaff;padding:0 8px}
```

## 6. Double-headed / vertical arrows between regions

Unicode beats SVG for these: `&#x21D4;` ⇔, `&#x2195;` ↕, `&#x2191;` ↑, `&#x25B6;`/`&#x25C0;`
for dashed-line endpoints. Position absolutely, size with `font-size`.

## 7. Legend rows

Inline-flex with color swatches:

```html
<div class="cap" style="left:510px;top:308px;display:flex;align-items:center;gap:8px">
  <span style="width:11px;height:11px;border-radius:50%;background:var(--pin)"></span> pin
  <span style="width:46px;height:15px;background:#cfcfcf;margin-left:18px"></span> Gap
</div>
```

## 8. Outcome/checklist side panels

Title bar + icon rows. **The #1 clipping victim** — 6+ rows near the slide
bottom routinely collide with a bottom banner. Compute: `bar(≈19px) +
n_rows × (font*1.2 + 2*pad)` and verify it ends above the banner top; compact
`padding`/`font-size` first, move the panel up second.

## 9. Footers

```html
<div class="foot date">May 9, 2026</div>
<div class="foot center">Conference @ Venue 2026</div>
<div class="foot num">14</div>
```
```css
.foot{position:absolute;bottom:18px;font-size:16px;color:#5a5a5a}
.foot.date{left:54px}.foot.center{left:0;right:0;text-align:center}.foot.num{right:46px}
```

## 10. Bottom banner

```html
<div class="banner">KEY MESSAGE = TAKEAWAY</div>
```
```css
.banner{position:absolute;left:190px;right:36px;bottom:12px;background:var(--primary);
  color:#fff;text-align:center;font-weight:800;padding:6px 0;border-radius:4px}
```

## Font-size ladder that matches typical slides at 1280×720

| Role | px |
|---|---|
| Slide title | 30–38 |
| Section header bars | 11–12 bold |
| Card titles | 10.5–11.5 bold |
| Body bullets | 8.5–9.5 |
| Step labels | 8–8.5 bold |
| Footers | 14–16 |

When source text looks bigger/smaller, trust measured proportions over this table.
