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
