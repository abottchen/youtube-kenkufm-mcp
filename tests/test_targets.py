import logging

import pytest
from kenkufm_youtube_mcp.cdp.targets import select_youtube_target
from kenkufm_youtube_mcp.errors import NoYouTubeViewError

def _t(type_, url, ws="ws://x"):
    return {"type": type_, "url": url, "webSocketDebuggerUrl": ws}

def test_selects_youtube_page():
    targets = [
        _t("page", "file:///player.html", "ws://player"),
        _t("page", "https://www.youtube.com/watch?v=abc", "ws://yt"),
        _t("service_worker", "https://www.youtube.com/sw.js", "ws://sw"),
    ]
    assert select_youtube_target(targets) == "ws://yt"

def test_ignores_non_page_and_missing_ws():
    targets = [
        _t("service_worker", "https://www.youtube.com/sw.js", "ws://sw"),
        {"type": "page", "url": "https://www.youtube.com/watch?v=abc"},  # no ws url
    ]
    with pytest.raises(NoYouTubeViewError):
        select_youtube_target(targets)

def test_no_youtube_raises():
    with pytest.raises(NoYouTubeViewError):
        select_youtube_target([_t("page", "file:///main.html")])

def test_multiple_youtube_pages_returns_first_and_warns(caplog):
    targets = [
        _t("page", "https://www.youtube.com/watch?v=one", "ws://yt1"),
        _t("page", "https://www.youtube.com/watch?v=two", "ws://yt2"),
        _t("service_worker", "https://www.youtube.com/sw.js", "ws://sw"),
    ]
    with caplog.at_level(logging.WARNING):
        assert select_youtube_target(targets) == "ws://yt1"
    assert any(r.levelno == logging.WARNING for r in caplog.records)
