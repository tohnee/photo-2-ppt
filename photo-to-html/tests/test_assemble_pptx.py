"""Tests for assemble_pptx.py — table parsing, color sampling, PPTX generation."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
import numpy as np
from PIL import Image


# ── parse_table_html ─────────────────────────────────────────────────────────

from assemble_pptx import parse_table_html

class TestParseTableHtml:
    def test_simple_table(self):
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
        rows = parse_table_html(html)
        assert rows == [["A", "B"], ["C", "D"]]

    def test_table_with_th(self):
        html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>v1</td><td>v2</td></tr></table>"
        rows = parse_table_html(html)
        assert rows == [["H1", "H2"], ["v1", "v2"]]

    def test_table_with_attributes(self):
        html = '<table class="x"><tr><td colspan="2">merged</td></tr></table>'
        rows = parse_table_html(html)
        assert rows == [["merged"]]

    def test_table_with_whitespace(self):
        html = "<table><tr><td>  spaced  </td></tr></table>"
        rows = parse_table_html(html)
        assert rows == [["spaced"]]

    def test_table_with_nested_tags(self):
        html = "<table><tr><td><b>bold</b> text</td></tr></table>"
        rows = parse_table_html(html)
        assert rows == [["bold text"]]

    def test_empty_string_returns_none(self):
        assert parse_table_html("") is None

    def test_no_table_returns_none(self):
        assert parse_table_html("<div>not a table</div>") is None

    def test_malformed_returns_none(self):
        assert parse_table_html("<table></table>") is None

    def test_uneven_rows_normalized(self):
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>"
        rows = parse_table_html(html)
        assert rows == [["A", "B"], ["C", ""]]


# ── crop_to_bytes ────────────────────────────────────────────────────────────

from assemble_pptx import crop_to_bytes

class TestCropToBytes:
    def test_returns_png_bytes(self):
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        b = crop_to_bytes(img, (10, 10, 50, 50))
        assert b is not None
        assert b[:8] == b"\x89PNG\r\n\x1a\n"

    def test_empty_bbox_returns_none(self):
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        assert crop_to_bytes(img, (50, 50, 50, 60)) is None

    def test_bbox_outside_image_clamped(self):
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        b = crop_to_bytes(img, (-10, -10, 200, 200))
        assert b is not None

    def test_white_balance_does_not_crash(self):
        img = Image.new("RGB", (100, 100), (0, 0, 0))
        b = crop_to_bytes(img, (10, 10, 50, 50), wb=True)
        assert b is not None


# ── sample_text_color ────────────────────────────────────────────────────────

from assemble_pptx import sample_text_color

class TestSampleTextColor:
    def test_light_bg_dark_text(self):
        img = Image.new("RGB", (200, 40), (245, 245, 245))
        for y in range(12, 28):
            for x in range(10, 190):
                img.putpixel((x, y), (20, 20, 20))
        rgb = sample_text_color(img, (0, 0, 200, 40))
        assert max(rgb) < 100

    def test_dark_bg_light_text(self):
        img = Image.new("RGB", (200, 40), (15, 15, 15))
        for y in range(12, 28):
            for x in range(10, 190):
                img.putpixel((x, y), (240, 240, 240))
        rgb = sample_text_color(img, (0, 0, 200, 40))
        assert min(rgb) > 180

    def test_empty_bbox_returns_default(self):
        img = Image.new("RGB", (200, 40), (200, 200, 200))
        rgb = sample_text_color(img, (0, 0, 0, 0))
        assert rgb == (26, 26, 26)

    def test_sparse_ink_on_bright_background(self):
        """Regression test: thin dark text on a mostly-white bbox must
        still sample as dark ink, not the dominant background color.

        The old percentile-based code returned ~light-gray here because
        >90% of pixels were white, so the 20th-percentile luminance was
        still 255 and `lum <= 255` matched every pixel.
        """
        img = Image.new("RGB", (200, 60), (255, 255, 255))
        # draw a single thin dark line (1px tall) — ~0.5% of the bbox
        for x in range(20, 180):
            img.putpixel((x, 30), (10, 10, 10))
        rgb = sample_text_color(img, (0, 0, 200, 60))
        assert max(rgb) < 80, f"expected dark ink, got {rgb}"


# ── build_pptx ───────────────────────────────────────────────────────────────

class TestBuildPptx:
    @pytest.fixture
    def minimal_spec(self, tmp_path):
        spec_path = tmp_path / "spec.json"
        img_path = tmp_path / "slide.jpg"
        # create a 1280x720 white image with a dark title bar
        img = Image.new("RGB", (1280, 720), (255, 255, 255))
        for y in range(20, 80):
            for x in range(50, 500):
                img.putpixel((x, y), (30, 30, 30))
        img.save(img_path)
        spec = {
            "source_image": str(img_path),
            "image_size": {"width": 1280, "height": 720},
            "canvas": {"width": 1280, "height": 720},
            "scale": 1.0,
            "ocr": {"engine": "PP-StructureV3", "text_backbone": "PP-OCRv5",
                    "schema_source": "test", "det_model": None, "rec_model": None},
            "blocks": [
                {"id": "b0", "type": "title", "bbox": [50, 20, 500, 80],
                 "text": "Hello World", "raw_label": "doc_title", "reading_order": 0},
                {"id": "b1", "type": "text", "bbox": [50, 100, 600, 200],
                 "text": "Some body text here.", "raw_label": "text", "reading_order": 1},
                {"id": "b2", "type": "table", "bbox": [50, 220, 600, 400],
                 "html": "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>",
                 "raw_label": "table", "reading_order": 2},
                {"id": "b3", "type": "figure", "bbox": [50, 420, 600, 600],
                 "text": "", "raw_label": "figure", "reading_order": 3},
                {"id": "b4", "type": "formula", "bbox": [650, 220, 1200, 300],
                 "latex": "E=mc^2", "text": "E=mc^2", "raw_label": "formula",
                 "reading_order": 4},
            ]
        }
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return str(spec_path), str(tmp_path / "out.pptx"), str(img_path)

    def test_generates_valid_pptx(self, minimal_spec):
        from assemble_pptx import build_pptx, load_image
        spec_path, out_pptx, img_path = minimal_spec
        spec = json.loads(open(spec_path).read())
        img = load_image(img_path)
        n_text, n_table, n_picture = build_pptx(spec, img, out_pptx)
        assert os.path.isfile(out_pptx)
        assert os.path.getsize(out_pptx) > 0
        # 2 text blocks (title + text), 1 table, 2 pictures (figure + formula)
        assert n_text == 2
        assert n_table == 1
        assert n_picture == 2

    def test_pptx_openable_by_python_pptx(self, minimal_spec):
        from pptx import Presentation
        from assemble_pptx import build_pptx, load_image
        spec_path, out_pptx, img_path = minimal_spec
        spec = json.loads(open(spec_path).read())
        img = load_image(img_path)
        build_pptx(spec, img, out_pptx)
        prs = Presentation(out_pptx)
        assert len(prs.slides) == 1
        slide = prs.slides[0]
        # 2 text + 1 table + 2 pictures = 5 shapes
        assert len(slide.shapes) == 5

    def test_text_content_preserved(self, minimal_spec):
        from pptx import Presentation
        from assemble_pptx import build_pptx, load_image
        spec_path, out_pptx, img_path = minimal_spec
        spec = json.loads(open(spec_path).read())
        img = load_image(img_path)
        build_pptx(spec, img, out_pptx)
        prs = Presentation(out_pptx)
        slide = prs.slides[0]
        all_text = ""
        for shape in slide.shapes:
            if shape.has_text_frame:
                all_text += shape.text_frame.text + " "
        assert "Hello World" in all_text
        assert "Some body text here." in all_text

    def test_table_content_preserved(self, minimal_spec):
        from pptx import Presentation
        from assemble_pptx import build_pptx, load_image
        spec_path, out_pptx, img_path = minimal_spec
        spec = json.loads(open(spec_path).read())
        img = load_image(img_path)
        build_pptx(spec, img, out_pptx)
        prs = Presentation(out_pptx)
        slide = prs.slides[0]
        table_shape = None
        for shape in slide.shapes:
            if shape.has_table:
                table_shape = shape
                break
        assert table_shape is not None
        tbl = table_shape.table
        assert tbl.cell(0, 0).text == "A"
        assert tbl.cell(0, 1).text == "B"
        assert tbl.cell(1, 0).text == "C"
        assert tbl.cell(1, 1).text == "D"

    def test_slide_size_matches_canvas(self, minimal_spec):
        from pptx import Presentation
        from assemble_pptx import build_pptx, load_image
        spec_path, out_pptx, img_path = minimal_spec
        spec = json.loads(open(spec_path).read())
        img = load_image(img_path)
        build_pptx(spec, img, out_pptx)
        prs = Presentation(out_pptx)
        # 16:9 aspect ratio
        ratio = prs.slide_width / prs.slide_height
        assert 1.7 < ratio < 1.8  # 16/9 ≈ 1.778

    def test_unparseable_table_falls_back_to_picture(self, tmp_path):
        """Table block with unparseable HTML should become a picture crop."""
        from assemble_pptx import build_pptx, load_image
        spec_path = tmp_path / "spec.json"
        img_path = tmp_path / "slide.jpg"
        out_pptx = str(tmp_path / "out.pptx")
        Image.new("RGB", (1280, 720), (255, 255, 255)).save(img_path)
        spec = {
            "source_image": str(img_path),
            "image_size": {"width": 1280, "height": 720},
            "canvas": {"width": 1280, "height": 720},
            "scale": 1.0,
            "ocr": {"engine": "test", "text_backbone": "test",
                    "schema_source": "test", "det_model": None, "rec_model": None},
            "blocks": [
                {"id": "b0", "type": "table", "bbox": [50, 50, 200, 100],
                 "html": "not a table", "raw_label": "table", "reading_order": 0},
            ]
        }
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        spec = json.loads(spec_path.read_text())
        img = load_image(str(img_path))
        n_text, n_table, n_picture = build_pptx(spec, img, out_pptx)
        assert n_table == 0
        assert n_picture == 1

    def test_empty_text_block_skipped(self, tmp_path):
        """Text block with empty text should be skipped."""
        from assemble_pptx import build_pptx, load_image
        spec_path = tmp_path / "spec.json"
        img_path = tmp_path / "slide.jpg"
        out_pptx = str(tmp_path / "out.pptx")
        Image.new("RGB", (1280, 720), (255, 255, 255)).save(img_path)
        spec = {
            "source_image": str(img_path),
            "image_size": {"width": 1280, "height": 720},
            "canvas": {"width": 1280, "height": 720},
            "scale": 1.0,
            "ocr": {"engine": "test", "text_backbone": "test",
                    "schema_source": "test", "det_model": None, "rec_model": None},
            "blocks": [
                {"id": "b0", "type": "text", "bbox": [50, 50, 200, 100],
                 "text": "   ", "raw_label": "text", "reading_order": 0},
            ]
        }
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        spec = json.loads(spec_path.read_text())
        img = load_image(str(img_path))
        n_text, n_table, n_picture = build_pptx(spec, img, out_pptx)
        assert n_text == 0
