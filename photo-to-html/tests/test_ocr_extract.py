"""Tests for ocr_extract.py — schema parsing and type mapping."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

# ── _norm_bbox ───────────────────────────────────────────────────────────────

from ocr_extract import _norm_bbox

class TestNormBbox:
    def test_list_format(self):
        assert _norm_bbox([10, 20, 100, 80]) == [10, 20, 100, 80]

    def test_polygon_format(self):
        bbox = [[10, 20], [100, 20], [100, 80], [10, 80]]
        result = _norm_bbox(bbox)
        assert result == [10, 20, 100, 80]

    def test_polygon_reordered(self):
        """Min/max across all vertices must be returned regardless of order."""
        bbox = [[100, 80], [10, 20], [10, 80], [100, 20]]
        result = _norm_bbox(bbox)
        assert result == [10, 20, 100, 80]

    def test_rounds_floats(self):
        result = _norm_bbox([10.4, 20.7, 99.9, 80.1])
        assert result == [10, 21, 100, 80]

    def test_none_returns_none(self):
        assert _norm_bbox(None) is None


# ── _to_type ─────────────────────────────────────────────────────────────────

from ocr_extract import _to_type

class TestToType:
    def test_known_labels(self):
        assert _to_type("doc_title") == "title"
        assert _to_type("paragraph_title") == "title"
        assert _to_type("text") == "text"
        assert _to_type("content") == "text"
        assert _to_type("formula") == "formula"
        assert _to_type("table") == "table"
        assert _to_type("figure") == "figure"
        assert _to_type("chart") == "figure"
        assert _to_type("algorithm") == "figure"
        assert _to_type("caption") == "caption"

    def test_case_insensitive(self):
        assert _to_type("TEXT") == "text"
        assert _to_type("Formula") == "formula"
        assert _to_type("  Title  ") == "title"

    def test_unknown_label_is_unknown(self):
        """Unknown labels must NOT be silently coerced to 'figure' or 'text'."""
        assert _to_type("foobar") == "unknown"
        assert _to_type("unknown_label") == "unknown"
        assert _to_type("configuration_block") == "unknown"

    def test_empty_returns_text(self):
        assert _to_type("") == "text"
        assert _to_type(None) == "text"


# ── parse_structure_result ───────────────────────────────────────────────────

from ocr_extract import parse_structure_result

class TestParseStructureResult:
    def test_parsing_res_list(self):
        res = {
            "res": {
                "parsing_res_list": [
                    {"block_label": "doc_title", "block_content": "Hello World",
                     "block_bbox": [10, 20, 400, 80]},
                    {"block_label": "text", "block_content": "Some body text",
                     "block_bbox": [10, 100, 400, 200]},
                    {"block_label": "formula", "block_content": "E=mc^2",
                     "block_bbox": [50, 220, 350, 280]},
                ]
            }
        }
        blocks, src = parse_structure_result(res)
        assert src == "parsing_res_list"
        assert len(blocks) == 3
        assert blocks[0]["type"] == "title"
        assert blocks[1]["type"] == "text"
        assert blocks[2]["type"] == "formula"
        assert blocks[2]["latex"] == "E=mc^2"

    def test_overall_ocr_res_fallback(self):
        res = {
            "res": {
                "overall_ocr_res": {
                    "rec_texts": ["Line one", "Line two"],
                    "rec_boxes": [[0, 0, 100, 20], [0, 30, 100, 50]]
                }
            }
        }
        blocks, src = parse_structure_result(res)
        assert src == "overall_ocr_res"
        assert len(blocks) == 2
        assert blocks[0]["text"] == "Line one"
        assert blocks[0]["type"] == "text"

    def test_unknown_schema_raises(self):
        """Unknown schema must raise RuntimeError with diagnostic output."""
        import io, contextlib
        res = {"res": {"unknown_key": []}}
        with pytest.raises(RuntimeError, match="Unknown PP-StructureV3 schema"):
            parse_structure_result(res)

    def test_reading_order_assigned(self):
        res = {
            "res": {
                "parsing_res_list": [
                    {"block_label": "text", "block_content": "A", "block_bbox": [0, 0, 10, 10]},
                    {"block_label": "text", "block_content": "B", "block_bbox": [0, 20, 10, 30]},
                ]
            }
        }
        blocks, _ = parse_structure_result(res)
        assert blocks[0]["reading_order"] == 0
        assert blocks[1]["reading_order"] == 1

    def test_raw_label_preserved(self):
        res = {
            "res": {
                "parsing_res_list": [
                    {"block_label": "my_custom_label", "block_content": "T",
                     "block_bbox": [0, 0, 10, 10]},
                ]
            }
        }
        blocks, _ = parse_structure_result(res)
        assert blocks[0]["raw_label"] == "my_custom_label"
        assert blocks[0]["type"] == "unknown"   # not silently coerced

    def test_table_html_preserved(self):
        res = {
            "res": {
                "parsing_res_list": [
                    {"block_label": "table", "block_content": "<table><tr><td>A</td></tr></table>",
                     "block_bbox": [0, 0, 100, 50]},
                ]
            }
        }
        blocks, _ = parse_structure_result(res)
        assert blocks[0]["html"] == "<table><tr><td>A</td></tr></table>"

    def test_polygon_bbox(self):
        res = {
            "res": {
                "parsing_res_list": [
                    {"block_label": "text", "block_content": "T",
                     "block_bbox": [[10, 20], [100, 20], [100, 80], [10, 80]]},
                ]
            }
        }
        blocks, _ = parse_structure_result(res)
        assert blocks[0]["bbox"] == [10, 20, 100, 80]


# ── _resolve_local_models ───────────────────────────────────────────────────

from ocr_extract import _resolve_local_models

class TestResolveLocalModels:
    """Regression tests for offline model directory resolution.

    PaddleOCR 3.7+ ships models as ``inference.json`` (structure) +
    ``inference.pdiparams`` (weights), NOT the legacy
    ``inference.pdmodel`` + ``inference.pdiparams`` pair. The resolver
    must accept both layouts.
    """

    def _make_v37_model(self, root, name):
        d = root / name
        d.mkdir(parents=True)
        (d / "inference.json").write_text("{}")
        (d / "inference.pdiparams").write_bytes(b"\0" * 8)
        (d / "inference.yml").write_text("config")
        return d

    def _make_legacy_model(self, root, name):
        d = root / name
        d.mkdir(parents=True)
        (d / "inference.pdmodel").write_bytes(b"\0" * 8)
        (d / "inference.pdiparams").write_bytes(b"\0" * 8)
        return d

    def test_resolves_v37_format(self, tmp_path):
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        self._make_v37_model(root, "PP-OCRv5_server_det")
        self._make_v37_model(root, "PP-OCRv5_server_rec")
        resolved = _resolve_local_models(Path(root))
        assert "text_detection_model_dir" in resolved
        assert "text_recognition_model_dir" in resolved
        assert resolved["text_detection_model_dir"].endswith("PP-OCRv5_server_det")

    def test_resolves_legacy_format(self, tmp_path):
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        self._make_legacy_model(root, "PP-OCRv5_server_det")
        resolved = _resolve_local_models(Path(root))
        assert "text_detection_model_dir" in resolved

    def test_skips_dir_missing_weights(self, tmp_path):
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        d = root / "PP-OCRv5_server_det"
        d.mkdir()
        (d / "inference.json").write_text("{}")
        # no inference.pdiparams
        resolved = _resolve_local_models(Path(root))
        assert resolved == {}

    def test_skips_dir_missing_structure(self, tmp_path):
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        d = root / "PP-OCRv5_server_det"
        d.mkdir()
        (d / "inference.pdiparams").write_bytes(b"\0" * 8)
        # no inference.json or inference.pdmodel
        resolved = _resolve_local_models(Path(root))
        assert resolved == {}

    def test_resolves_all_11_models(self, tmp_path):
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        names = [
            "PP-OCRv5_server_det", "PP-OCRv5_server_rec",
            "PP-DocLayout_plus-L", "PP-DocBlockLayout",
            "SLANet_plus", "SLANeXt_wired",
            "PP-FormulaNet_plus-L",
            "PP-LCNet_x1_0_textline_ori", "PP-LCNet_x1_0_table_cls",
            "RT-DETR-L_wired_table_cell_det",
            "RT-DETR-L_wireless_table_cell_det",
        ]
        for n in names:
            self._make_v37_model(root, n)
        resolved = _resolve_local_models(Path(root))
        assert len(resolved) == 11
        expected_kwargs = {
            "text_detection_model_dir", "text_recognition_model_dir",
            "layout_detection_model_dir", "region_detection_model_dir",
            "wireless_table_structure_recognition_model_dir",
            "wired_table_structure_recognition_model_dir",
            "formula_recognition_model_dir",
            "textline_orientation_model_dir",
            "table_classification_model_dir",
            "wired_table_cells_detection_model_dir",
            "wireless_table_cells_detection_model_dir",
        }
        assert set(resolved.keys()) == expected_kwargs

    # ── PP-OCRv6 support (opt-in, user-downloaded) ──────────────────────────

    def test_v6_preferred_over_v5_when_both_present(self, tmp_path):
        """When both v5_server and v6_medium are on disk, v6 wins (opt-in)."""
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        self._make_v37_model(root, "PP-OCRv5_server_det")
        self._make_v37_model(root, "PP-OCRv5_server_rec")
        self._make_v37_model(root, "PP-OCRv6_medium_det")
        self._make_v37_model(root, "PP-OCRv6_medium_rec")
        resolved = _resolve_local_models(Path(root))
        assert resolved["text_detection_model_dir"].endswith("PP-OCRv6_medium_det")
        assert resolved["text_recognition_model_dir"].endswith("PP-OCRv6_medium_rec")

    def test_v6_alone_is_resolved(self, tmp_path):
        """v6 without v5 should still populate text det/rec kwargs."""
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        self._make_v37_model(root, "PP-OCRv6_small_det")
        self._make_v37_model(root, "PP-OCRv6_small_rec")
        resolved = _resolve_local_models(Path(root))
        assert resolved["text_detection_model_dir"].endswith("PP-OCRv6_small_det")
        assert resolved["text_recognition_model_dir"].endswith("PP-OCRv6_small_rec")

    def test_cli_det_model_overrides_priority(self, tmp_path):
        """--det-model PP-OCRv6_tiny_det wins even if v6_medium is present."""
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        self._make_v37_model(root, "PP-OCRv6_medium_det")
        self._make_v37_model(root, "PP-OCRv6_tiny_det")
        resolved = _resolve_local_models(Path(root),
                                         det_model="PP-OCRv6_tiny_det")
        assert resolved["text_detection_model_dir"].endswith("PP-OCRv6_tiny_det")

    def test_cli_det_model_not_on_disk_is_skipped(self, tmp_path):
        """If --det-model names a dir not on disk, fall through to v6/v5."""
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        self._make_v37_model(root, "PP-OCRv5_server_det")
        resolved = _resolve_local_models(Path(root),
                                         det_model="PP-OCRv6_medium_det")
        # v6_medium_det not on disk -> falls back to v5_server_det
        assert resolved["text_detection_model_dir"].endswith("PP-OCRv5_server_det")

    def test_v6_medium_preferred_over_small_and_tiny(self, tmp_path):
        """Within v6 variants, medium > small > tiny priority."""
        from pathlib import Path
        root = tmp_path / "models"
        root.mkdir()
        for name in ("PP-OCRv6_tiny_det", "PP-OCRv6_small_det",
                     "PP-OCRv6_medium_det"):
            self._make_v37_model(root, name)
        resolved = _resolve_local_models(Path(root))
        assert resolved["text_detection_model_dir"].endswith("PP-OCRv6_medium_det")
