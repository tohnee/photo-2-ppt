"""Tests for crop_region.py — white balance, flat field, key light."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
from PIL import Image

import pytest

# ── white_balance ─────────────────────────────────────────────────────────────

from crop_region import white_balance

class TestCRWhiteBalance:
    def test_per_channel_levels(self):
        """WB should scale each channel independently."""
        img = Image.new("RGB", (100, 100), (100, 150, 200))
        out = white_balance(img)
        assert out.size == img.size
        # Pillow 11+ Image objects don't expose .dtype; check via numpy
        assert np.array(out).dtype == np.uint8

    def test_single_channel_zero(self):
        """Zero-value channel must not cause division by zero."""
        img = Image.new("RGB", (100, 100), (0, 100, 100))
        out = white_balance(img)
        assert out.size == img.size

    def test_output_dtype_uint8(self):
        img = Image.new("RGB", (50, 50), (80, 120, 160))
        out = white_balance(img)
        assert np.array(out).dtype == np.uint8

    def test_values_in_uint8_range(self):
        img = Image.new("RGB", (100, 100), (10, 10, 10))
        out = white_balance(img)
        arr = np.array(out)
        assert arr.min() >= 0
        assert arr.max() <= 255


# ── flat_field ────────────────────────────────────────────────────────────────

from crop_region import flat_field

class TestFlatField:
    def test_removes_brightness_gradient(self):
        """Flat-field on a vignette-like image should flatten it."""
        w, h = 200, 200
        # Build a vignette as uint8
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                fx = 1 - abs(x - w/2.0) / (w/2.0)
                fy = 1 - abs(y - h/2.0) / (h/2.0)
                factor = 0.5 + 0.5 * fx * fy
                val = int(round(factor * 200))
                arr[y, x] = (val, val, val)
        img = Image.fromarray(arr)
        out = flat_field(img)
        assert out.size == img.size
        out_arr = np.array(out).astype(float)
        in_arr = np.array(img).astype(float)
        assert np.std(out_arr) < np.std(in_arr) * 2

    def test_does_not_crash_on_uniform_image(self):
        img = Image.new("RGB", (100, 100), (200, 200, 200))
        out = flat_field(img)
        assert out.size == img.size

    def test_custom_radius(self):
        img = Image.new("RGB", (200, 200), (150, 150, 150))
        out = flat_field(img, radius=20)
        assert out.size == img.size


# ── key_light ────────────────────────────────────────────────────────────────

from crop_region import key_light

class TestKeyLight:
    def test_produces_rgba(self):
        img = Image.new("RGB", (100, 100), (240, 240, 240))
        out = key_light(img, thresh=230)
        assert out.mode == "RGBA"

    def test_dark_region_becomes_transparent(self):
        """Pixels above luminance threshold should have near-zero alpha."""
        img = Image.new("RGB", (100, 100), (240, 240, 240))
        out = key_light(img, thresh=230)
        out_arr = np.array(out)
        alpha = out_arr[:, :, 3]
        # Bright background should be transparent (low alpha)
        assert alpha.mean() < 128

    def test_flat_field_applied_before_keying(self):
        """key_light must not crash on uniform images (flat_field handles it)."""
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        out = key_light(img, thresh=100)
        assert out.mode == "RGBA"
        assert out.size == img.size

    def test_transparent_output_values_clipped(self):
        img = Image.new("RGB", (100, 100), (250, 250, 250))
        out = key_light(img, thresh=230)
        out_arr = np.array(out)
        assert out_arr.max() <= 255
        assert out_arr.min() >= 0


# ── CLI argument parsing ─────────────────────────────────────────────────────

class TestCLI:
    def test_bbox_parsing_valid(self, monkeypatch, tmp_path):
        from crop_region import main
        img = Image.new("RGB", (1000, 1000), (200, 200, 200))
        tmp_path_file = tmp_path / "test_crop_input.jpg"
        img.save(str(tmp_path_file))
        monkeypatch.setattr("sys.argv", ["crop_region.py", str(tmp_path_file), "--bbox", "10,10,100,100"])
        rc = main()
        assert rc == 0

    def test_bbox_parsing_invalid(self, monkeypatch, tmp_path):
        from crop_region import main
        img = Image.new("RGB", (1000, 1000), (200, 200, 200))
        tmp_path_file = tmp_path / "test_crop_input.jpg"
        img.save(str(tmp_path_file))
        monkeypatch.setattr("sys.argv", ["crop_region.py", str(tmp_path_file), "--bbox", "not_a_bbox"])
        rc = main()
        assert rc == 1

    def test_empty_bbox_rejected(self, monkeypatch, tmp_path):
        from crop_region import main
        img = Image.new("RGB", (1000, 1000), (200, 200, 200))
        tmp_path_file = tmp_path / "test_crop_input.jpg"
        img.save(str(tmp_path_file))
        monkeypatch.setattr("sys.argv", ["crop_region.py", str(tmp_path_file), "--bbox", "50,50,50,60"])
        rc = main()
        assert rc == 1
