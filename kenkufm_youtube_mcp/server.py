from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from .config import Config
from .errors import KenkuYoutubeError
from .youtube import ids, player


async def _guard(coro):
    """Run a player coroutine; convert user-facing errors into {'error': msg}."""
    try:
        return await coro
    except KenkuYoutubeError as exc:
        return {"error": str(exc)}


def build_mcp(cfg: Config) -> FastMCP:
    mcp = FastMCP("kenkufm-youtube-mcp", host=cfg.host, port=cfg.port)

    @mcp.tool()
    async def get_playback_state() -> dict:
        """Get the current YouTube playback state in the Kenku FM view."""
        return await _guard(player.get_state(cfg))

    @mcp.tool()
    async def play_video(video: str, start_seconds: int | None = None,
                         loop: bool = False) -> dict:
        """Load and play a YouTube video by URL, youtu.be link, or 11-char ID.

        Set loop=True to repeat the video infinitely.
        """
        try:
            video_id = ids.parse_video_id(video)
        except KenkuYoutubeError as exc:
            return {"error": str(exc)}
        return await _guard(player.play_video(cfg, video_id, start_seconds, loop))

    @mcp.tool()
    async def play_playlist(playlist: str, index: int | None = None,
                            start_seconds: int | None = None) -> dict:
        """Load and play a YouTube playlist by URL or playlist ID (list=...)."""
        try:
            list_id = ids.parse_playlist_id(playlist)
        except KenkuYoutubeError as exc:
            return {"error": str(exc)}
        return await _guard(player.play_playlist(cfg, list_id, index, start_seconds))

    @mcp.tool()
    async def pause() -> dict:
        """Pause playback."""
        return await _guard(player.simple_action(cfg, "pause"))

    @mcp.tool()
    async def resume() -> dict:
        """Resume playback."""
        return await _guard(player.simple_action(cfg, "resume"))

    @mcp.tool()
    async def next() -> dict:
        """Skip to the next video (in a playlist)."""
        return await _guard(player.simple_action(cfg, "next"))

    @mcp.tool()
    async def previous() -> dict:
        """Skip to the previous video (in a playlist)."""
        return await _guard(player.simple_action(cfg, "previous"))

    @mcp.tool()
    async def seek(seconds: float) -> dict:
        """Seek to an absolute position in seconds."""
        return await _guard(player.seek(cfg, seconds))

    @mcp.tool()
    async def set_volume(volume: int) -> dict:
        """Set the YouTube player volume (0-100)."""
        return await _guard(player.set_volume(cfg, volume))

    @mcp.tool()
    async def mute() -> dict:
        """Mute the YouTube player."""
        return await _guard(player.simple_action(cfg, "mute"))

    @mcp.tool()
    async def unmute() -> dict:
        """Unmute the YouTube player."""
        return await _guard(player.simple_action(cfg, "unmute"))

    @mcp.tool()
    async def set_loop(enabled: bool) -> dict:
        """Turn infinite looping of the currently playing video on or off."""
        return await _guard(player.set_loop(cfg, enabled))

    return mcp


class BearerAuthASGI:
    """Pure-ASGI wrapper enforcing a bearer token on HTTP requests.

    Non-HTTP scopes (lifespan, websocket) pass straight through so the wrapped
    Starlette app's session-manager lifespan still runs.
    """

    def __init__(self, app, token: str):
        self.app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode("latin-1")
            if auth != self._expected:
                await JSONResponse({"error": "unauthorized"}, status_code=401)(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)


def build_app(cfg: Config):
    mcp = build_mcp(cfg)
    return BearerAuthASGI(mcp.streamable_http_app(), cfg.auth_token)
