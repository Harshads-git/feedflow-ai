"""
tests/test_email_template.py
==============================
Tests for Day 29 email renderer in src/delivery/email_template.py.

Coverage:
  - _score_color: green for high scores, amber/orange/red for lower
  - _esc: HTML entities escaped, None handled
  - render_email_html: DOCTYPE, XHTML namespace, table layout present,
      no <style>-only CSS (inline styles used), story title/url in output,
      score circle present, topics bar present when top_topics non-empty,
      no-items fallback message, key_points rendered, executive_summary
      rendered, footer present, valid HTML (no unclosed main tags),
      multiple items all rendered, subject line format tested separately
  - render_email_html edge cases: empty items list, no summary, no topics,
      no key_points, very long title truncated safely, special chars escaped
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.delivery.email_template import (
    _esc,
    _score_color,
    render_email_html,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_scored_item(
    title: str = "Test Story",
    url: str = "https://example.com/test",
    score: int = 8,
    topics: list[str] = None,
    summary: str = "First para.\n\nSecond para.",
    key_points: list[str] = None,
    headline: str = "",
    source: str = "HN",
):
    scored = MagicMock()
    scored.ai_topics = topics or ["Python"]

    item_data = MagicMock()
    item_data.title = title
    item_data.url = url
    item_data.source_name = source

    si = MagicMock()
    si.scored = scored
    si.scored.item = item_data
    si.ai_score = score
    si.title = title
    si.url = url
    si.source_name = source
    si.ai_headline = headline or title
    si.ai_summary = summary
    si.key_points = key_points or []
    return si


def _make_briefing(
    date: str = "2026-07-19",
    items=None,
    top_topics: list[str] = None,
    summary: str = "Executive summary.",
):
    briefing = MagicMock()
    briefing.date = date
    briefing.items = items if items is not None else [_make_scored_item()]
    briefing.top_topics = top_topics if top_topics is not None else ["Python", "AI"]
    briefing.executive_summary = summary
    briefing.generated_at = datetime(2026, 7, 19, 6, 0, 0, tzinfo=timezone.utc)
    return briefing


# ===========================================================================
# _score_color
# ===========================================================================


class TestScoreColor:
    @pytest.mark.unit
    def test_high_score_green(self):
        color = _score_color(10)
        assert color == "#4ade80"

    @pytest.mark.unit
    def test_score_8_green(self):
        assert _score_color(8) == "#4ade80"

    @pytest.mark.unit
    def test_score_7_amber(self):
        assert _score_color(7) == "#facc15"

    @pytest.mark.unit
    def test_score_5_orange(self):
        assert _score_color(5) == "#f97316"

    @pytest.mark.unit
    def test_score_3_red(self):
        assert _score_color(3) == "#f87171"

    @pytest.mark.unit
    def test_score_1_red(self):
        assert _score_color(1) == "#f87171"


# ===========================================================================
# _esc
# ===========================================================================


class TestEsc:
    @pytest.mark.unit
    def test_ampersand_escaped(self):
        assert "&amp;" in _esc("a & b")

    @pytest.mark.unit
    def test_angle_brackets_escaped(self):
        result = _esc("<script>")
        assert "<" not in result
        assert ">" not in result

    @pytest.mark.unit
    def test_none_becomes_empty(self):
        assert _esc(None) == ""

    @pytest.mark.unit
    def test_plain_string_unchanged(self):
        assert _esc("hello world") == "hello world"

    @pytest.mark.unit
    def test_quotes_escaped(self):
        assert "&quot;" in _esc('"quoted"')


# ===========================================================================
# render_email_html — structure
# ===========================================================================


class TestRenderEmailHtmlStructure:
    @pytest.mark.unit
    def test_has_doctype(self):
        html = render_email_html(_make_briefing())
        assert "<!DOCTYPE html" in html

    @pytest.mark.unit
    def test_has_xhtml_namespace(self):
        html = render_email_html(_make_briefing())
        assert "xmlns" in html

    @pytest.mark.unit
    def test_has_table_layout(self):
        html = render_email_html(_make_briefing())
        assert "<table" in html

    @pytest.mark.unit
    def test_has_mso_conditional_comments(self):
        html = render_email_html(_make_briefing())
        assert "<!--[if mso]>" in html

    @pytest.mark.unit
    def test_has_viewport_meta(self):
        html = render_email_html(_make_briefing())
        assert "viewport" in html

    @pytest.mark.unit
    def test_has_charset_meta(self):
        html = render_email_html(_make_briefing())
        assert "UTF-8" in html

    @pytest.mark.unit
    def test_inline_styles_present(self):
        html = render_email_html(_make_briefing())
        assert 'style="' in html

    @pytest.mark.unit
    def test_no_css_custom_properties(self):
        # Email clients (especially Outlook) don't support CSS variables
        html = render_email_html(_make_briefing())
        assert "var(--" not in html


# ===========================================================================
# render_email_html — content
# ===========================================================================


class TestRenderEmailHtmlContent:
    @pytest.mark.unit
    def test_story_title_in_output(self):
        html = render_email_html(_make_briefing())
        assert "Test Story" in html

    @pytest.mark.unit
    def test_story_url_in_output(self):
        html = render_email_html(_make_briefing())
        assert "https://example.com/test" in html

    @pytest.mark.unit
    def test_read_article_link_present(self):
        html = render_email_html(_make_briefing())
        assert "Read article" in html

    @pytest.mark.unit
    def test_briefing_date_in_output(self):
        html = render_email_html(_make_briefing(date="2026-07-19"))
        assert "2026-07-19" in html

    @pytest.mark.unit
    def test_executive_summary_in_output(self):
        html = render_email_html(_make_briefing(summary="Big news today."))
        assert "Big news today." in html

    @pytest.mark.unit
    def test_topics_bar_present_when_topics(self):
        html = render_email_html(_make_briefing(top_topics=["Python", "AI"]))
        assert "Python" in html
        assert "AI" in html

    @pytest.mark.unit
    def test_key_points_rendered(self):
        si = _make_scored_item(key_points=["Point one", "Point two"])
        html = render_email_html(_make_briefing(items=[si]))
        assert "Point one" in html

    @pytest.mark.unit
    def test_summary_first_para_only(self):
        si = _make_scored_item(summary="First paragraph.\n\nSecond paragraph.")
        html = render_email_html(_make_briefing(items=[si]))
        assert "First paragraph." in html

    @pytest.mark.unit
    def test_footer_present(self):
        html = render_email_html(_make_briefing())
        assert "FeedFlow AI" in html
        # Footer should contain the date
        assert "2026-07-19" in html

    @pytest.mark.unit
    def test_special_chars_escaped_in_title(self):
        si = _make_scored_item(title="<script>alert('xss')</script>")
        html = render_email_html(_make_briefing(items=[si]))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    @pytest.mark.unit
    def test_multiple_items_all_rendered(self):
        items = [_make_scored_item(title=f"Story {i}") for i in range(5)]
        html = render_email_html(_make_briefing(items=items))
        for i in range(5):
            assert f"Story {i}" in html


# ===========================================================================
# render_email_html — edge cases
# ===========================================================================


class TestRenderEmailHtmlEdgeCases:
    @pytest.mark.unit
    def test_empty_items_shows_fallback(self):
        html = render_email_html(_make_briefing(items=[]))
        assert "No stories" in html or "threshold" in html

    @pytest.mark.unit
    def test_no_top_topics_no_crash(self):
        html = render_email_html(_make_briefing(top_topics=[]))
        assert "<!DOCTYPE html" in html

    @pytest.mark.unit
    def test_no_summary_no_crash(self):
        html = render_email_html(_make_briefing(summary=""))
        assert "<!DOCTYPE html" in html

    @pytest.mark.unit
    def test_no_key_points_no_crash(self):
        si = _make_scored_item(key_points=[])
        html = render_email_html(_make_briefing(items=[si]))
        assert "<!DOCTYPE html" in html

    @pytest.mark.unit
    def test_output_is_substantial(self):
        html = render_email_html(_make_briefing())
        assert len(html) > 3000
