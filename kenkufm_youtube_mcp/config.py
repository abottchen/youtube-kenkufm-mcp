from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    auth_token: str = field(repr=False)
    port: int = 3940
    host: str = "127.0.0.1"
    cdp_url: str = "http://localhost:9222"
    view_match: str = "youtube.com"
    log_level: str = "INFO"


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    token = (env.get("YOUTUBE_MCP_AUTH_TOKEN") or "").strip()
    if len(token) < 16:
        raise ConfigError(
            "YOUTUBE_MCP_AUTH_TOKEN must be set and at least 16 characters "
            "(generate one with: openssl rand -hex 32)"
        )
    raw_port = env.get("YOUTUBE_MCP_PORT", "3940")
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"YOUTUBE_MCP_PORT must be an integer (got {raw_port!r})"
        ) from exc
    if not 1 <= port <= 65535:
        raise ConfigError(
            f"YOUTUBE_MCP_PORT must be between 1 and 65535 (got {port})"
        )
    return Config(
        auth_token=token,
        port=port,
        host=env.get("YOUTUBE_MCP_HOST", "127.0.0.1"),
        cdp_url=env.get("KENKU_CDP_URL", "http://localhost:9222"),
        view_match=env.get("YOUTUBE_VIEW_URL_MATCH", "youtube.com"),
        log_level=env.get("LOG_LEVEL", "INFO"),
    )
