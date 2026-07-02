from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient
from kenkufm_youtube_mcp.server import BearerAuthASGI

TOKEN = "secrettoken1234567890"

async def _dummy(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        await PlainTextResponse("ok")(scope, receive, send)

def test_rejects_without_token():
    with TestClient(BearerAuthASGI(_dummy, TOKEN)) as client:
        assert client.get("/mcp").status_code == 401

def test_rejects_wrong_token():
    with TestClient(BearerAuthASGI(_dummy, TOKEN)) as client:
        r = client.get("/mcp", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

def test_accepts_valid_token():
    with TestClient(BearerAuthASGI(_dummy, TOKEN)) as client:
        r = client.get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200
        assert r.text == "ok"
