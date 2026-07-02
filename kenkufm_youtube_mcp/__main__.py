from __future__ import annotations

import logging

import uvicorn

from .config import ConfigError, load_config, load_dotenv
from .server import build_app


def main() -> None:
    load_dotenv()  # load .env from the current directory if present
    try:
        cfg = load_config()
    except ConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}")

    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO))
    log = logging.getLogger("kenkufm_youtube_mcp")

    app = build_app(cfg)
    log.info(
        "kenkufm-youtube-mcp listening on http://%s:%s/mcp (CDP: %s)",
        cfg.host, cfg.port, cfg.cdp_url,
    )
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=cfg.log_level.lower())


if __name__ == "__main__":
    main()
