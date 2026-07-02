import json
import pytest
import websockets
from kenkufm_youtube_mcp.cdp.client import evaluate, CdpEvalError

async def _serve(handler):
    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"ws://127.0.0.1:{port}"

async def test_evaluate_returns_value():
    async def handler(ws):
        req = json.loads(await ws.recv())
        assert req["method"] == "Runtime.evaluate"
        await ws.send(json.dumps(
            {"id": req["id"], "result": {"result": {"type": "object", "value": {"found": True, "state": 1}}}}
        ))
    server, url = await _serve(handler)
    try:
        assert await evaluate(url, "whatever") == {"found": True, "state": 1}
    finally:
        server.close()
        await server.wait_closed()

async def test_evaluate_raises_on_page_exception():
    async def handler(ws):
        req = json.loads(await ws.recv())
        await ws.send(json.dumps(
            {"id": req["id"], "result": {"result": {}, "exceptionDetails": {"text": "boom"}}}
        ))
    server, url = await _serve(handler)
    try:
        with pytest.raises(CdpEvalError):
            await evaluate(url, "throw 1")
    finally:
        server.close()
        await server.wait_closed()
