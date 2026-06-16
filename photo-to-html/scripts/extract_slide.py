#!/usr/bin/env python3
"""
extract_slide.py — Extract a clean slide image from a photo of a projected/displayed slide.

Detects the bright rectangular screen, performs a 4-point perspective correction,
applies CLAHE for contrast recovery, and writes a 16:9 JPG.

Usage:
    python extract_slide.py photo.jpg
    python extract_slide.py photo.jpg --output cleaned.jpg
    python extract_slide.py photo.jpg --output cleaned.jpg --ratio 4:3

For edge cases (low contrast, multiple bright regions, occlusion), see
references/extraction_edge_cases.md.

Dependencies:
    pip install opencv-python --break-system-packages
"""

import argparse
import sys
import cv2
import numpy as np


def detect_screen_corners(img: np.ndarray, threshold_value: int = 150) -> np.ndarray:
    """
    Find the four corners of the bright rectangular screen in the photo.

    Args:
        img: input BGR image
        threshold_value: base threshold for bright-region isolation.
                          Used as the upper-bound for OTSU when mode is 'auto'.
                          Ignored when threshold_mode='manual'.

    Returns:
        4x2 array of (x, y) corner coordinates (unordered).

    Raises:
        RuntimeError if no valid quadrilateral can be detected.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # OTSU is more robust than a fixed threshold across varied lighting
    _, thresh = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Morphological kernel scales with image resolution to stay semantic
    # (25px at 640px ≈ 1/25; at 3840px that would be too large → clamp)
    base_size = max(W, H) // 40
    kernel_size = max(7, min(base_size, 61))  # clamp to [7, 61]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # Find contours, keep the largest few
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    # Look for a 4-vertex contour that's large enough
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        area = cv2.contourArea(c)
        if len(approx) == 4 and area > 0.2 * W * H:
            return approx.reshape(4, 2).astype(np.float32)

    # Fallback: use the minimum-area rectangle of the largest contour
    if contours:
        rect = cv2.minAreaRect(contours[0])
        return cv2.boxPoints(rect).astype(np.float32)

    raise RuntimeError("Could not detect any bright rectangular region in the photo.")


def order_corners(pts: np.ndarray) -> np.ndarray:
    """
    Order corners as [top-left, top-right, bottom-right, bottom-left].
    Uses centroid-based classification first, then y-sorted tiebreaking
    for near-axis-aligned inputs where x-y differences are unreliable.
    """
    # Centroid-based classification: reliable regardless of aspect ratio
    centroid = pts.mean(axis=0)
    tl, tr, br, bl = [], [], [], []
    for p in pts:
        dx = p[0] - centroid[0]
        dy = p[1] - centroid[1]
        if dx < 0 and dy < 0:
            tl.append(p)
        elif dx >= 0 and dy < 0:
            tr.append(p)
        elif dx >= 0 and dy >= 0:
            br.append(p)
        else:
            bl.append(p)

    def _top(a, b):
        return a if a[1] <= b[1] else b

    def _bot(a, b):
        return a if a[1] >= b[1] else b

    rect = np.zeros((4, 2), dtype=np.float32)
    rect[0] = _top(tl[0], tl[1]) if len(tl) == 2 else tl[0]
    rect[1] = _top(tr[0], tr[1]) if len(tr) == 2 else tr[0]
    rect[2] = _bot(br[0], br[1]) if len(br) == 2 else br[0]
    rect[3] = _bot(bl[0], bl[1]) if len(bl) == 2 else bl[0]
    return rect


def perspective_correct(img: np.ndarray, corners: np.ndarray, ratio: str = "16:9") -> np.ndarray:
    """
    Warp the image so the four corners become a rectangle with the given aspect ratio.
    """
    rect = order_corners(corners)
    tl, tr, br, bl = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))

    # Force the target aspect ratio
    if ratio == "16:9":
        target_h = int(max_w * 9 / 16)
    elif ratio == "4:3":
        target_h = int(max_w * 3 / 4)
    else:
        # "auto" — use the detected height as-is
        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        target_h = int(max(height_a, height_b))

    target_w = max_w
    dst = np.array([
        [0, 0],
        [target_w - 1, 0],
        [target_w - 1, target_h - 1],
        [0, target_h - 1]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, M, (target_w, target_h))


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE to the L channel in LAB space. Recovers contrast lost to projection.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Path to the input photo (JPG or PNG)")
    parser.add_argument("--output", "-o", default="slide_extracted.jpg",
                        help="Path for the extracted slide image (default: slide_extracted.jpg)")
    parser.add_argument("--ratio", default="16:9", choices=["16:9", "4:3", "auto"],
                        help="Target aspect ratio (default: 16:9)")
    parser.add_argument("--threshold", type=int, default=150,
                        help="Base threshold for bright-region isolation (default: 150). "
                             "OTSU is always used; this is the upper bound.")
    parser.add_argument("--no-enhance", action="store_true",
                        help="Skip the CLAHE contrast enhancement step")
    parser.add_argument("--quality", type=int, default=95,
                        help="JPG quality 1-100 (default: 95)")
    args = parser.parse_args()

    img = cv2.imread(args.input)
    if img is None:
        print(f"Error: could not load image from {args.input}", file=sys.stderr)
        sys.exit(1)

    H, W = img.shape[:2]
    print(f"Input image: {W} x {H}")

    # Rotate portrait photos to landscape (common iPhone case); if detection
    # fails after rotation, try the original orientation as a fallback.
    _rotation_done = False
    if H > W:
        print("Portrait photo detected — rotating 90° to landscape.")
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        _rotation_done = True

    try:
        corners = detect_screen_corners(img, threshold_value=args.threshold)
    except RuntimeError:
        # Fallback: if rotation was applied and detection failed, try the
        # original orientation before giving up
        if _rotation_done:
            print("Detection failed after rotation — retrying original orientation.",
                  file=sys.stderr)
            img_orig = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            img = img_orig
            try:
                corners = detect_screen_corners(img, threshold_value=args.threshold)
            except RuntimeError as e:
                print(f"Error: {e}", file=sys.stderr)
                print("See references/extraction_edge_cases.md for fallback strategies.",
                      file=sys.stderr)
                sys.exit(2)
        else:
            raise

    print(f"Detected screen corners: {corners.tolist()}")

    warped = perspective_correct(img, corners, ratio=args.ratio)
    print(f"Warped to: {warped.shape[1]} x {warped.shape[0]}")

    if not args.no_enhance:
        warped = enhance_contrast(warped)

    cv2.imwrite(args.output, warped, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
    print(f"✓ Wrote: {args.output}")


if __name__ == "__main__":
    main()
