"""Unit tests for the Blended Image watermark filter.

The Airtable "Blended Image" field can hold the original upload plus one
or more ``*_watermarked.jpg`` versions per record. Without filtering, the
gallery renders each record 2-3 times. ``_filter_watermarked_only`` keeps
only the watermarked attachments and dedupes byte-identical duplicates.

Run directly: ``python tests/test_blended_image_filter.py``.
"""
import os
import sys

# Make ``src`` importable when this file is run directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.airtable_client import _filter_watermarked_only  # noqa: E402


def test_drops_original_and_dedupes_duplicate_watermarks():
    atts = [
        {"filename": "1776211911487-55fa9we6tp.png", "size": 8653014, "id": "a1"},
        {"filename": "rec023Qzfzf6ze8Ia_watermarked.jpg", "size": 1453694, "id": "a2"},
        {
            "filename": "tbl0H4CE8jdcawJfT_rec023Qzfzf6ze8Ia_watermarked.jpg",
            "size": 1453694,
            "id": "a3",
        },
    ]
    out = _filter_watermarked_only(atts)
    assert len(out) == 1
    assert "_watermarked" in out[0]["filename"].lower()


def test_drops_original_when_one_watermark_present():
    atts = [
        {"filename": "1776659084499-x6w0uy7j0io.png", "size": 9450306, "id": "b1"},
        {
            "filename": "tblUdcQhWKBbj2QG2_rec0d1wf5mmZVyfDp_watermarked.jpg",
            "size": 1692832,
            "id": "b2",
        },
    ]
    out = _filter_watermarked_only(atts)
    assert len(out) == 1
    assert "_watermarked" in out[0]["filename"].lower()


def test_returns_input_when_no_watermark_present():
    atts = [
        {"filename": "1776659084499-x6w0uy7j0io.png", "size": 9450306, "id": "c1"},
    ]
    assert _filter_watermarked_only(atts) == atts


def test_handles_empty_and_none_inputs():
    assert _filter_watermarked_only([]) == []
    assert _filter_watermarked_only(None) is None


def test_keeps_distinct_watermarks_for_different_records():
    atts = [
        {"filename": "rec_a_watermarked.jpg", "size": 100, "id": "d1"},
        {"filename": "rec_b_watermarked.jpg", "size": 200, "id": "d2"},
    ]
    out = _filter_watermarked_only(atts)
    assert len(out) == 2


if __name__ == "__main__":
    test_drops_original_and_dedupes_duplicate_watermarks()
    test_drops_original_when_one_watermark_present()
    test_returns_input_when_no_watermark_present()
    test_handles_empty_and_none_inputs()
    test_keeps_distinct_watermarks_for_different_records()
    print("All Blended Image watermark filter tests passed.")
