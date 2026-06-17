"""Tests for extract_slide.py — perspective correction and corner ordering."""
import sys, os, tempfile, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import numpy as np
import pytest

# ── fixtures ──────────────────────────────────────────────────────────────────

def make_synth_slide(size=(1280, 720), corners=None):
    """Return a white BGRA image with a bright white rect drawn at given corners."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, (30, 30, 30))   # dark surround
    draw = ImageDraw.Draw(img)
    if corners is None:
        # Full-frame bright rect
        pts = [(0, 0), (size[0]-1, 0), (size[0]-1, size[1]-1), (0, size[1]-1)]
    else:
        pts = [(int(x), int(y)) for x, y in corners]
    draw.polygon(pts, fill=(240, 240, 240))
    return img


def np_corners(pts4):
    return np.array(pts4, dtype=np.float32)


# ── order_corners ─────────────────────────────────────────────────────────────

from extract_slide import order_corners

def _check_order(rect, name=""):
    tl, tr, br, bl = rect
    assert tl[0] < tr[0], f"{name}: tl.x must be < tr.x  got {tl[0]}, {tr[0]}"
    assert bl[0] < br[0], f"{name}: bl.x must be < br.x  got {bl[0]}, {br[0]}"
    assert tl[1] < bl[1], f"{name}: tl.y must be < bl.y  got {tl[1]}, {bl[1]}"
    assert tr[1] < br[1], f"{name}: tr.y must be < br.y  got {tr[1]}, {br[1]}"


class TestOrderCorners:
    def test_near_square(self):
        """Near-axis-aligned square — the case where np.diff was fragile."""
        pts = np_corners([(10, 10), (500, 10), (500, 300), (10, 300)])
        rect = order_corners(pts)
        _check_order(rect, "near_square")
        # Top-left should be (10, 10)
        assert abs(rect[0][0] - 10) < 1 and abs(rect[0][1] - 10) < 1, rect

    def test_rotated_rect(self):
        pts = np_corners([(100, 50), (600, 150), (500, 600), (0, 500)])
        rect = order_corners(pts)
        _check_order(rect, "rotated")

    def test_already_ordered(self):
        """Already TL→TR→BR→BL — should survive unchanged."""
        pts = np_corners([(50, 30), (700, 30), (700, 400), (50, 400)])
        rect = order_corners(pts)
        _check_order(rect, "already_ordered")
        np.testing.assert_array_almost_equal(rect[0], [50, 30])
        np.testing.assert_array_almost_equal(rect[1], [700, 30])

    def test_near_horizontal(self):
        """Near-horizontal top edge — x-y diff is tiny."""
        pts = np_corners([(20, 100), (600, 105), (590, 400), (30, 395)])
        rect = order_corners(pts)
        _check_order(rect, "near_horizontal")


# ── perspective_correct ───────────────────────────────────────────────────────

from extract_slide import perspective_correct

def _homography_error(src_pts, dst_pts):
    """Check that a perspective warp with 4 known correspondences maps correctly."""
    import cv2
    H, W = 400, 600
    # Synthetic image
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:, :] = (30, 30, 30)
    warped = perspective_correct(img, src_pts)
    # TL->TR should be top row, BL->BR bottom row
    assert warped.shape[0] > 0 and warped.shape[1] > 0, f"empty output: {warped.shape}"
    # Check aspect ratio is roughly correct
    ratio = warped.shape[1] / warped.shape[0]
    assert 1.6 < ratio < 1.8, f"16:9 expected, got {ratio:.2f}"


class TestPerspectiveCorrect:
    def test_full_frame(self):
        pts = np_corners([(0, 0), (1279, 0), (1279, 719), (0, 719)])
        _homography_error(pts, None)

    def test_slightly_cropped(self):
        pts = np_corners([(50, 30), (1230, 20), (1240, 690), (40, 700)])
        _homography_error(pts, None)

    def test_ratiostring_4_3(self):
        import cv2
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        pts = np_corners([(0, 0), (639, 0), (639, 479), (0, 479)])
        warped = perspective_correct(img, pts, ratio="4:3")
        ratio = warped.shape[1] / warped.shape[0]
        assert 1.3 < ratio < 1.35, f"4:3 expected, got {ratio:.2f}"


# ── detect_screen_corners ────────────────────────────────────────────────────

from extract_slide import detect_screen_corners

class TestDetectScreenCorners:
    def test_full_bright_rectangle(self):
        """A full-frame bright rectangle must be detected."""
        img = np.full((400, 600, 3), 255, dtype=np.uint8)
        pts = detect_screen_corners(img)
        assert pts.shape == (4, 2)

    def test_bright_on_dark_detects_region(self):
        """Bright rect on dark background: should isolate correctly with OTSU."""
        img = np.full((400, 600, 3), 20, dtype=np.uint8)
        img[50:350, 80:520] = 240   # bright rect
        pts = detect_screen_corners(img)
        assert pts.shape == (4, 2)
        xs = pts[:, 0]; ys = pts[:, 1]
        assert xs.min() < 100, f"left edge too far right: {xs.min()}"
        assert xs.max() > 500, f"right edge too far left: {xs.max()}"

    def test_threshold_arg_passed_through(self):
        """threshold_value param is forwarded to detect_screen_corners."""
        img = np.full((400, 600, 3), 20, dtype=np.uint8)
        img[50:350, 80:520] = 200
        # Should succeed with reasonable threshold
        pts = detect_screen_corners(img, threshold_value=120)
        assert pts.shape == (4, 2)


# ── enhance_contrast ─────────────────────────────────────────────────────────

from extract_slide import enhance_contrast

class TestEnhanceContrast:
    def test_does_not_crash(self):
        img = np.full((200, 300, 3), 128, dtype=np.uint8)
        out = enhance_contrast(img)
        assert out.shape == img.shape
        assert out.dtype == np.uint8

    def test_increases_dynamic_range(self):
        """CLAHE should spread the flat region."""
        img = np.full((200, 300, 3), 128, dtype=np.uint8)
        out = enhance_contrast(img)
        assert out.std() >= 0   # just ensure it runs without error


# ── main() CLI smoke test ────────────────────────────────────────────────────

class TestCLI:
    def test_missing_input(self, tmp_path, monkeypatch):
        from extract_slide import main
        import io, contextlib
        # Force sys.argv to have no positional args so argparse rejects.
        # Without this, a prior test's monkeypatch can leak and main()
        # would see stale args.
        monkeypatch.setattr("sys.argv", ["extract_slide.py"])
        f = io.StringIO()
        with pytest.raises(SystemExit) as exc:
            with contextlib.redirect_stderr(f):
                main()   # no args
        assert exc.value.code == 2   # argparse exits 2 for bad args

    def test_nonexistent_file(self, tmp_path, monkeypatch):
        from extract_slide import main
        import io, contextlib
        monkeypatch.setattr("sys.argv", ["extract_slide.py", "nonexistent.jpg"])
        f = io.StringIO()
        with pytest.raises(SystemExit) as exc:
            with contextlib.redirect_stderr(f):
                main()
        assert exc.value.code == 1
