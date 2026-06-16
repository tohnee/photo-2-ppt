# Math notation in plain HTML/CSS (no MathJax/KaTeX)

Slides with set notation, scripts, and dimensioned variables can be typeset
faithfully with three tools: a serif math font stack, Unicode math letters,
and one flexbox trick. Avoid KaTeX/MathJax — they break the zero-dependency,
single-file guarantee, and slide math is rarely complex enough to need them.

## Base classes (already in the canvas template)

```css
.math  {font-family:"STIX Two Math","Cambria Math","Times New Roman",serif;font-style:italic}
.mathup{font-family:"STIX Two Math","Cambria Math","Times New Roman",serif;font-style:normal}
sub,sup{font-size:0.62em}
.ss{display:inline-flex;flex-direction:column;vertical-align:-0.45em;
    line-height:0.95;font-size:0.6em;font-style:normal;margin-left:1px}
.ss i{font-style:italic}
```

Conventions: variables italic (`.math`), operators/braces/brackets upright
(`.mathup`), function names upright.

## The stacked-script pattern (THE classic failure)

`{gᵢ}ᵢ₌₁ᴹ` written naively as `<sub>i=1</sub><sup>M</sup>` renders the sub and
sup **side by side**, not stacked. Use the `.ss` column flexbox:

```html
<span class="math">G</span> <span class="mathup">= {</span><span class="math">g<sub>i</sub></span><span class="mathup">}</span><span class="ss mathup"><span><i>M</i></span><span><i>i</i>=1</span></span>
```

Order inside `.ss`: superscript line first (top), subscript line second.
Tune `vertical-align` between −0.35em and −0.55em per font.

## Unicode pickers

| Need | Char | Codepoint |
|---|---|---|
| script G (gap-assignment fn) | 𝒢 | U+1D4A2 |
| script S (offset fn) | 𝒮 | U+1D4AE |
| script N, L, F, H | 𝒩 𝓛 ℱ ℋ | U+1D4A9, U+1D4DB, U+2131, U+210B |
| element of | ∈ | U+2208 |
| real numbers | ℝ | U+211D |
| times, cdot | × ⋅ | U+00D7, U+22C5 |
| arrows | → ⇒ ↦ | U+2192, U+21D2, U+21A6 |
| inequality | ≤ ≥ ≠ ≈ | — |
| sum / product | ∑ ∏ | U+2211, U+220F (use .ss for limits) |

Renderer check: in Stage 4, confirm script letters didn't fall back to tofu.
The Times fallback in the stack covers ∈/≤ everywhere; Plane-1 script letters
(𝒢, 𝒮) need a math/Noto font — present in Chromium on Linux, but if a target
viewer lacks it, fall back to italic serif capitals: `<i class="math">G</i>`
with a visual distinction (e.g., a calligraphic webfont is NOT an option;
prefer a different color or accept plain italic).

## Inside SVG diagrams

`<text font-style="italic">` + manual subscripts (smaller `font-size`, +6px y):

```svg
<text x="14" y="36" font-size="20" font-style="italic">g</text>
<text x="24" y="42" font-size="13">3</text>
```

Plane-1 chars work in SVG `<text>` too: `<text font-style="italic">𝒢(t)</text>`.

## Brackets/intervals

Plain text with `.mathup`: `[0, <span class="math">w<sub>g</sub></span>]`.
For oversized delimiters around tall content, scale a bracket char with
`transform:scaleY(1.6)` on an inline-block span rather than hunting for
Unicode size variants.

## When to escalate to KaTeX after all

Only if the slide is *math-dense* (multi-line derivations, fractions inside
fractions, matrices). Then vendor katex.min.css + fonts inline is heavy;
prefer rendering each formula to standalone SVG offline (`katex` CLI or
MathJax-node) and embedding the SVG — keeps the single-file property.
