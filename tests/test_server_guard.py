from kenkufm_youtube_mcp import server
from kenkufm_youtube_mcp.cdp.client import CdpEvalError
from kenkufm_youtube_mcp.config import Config
from kenkufm_youtube_mcp.errors import KenkuYoutubeError


def test_cdp_eval_error_is_kenku_youtube_error():
    assert issubclass(CdpEvalError, KenkuYoutubeError)


async def test_guard_catches_cdp_eval_error():
    async def _boom():
        raise CdpEvalError("page threw")

    out = await server._guard(_boom())
    assert isinstance(out, dict) and "error" in out


async def test_set_loop_tool_registered_with_loop_params():
    mcp = server.build_mcp(Config(auth_token="x" * 16))
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "set_loop" in names
    assert {"play_video", "play_playlist"} <= names
    assert len(tools) == 12
    pv = next(t for t in tools if t.name == "play_video")
    assert "loop" in pv.inputSchema["properties"]
    sl = next(t for t in tools if t.name == "set_loop")
    assert "enabled" in sl.inputSchema["properties"]
