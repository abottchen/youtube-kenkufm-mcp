from __future__ import annotations

import asyncio
import json
import os
import sys

from .config import Config, load_dotenv
from .youtube import ids, player


def main() -> None:
    """Connect to a running Kenku, resolve the YouTube view, print its state.

    Pass a playlist URL/ID as the first argument to instead print that
    playlist's videos via list_playlist (exercises the in-page fetch/walk that
    the mocked unit suite can't). Does NOT require YOUTUBE_MCP_AUTH_TOKEN
    (no server is started).
    """
    load_dotenv()  # pick up KENKU_CDP_URL / YOUTUBE_VIEW_URL_MATCH from .env if present
    cfg = Config(
        auth_token="x" * 16,  # unused; smoke never starts the HTTP server
        cdp_url=os.environ.get("KENKU_CDP_URL", "http://localhost:9222"),
        view_match=os.environ.get("YOUTUBE_VIEW_URL_MATCH", "youtube.com"),
    )
    if len(sys.argv) > 1:
        list_id = ids.parse_playlist_id(sys.argv[1])
        result = asyncio.run(player.list_playlist(cfg, list_id))
    else:
        result = asyncio.run(player.get_state(cfg))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
