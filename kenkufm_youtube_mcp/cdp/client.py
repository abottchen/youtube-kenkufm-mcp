from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets
from websockets.exceptions import WebSocketException

from ..errors import KenkuUnreachableError, KenkuYoutubeError


class CdpEvalError(KenkuYoutubeError):
    """The page evaluation returned a CDP-level or JS exception."""


async def evaluate(ws_url: str, expression: str, timeout: float = 8.0) -> Any:
    """Open a CDP page WebSocket, run one Runtime.evaluate, return its value."""
    msg_id = 1
    try:
        async with websockets.connect(ws_url, max_size=None) as ws:
            await ws.send(json.dumps({
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
            }))

            async def _await_matching() -> dict:
                while True:
                    data = json.loads(await ws.recv())
                    if data.get("id") == msg_id:
                        return data

            data = await asyncio.wait_for(_await_matching(), timeout=timeout)
    except (OSError, WebSocketException, asyncio.TimeoutError) as exc:
        raise KenkuUnreachableError(
            f"Lost the CDP connection to the YouTube view ({exc})."
        ) from exc

    if "error" in data:
        raise CdpEvalError(f"CDP error: {data['error']}")
    result = data.get("result", {})
    if "exceptionDetails" in result:
        raise CdpEvalError(f"Page evaluation threw: {result['exceptionDetails']}")
    return result.get("result", {}).get("value")
