"""Tests for assemble_html.py — white balance, color sampling, HTML generation."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
from PIL import Image

import pytest


# ── white_balance ─────────────────────────────────────────────────────────────

from assemble_html import white_balance

class TestWhiteBalance:
    def test_does_not_crash_on_all_white(self):
        """All-white image must not produce NaN."""
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        out = white_balance(img)
        assert out.size == img.size

    def test_does_not_crash_on_all_black(self):
        """All-black image must not produce NaN."""
        img = Image.new("RGB", (100, 100), (0, 0, 0))
        out = white_balance(img)
        assert out.size == img.size

    def test_single_channel_zero(self):
        """Zero-valued channel must not cause division by zero."""
        img = Image.new("RGB", (100, 100), (0, 200, 200))
        out = white_balance(img)
        assert out.size == img.size

    def test_output_dtype_is_uint8(self):
        img = Image.new("RGB", (50, 50), (100, 150, 200))
        out = white_balance(img)
        arr = np.array(out)
        assert arr.dtype == np.uint8

    def test_values_clipped_to_0_255(self):
        """WB can saturate channels — output must stay in [0, 255]."""
        img = Image.new("RGB", (100, 100), (10, 10, 10))
        out = white_balance(img)
        arr = np.array(out)
        assert arr.min() >= 0
        assert arr.max() <= 255


# ── sample_text_color ────────────────────────────────────────────────────────

from assemble_html import sample_text_color

class TestSampleTextColor:
    def test_light_bg_dark_text(self):
        """White background + dark text — should return a dark hex."""
        img = Image.new("RGB", (200, 40), (245, 245, 245))
        for y in range(12, 28):
            for x in range(10, 190):
                img.putpixel((x, y), (20, 20, 20))
        color = sample_text_color(img, (0, 0, 200, 40))
        assert color.startswith("#")
        assert len(color) == 7
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        assert max(r, g, b) < 100, f"expected dark, got {color}"

    def test_dark_bg_light_text(self):
        """Dark background + light text — should return a light hex."""
        img = Image.new("RGB", (200, 40), (15, 15, 15))
        for y in range(12, 28):
            for x in range(10, 190):
                img.putpixel((x, y), (240, 240, 240))
        color = sample_text_color(img, (0, 0, 200, 40))
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        assert min(r, g, b) > 180, f"expected light, got {color}"

    def test_empty_bbox_returns_default(self):
        img = Image.new("RGB", (200, 40), (200, 200, 200))
        color = sample_text_color(img, (0, 0, 0, 0))
        assert color == "#1a1a1a"

    def test_returns_valid_hex(self):
        img = Image.new("RGB", (200, 40), (128, 128, 128))
        color = sample_text_color(img, (0, 0, 0, 0))
        assert color == "#1a1a1a"


# ── crop_datauri (from assemble_html) ─────────────────────────────────────────

from assemble_html import crop_datauri

class TestCropDatauri:
    def test_returns_base64_data_uri(self):
        img = Image.new("RGB", (300, 200), (128, 128, 128))
        uri = crop_datauri(img, (10, 10, 100, 100))
        assert uri.startswith("data:image/png;base64,")

    def test_empty_bbox_returns_none(self):
        img = Image.new("RGB", (300, 200), (128, 128, 128))
        assert crop_datauri(img, (50, 50, 50, 60)) is None

    def test_bbox_outside_image_clamped(self):
        """Bbox outside image dimensions should be safely handled."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        uri = crop_datauri(img, (-10, -10, 200, 200))
        assert uri is not None
        assert uri.startswith("data:image")

    def test_padding_applied(self):
        img = Image.new("RGB", (50, 50), (128, 128, 128))
        uri = crop_datauri(img, (5, 5, 45, 45), pad=3)
        assert uri is not None


# ── HTML output structure ─────────────────────────────────────────────────────

class TestHTMLOutput:
    @pytest.fixture
    def minimal_spec(self, tmp_path):
        spec_path = tmp_path / "spec.json"
        img_path = tmp_path / "slide.jpg"
        Image.new("RGB", (1280, 720), (240, 240, 240)).save(img_path)
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
            ]
        }
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return str(spec_path), str(tmp_path / "out.html")

    def test_lang_attribute_en(self, minimal_spec, monkeypatch):
        from assemble_html import main
        spec_path, out_html = minimal_spec
        monkeypatch.setattr("sys.argv", ["assemble_html.py", spec_path, "--out", out_html, "--lang", "en"])
        main()
        html = open(out_html, encoding="utf-8").read()
        assert 'lang="en"' in html

    def test_canvas_dims_from_spec(self, minimal_spec, monkeypatch):
        from assemble_html import main
        spec_path, out_html = minimal_spec
        monkeypatch.setattr("sys.argv", ["assemble_html.py", spec_path, "--out", out_html])
        main()
        html = open(out_html, encoding="utf-8").read()
        assert "--canvas-w: 1280px" in html
        assert "--canvas-h: 720px" in html

    def test_text_blocks_in_output(self, minimal_spec, monkeypatch):
        from assemble_html import main
        spec_path, out_html = minimal_spec
        monkeypatch.setattr("sys.argv", ["assemble_html.py", spec_path, "--out", out_html])
        main()
        html = open(out_html, encoding="utf-8").read()
        assert "Hello World" in html
        assert "Some body text here." in html

    def test_object_fit_is_contain(self, minimal_spec, monkeypatch):
        from assemble_html import main
        spec_path, out_html = minimal_spec
        monkeypatch.setattr("sys.argv", ["assemble_html.py", spec_path, "--out", out_html])
        main()
        html = open(out_html, encoding="utf-8").read()
        assert "object-fit:contain" in html

    def test_main_exits_on_missing_spec(self, monkeypatch):
        import io, contextlib
        from assemble_html import main
        monkeypatch.setattr("sys.argv", ["assemble_html.py", "/nonexistent/spec.json", "--out", "/tmp/out.html"])
        f = io.StringIO()
        with pytest.raises(SystemExit):
            with contextlib.redirect_stderr(f):
                main()
