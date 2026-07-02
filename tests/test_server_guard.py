from kenkufm_youtube_mcp import server
from kenkufm_youtube_mcp.cdp.client import CdpEvalError
from kenkufm_youtube_mcp.errors import KenkuYoutubeError


def test_cdp_eval_error_is_kenku_youtube_error():
    assert issubclass(CdpEvalError, KenkuYoutubeError)


async def test_guard_catches_cdp_eval_error():
    async def _boom():
        raise CdpEvalError("page threw")

    out = await server._guard(_boom())
    assert isinstance(out, dict) and "error" in out
