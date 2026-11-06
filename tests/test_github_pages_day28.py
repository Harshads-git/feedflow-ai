"""
tests/test_github_pages_day28.py
==================================
Tests for Day 28 additions to src/renderers/github_pages.py:
  - _topic_slug: various inputs including special chars, spaces, empty
  - _build_search_nav_snippet: contains search input, topic pills, JS
  - _build_topic_page_html: correct title/url/score in output, back links
  - _build_topics_index_html: sorted by count, grid cards, no-data fallback
  - GitHubPagesWriter._write_search_index: creates file, correct JSON,
      idempotent re-run replaces today's entries, preserves old entries
  - GitHubPagesWriter._write_topic_pages: creates per-topic HTML files
  - GitHubPagesWriter.collect_all_topics: empty without search.json,
      reads search.json, filters topics with < 2 stories
  - GitHubPagesWriter.write: produces search_json and topic pages in outputs
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.renderers.github_pages import (
    GitHubPagesWriter,
    _build_search_nav_snippet,
    _build_topic_page_html,
    _build_topics_index_html,
    _topic_slug,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_briefing(
    date: str = "2026-07-18",
    topics: list[str] = None,
    items: list[dict] = None,
    top_topics: list[str] = None,
) -> MagicMock:
    """Build a minimal mock Briefing for testing."""
    topics = topics or ["Python", "AI"]
    top_topics_val = top_topics if top_topics is not None else topics

    scored = MagicMock()
    scored.ai_topics = topics

    item = MagicMock()
    item.title = "Test Story"
    item.url = "https://example.com/test"
    item.source_name = "HN"
    item.ai_score = 8
    item.ai_summary = "A short summary"
    item.ai_headline = "Test Headline"
    item.scored = scored

    briefing = MagicMock()
    briefing.date = date
    briefing.items = [item]
    briefing.top_topics = top_topics_val
    briefing.executive_summary = "Test exec summary"
    return briefing


def _patched_writer(docs_dir: Path) -> GitHubPagesWriter:
    """Return a GitHubPagesWriter with render calls stubbed out."""
    import src.renderers.github_pages as gp
    gp.render_html = lambda b: "<html><body>Test</body></html>"
    gp.render_markdown = lambda b: "# Test"
    return GitHubPagesWriter(docs_dir)


# ===========================================================================
# _topic_slug
# ===========================================================================


class TestTopicSlug:
    @pytest.mark.unit
    def test_spaces_become_dashes(self):
        assert _topic_slug("Machine Learning") == "machine-learning"

    @pytest.mark.unit
    def test_lowercase(self):
        assert _topic_slug("AI") == "ai"

    @pytest.mark.unit
    def test_special_chars_stripped(self):
        assert _topic_slug("C++") == "c"

    @pytest.mark.unit
    def test_empty_string_returns_misc(self):
        assert _topic_slug("") == "misc"

    @pytest.mark.unit
    def test_multiple_spaces_collapsed(self):
        assert _topic_slug("Open  Source") == "open-source"

    @pytest.mark.unit
    def test_leading_trailing_stripped(self):
        assert _topic_slug("  Python  ") == "python"

    @pytest.mark.unit
    def test_numbers_preserved(self):
        assert _topic_slug("Python 3") == "python-3"


# ===========================================================================
# _build_search_nav_snippet
# ===========================================================================


class TestBuildSearchNavSnippet:
    @pytest.mark.unit
    def test_contains_search_input(self):
        snippet = _build_search_nav_snippet(["Python"])
        assert "nr-search" in snippet

    @pytest.mark.unit
    def test_contains_topic_pill_link(self):
        snippet = _build_search_nav_snippet(["Python", "AI"])
        assert "topic-pill" in snippet
        assert "topic-python.html" in snippet

    @pytest.mark.unit
    def test_contains_js_listener(self):
        snippet = _build_search_nav_snippet([])
        assert "addEventListener" in snippet

    @pytest.mark.unit
    def test_archive_and_topics_nav_links(self):
        snippet = _build_search_nav_snippet([])
        assert "archive.html" in snippet
        assert "topics.html" in snippet

    @pytest.mark.unit
    def test_empty_topics_list_ok(self):
        snippet = _build_search_nav_snippet([])
        assert "nr-search" in snippet

    @pytest.mark.unit
    def test_caps_at_twelve_pills(self):
        topics = [f"Topic{i}" for i in range(20)]
        snippet = _build_search_nav_snippet(topics)
        # Only first 12 topics rendered — count <a ... class="topic-pill"> anchors
        import re as _re
        pill_links = _re.findall(r'class="topic-pill"', snippet)
        assert len(pill_links) <= 12


# ===========================================================================
# _build_topic_page_html
# ===========================================================================


class TestBuildTopicPageHtml:
    @pytest.mark.unit
    def test_title_in_output(self):
        stories = [{"title": "Great Story", "url": "https://ex.com", "date": "2026-07-18", "ai_score": 7, "source_name": "HN", "topic_label": "Python"}]
        page = _build_topic_page_html("Python", "python", stories)
        assert "Great Story" in page

    @pytest.mark.unit
    def test_url_in_output(self):
        stories = [{"title": "T", "url": "https://test.example.com", "date": "2026-07-18", "ai_score": 5, "source_name": "HN", "topic_label": "Python"}]
        page = _build_topic_page_html("Python", "python", stories)
        assert "https://test.example.com" in page

    @pytest.mark.unit
    def test_back_link_to_topics(self):
        page = _build_topic_page_html("AI", "ai", [])
        assert "topics.html" in page

    @pytest.mark.unit
    def test_back_link_to_index(self):
        page = _build_topic_page_html("AI", "ai", [])
        assert "index.html" in page

    @pytest.mark.unit
    def test_topic_label_in_badge(self):
        page = _build_topic_page_html("Open Source", "open-source", [])
        assert "Open Source" in page

    @pytest.mark.unit
    def test_score_in_output(self):
        stories = [{"title": "T", "url": "https://ex.com", "date": "2026-07-18", "ai_score": 9, "source_name": "HN", "topic_label": "AI"}]
        page = _build_topic_page_html("AI", "ai", stories)
        assert "9/10" in page

    @pytest.mark.unit
    def test_story_count_in_meta(self):
        stories = [
            {"title": f"Story {i}", "url": f"https://ex.com/{i}", "date": "2026-07-18", "ai_score": 5, "source_name": "HN", "topic_label": "AI"}
            for i in range(3)
        ]
        page = _build_topic_page_html("AI", "ai", stories)
        assert "3 stories" in page


# ===========================================================================
# _build_topics_index_html
# ===========================================================================


class TestBuildTopicsIndexHtml:
    @pytest.mark.unit
    def test_topic_names_in_output(self):
        stories = [{"title": "T", "url": "https://ex.com", "date": "2026-07-18", "ai_score": 5, "source_name": "HN", "topic_label": "Python"}]
        idx = _build_topics_index_html({"python": stories * 3})
        assert "#Python" in idx

    @pytest.mark.unit
    def test_topic_card_links_to_page(self):
        stories = [{"topic_label": "AI", "title": "T", "url": "https://ex.com", "date": "2026-07-18", "ai_score": 5, "source_name": "HN"}]
        idx = _build_topics_index_html({"ai": stories * 2})
        assert "topic-ai.html" in idx

    @pytest.mark.unit
    def test_no_data_fallback_message(self):
        idx = _build_topics_index_html({})
        assert "No topic data" in idx

    @pytest.mark.unit
    def test_story_count_shown(self):
        stories = [{"topic_label": "Python", "title": "T", "url": "https://ex.com", "date": "2026-07-18", "ai_score": 5, "source_name": "HN"}]
        idx = _build_topics_index_html({"python": stories * 4})
        assert "4 stories" in idx

    @pytest.mark.unit
    def test_navigation_links_present(self):
        idx = _build_topics_index_html({})
        assert "index.html" in idx
        assert "archive.html" in idx


# ===========================================================================
# GitHubPagesWriter._write_search_index
# ===========================================================================


class TestWriteSearchIndex:
    @pytest.mark.unit
    def test_creates_search_json(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing()
        writer._write_search_index(briefing)
        assert (tmp_path / "search.json").exists()

    @pytest.mark.unit
    def test_search_json_contains_title(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing()
        writer._write_search_index(briefing)
        data = json.loads((tmp_path / "search.json").read_text())
        assert any(e["title"] == "Test Story" for e in data)

    @pytest.mark.unit
    def test_search_json_contains_topics(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing(topics=["Python", "AI"])
        writer._write_search_index(briefing)
        data = json.loads((tmp_path / "search.json").read_text())
        assert "Python" in data[0]["topics"]

    @pytest.mark.unit
    def test_idempotent_rerun_replaces_today(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing(date="2026-07-18")
        writer._write_search_index(briefing)
        writer._write_search_index(briefing)
        data = json.loads((tmp_path / "search.json").read_text())
        today_entries = [e for e in data if e["date"] == "2026-07-18"]
        assert len(today_entries) == 1

    @pytest.mark.unit
    def test_preserves_old_entries(self, tmp_path):
        writer = _patched_writer(tmp_path)
        # Write old entry directly
        old = [{"date": "2026-07-10", "title": "Old Story", "url": "https://old.com", "topics": ["AI"], "ai_score": 6, "source_name": "RSS", "summary": "", "headline": ""}]
        (tmp_path / "search.json").write_text(json.dumps(old))
        briefing = _make_briefing(date="2026-07-18")
        writer._write_search_index(briefing)
        data = json.loads((tmp_path / "search.json").read_text())
        dates = {e["date"] for e in data}
        assert "2026-07-10" in dates
        assert "2026-07-18" in dates


# ===========================================================================
# GitHubPagesWriter._write_topic_pages
# ===========================================================================


class TestWriteTopicPages:
    @pytest.mark.unit
    def test_creates_per_topic_html(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing(topics=["Python"])
        writer._write_topic_pages(briefing)
        assert (tmp_path / "topic-python.html").exists()

    @pytest.mark.unit
    def test_multiple_topics_create_multiple_files(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing(topics=["Python", "AI"])
        writer._write_topic_pages(briefing)
        assert (tmp_path / "topic-python.html").exists()
        assert (tmp_path / "topic-ai.html").exists()

    @pytest.mark.unit
    def test_returns_dict_of_paths(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing(topics=["Python"])
        result = writer._write_topic_pages(briefing)
        assert "topic_python" in result


# ===========================================================================
# GitHubPagesWriter.collect_all_topics
# ===========================================================================


class TestCollectAllTopics:
    @pytest.mark.unit
    def test_empty_without_search_json(self, tmp_path):
        writer = _patched_writer(tmp_path)
        assert writer.collect_all_topics() == {}

    @pytest.mark.unit
    def test_reads_topics_from_search_json(self, tmp_path):
        writer = _patched_writer(tmp_path)
        entries = [
            {"date": "2026-07-18", "title": f"Story {i}", "url": f"https://ex.com/{i}", "topics": ["Python"], "ai_score": 5, "source_name": "HN", "summary": "", "headline": ""}
            for i in range(3)
        ]
        (tmp_path / "search.json").write_text(json.dumps(entries))
        topics = writer.collect_all_topics()
        assert "python" in topics

    @pytest.mark.unit
    def test_filters_topics_with_fewer_than_two_stories(self, tmp_path):
        writer = _patched_writer(tmp_path)
        entries = [
            {"date": "2026-07-18", "title": "Only One", "url": "https://ex.com/1", "topics": ["Rare"], "ai_score": 5, "source_name": "HN", "summary": "", "headline": ""}
        ]
        (tmp_path / "search.json").write_text(json.dumps(entries))
        topics = writer.collect_all_topics()
        assert "rare" not in topics


# ===========================================================================
# GitHubPagesWriter.write (integration)
# ===========================================================================


class TestWriteIntegration:
    @pytest.mark.unit
    def test_write_produces_search_json(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing()
        outputs = writer.write(briefing)
        assert "search_json" in outputs
        assert (tmp_path / "search.json").exists()

    @pytest.mark.unit
    def test_write_produces_topic_pages(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing(topics=["Python"])
        outputs = writer.write(briefing)
        assert "topic_python" in outputs

    @pytest.mark.unit
    def test_index_html_contains_search_bar(self, tmp_path):
        writer = _patched_writer(tmp_path)
        briefing = _make_briefing()
        writer.write(briefing)
        index_content = (tmp_path / "index.html").read_text()
        assert "nr-search" in index_content
