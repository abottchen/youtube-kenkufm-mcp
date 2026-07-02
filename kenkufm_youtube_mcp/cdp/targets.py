from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from ..errors import KenkuUnreachableError, NoYouTubeViewError

log = logging.getLogger("kenkufm_youtube_mcp")


def fetch_targets(cdp_url: str, timeout: float = 4.0) -> list[dict]:
    url = cdp_url.rstrip("/") + "/json/list"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.load(resp)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise KenkuUnreachableError(
            f"Kenku FM is not reachable at {cdp_url}. Launch Kenku with "
            "--remote-debugging-port=9222 and make sure WSL mirrored networking "
            f"is enabled. ({exc})"
        ) from exc


def select_youtube_target(targets: list[dict], match: str = "youtube.com") -> str:
    pages = [
        t for t in targets
        if t.get("type") == "page"
        and match in (t.get("url") or "")
        and t.get("webSocketDebuggerUrl")
    ]
    if not pages:
        raise NoYouTubeViewError(
            "No YouTube view is open in Kenku FM. Open a youtube.com web view "
            "in Kenku and try again."
        )
    if len(pages) > 1:
        log.warning(
            "Multiple YouTube views open (%d); using the first: %s",
            len(pages), [p.get("url") for p in pages],
        )
    return pages[0]["webSocketDebuggerUrl"]
