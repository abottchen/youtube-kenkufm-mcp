from __future__ import annotations

import asyncio
import json
import os

from .config import Config, load_dotenv
from .youtube import player


def main() -> None:
    """Connect to a running Kenku, resolve the YouTube view, print its state.

    Does NOT require YOUTUBE_MCP_AUTH_TOKEN (no server is started).
    """
    load_dotenv()  # pick up KENKU_CDP_URL / YOUTUBE_VIEW_URL_MATCH from .env if present
    cfg = Config(
        auth_token="x" * 16,  # unused; smoke never starts the HTTP server
        cdp_url=os.environ.get("KENKU_CDP_URL", "http://localhost:9222"),
        view_match=os.environ.get("YOUTUBE_VIEW_URL_MATCH", "youtube.com"),
    )
    print(json.dumps(asyncio.run(player.get_state(cfg)), indent=2))


if __name__ == "__main__":
    main()
