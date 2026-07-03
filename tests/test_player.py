import pytest
import kenkufm_youtube_mcp.youtube.player as player
from kenkufm_youtube_mcp.config import Config
from kenkufm_youtube_mcp.errors import (
    PlayerNotReadyError,
    InvalidInputError,
    VideoNotPlayableError,
)

CFG = Config(auth_token="x" * 16)

# --- pure: normalize_state ---
def test_normalize_maps_state_and_fields():
    raw = {"found": True, "state": 1, "currentTime": 5.0, "duration": 200.0,
           "volume": 15, "muted": False, "videoId": "abc", "title": "T",
           "author": "A", "isPlayable": True, "errorCode": None}
    out = player.normalize_state(raw)
    assert out["state"] == "playing"
    assert out["videoId"] == "abc"
    assert out["volume"] == 15

def test_normalize_unknown_state_code():
    assert player.normalize_state({"found": True, "state": 99})["state"] == "unknown(99)"

def test_normalize_not_found_raises():
    with pytest.raises(PlayerNotReadyError):
        player.normalize_state({"found": False})

# --- pure: js builders ---
def test_js_load_video_contains_id_and_start():
    js = player.js_load_video("DyhYzRRMBSU", 30)
    assert "loadVideoById" in js and "DyhYzRRMBSU" in js and "startSeconds: 30" in js

def test_js_load_video_never_uses_playlist():
    # Single-video load must not go through loadPlaylist (that mechanism does not
    # loop on the real watch page and can wedge the player with api.invalidparam).
    js = player.js_load_video("DyhYzRRMBSU", 30)
    assert "loadVideoById" in js
    assert "loadPlaylist" not in js

def test_js_load_playlist_has_no_setloop():
    # Playlist looping is out of scope — setLoop does not loop on the watch page.
    js = player.js_load_playlist("PLabc123", None, None)
    assert "setLoop" not in js

def test_js_set_loop_true_uses_video_loop():
    # Looping is single-video only, via the HTML5 media element.
    js = player.js_set_loop(True)
    assert "v.loop = true" in js
    assert "loadPlaylist" not in js
    assert "setLoop" not in js
    assert "noVideo" in js

def test_js_set_loop_false_disables_video_loop():
    js = player.js_set_loop(False)
    assert "v.loop = false" in js
    assert "setLoop" not in js
    assert "loadPlaylist" not in js

def test_js_set_volume_coerces_int():
    assert "setVolume(50)" in player.js_set_volume(50)

# --- async orchestration (deps monkeypatched) ---
async def test_play_video_loads_then_reads_state(monkeypatch):
    calls = []

    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        if "loadVideoById" in expression:
            return {"found": True}
        return {"found": True, "state": 1, "videoId": "DyhYzRRMBSU",
                "isPlayable": True, "errorCode": None}

    monkeypatch.setattr(player, "_eval", fake_eval)
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    out = await player.play_video(CFG, "DyhYzRRMBSU")
    assert out["state"] == "playing"
    assert any("loadVideoById" in c for c in calls)

async def test_play_video_loop_sets_video_loop(monkeypatch):
    calls = []
    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        return {"found": True, "state": 1, "videoId": "DyhYzRRMBSU",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    await player.play_video(CFG, "DyhYzRRMBSU", loop=True)
    assert any("loadVideoById" in c for c in calls)  # reliable load path
    assert any("v.loop = true" in c for c in calls)   # loop applied after load

async def test_play_video_no_loop_skips_loop_eval(monkeypatch):
    calls = []
    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        return {"found": True, "state": 1, "videoId": "DyhYzRRMBSU",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    await player.play_video(CFG, "DyhYzRRMBSU", loop=False)
    assert not any("v.loop" in c for c in calls)

async def test_play_playlist_loads_without_loop(monkeypatch):
    calls = []
    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        return {"found": True, "state": 1, "videoId": "x",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    await player.play_playlist(CFG, "PLabc123")
    assert any("loadPlaylist" in c for c in calls)
    assert not any("setLoop" in c for c in calls)  # no playlist looping

async def test_set_loop_echoes_enabled_and_builds_video_loop(monkeypatch):
    calls = []
    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        return {"found": True, "state": 1, "videoId": "abc",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)

    out = await player.set_loop(CFG, True)
    assert out["loop"] is True
    assert out["state"] == "playing"
    assert any("v.loop = true" in c for c in calls)  # confirms set_loop -> js_set_loop

async def test_set_loop_disable_builds_video_loop_false(monkeypatch):
    calls = []
    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        return {"found": True, "state": 2, "videoId": "abc",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)

    out = await player.set_loop(CFG, False)
    assert out["loop"] is False
    assert any("v.loop = false" in c for c in calls)

async def test_set_loop_no_video_raises(monkeypatch):
    async def fake_eval(cfg, expression, **kw):
        return {"found": True, "noVideo": True}
    monkeypatch.setattr(player, "_eval", fake_eval)

    with pytest.raises(InvalidInputError):
        await player.set_loop(CFG, True)

async def test_set_volume_out_of_range_raises():
    with pytest.raises(InvalidInputError):
        await player.set_volume(CFG, 150)

# --- _eval retry loop (real _eval, dependencies monkeypatched) ---
async def test_eval_retry_exhaustion_raises(monkeypatch):
    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def always_not_found(ws_url, expression):
        return {"found": False}

    async def no_sleep(*a, **k):
        return None

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", always_not_found)
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    with pytest.raises(PlayerNotReadyError):
        await player._eval(CFG, "expr")

async def test_eval_retry_recovers(monkeypatch):
    calls = []

    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def flaky_evaluate(ws_url, expression):
        calls.append(expression)
        if len(calls) <= 3:
            return {"found": False}
        return {"found": True, "state": 1}

    async def no_sleep(*a, **k):
        return None

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", flaky_evaluate)
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    result = await player._eval(CFG, "expr")
    assert result == {"found": True, "state": 1}
    assert len(calls) == 4

# --- get_state VideoNotPlayableError branch ---
async def test_get_state_not_playable_raises(monkeypatch):
    async def fake_eval(cfg, expression, **kw):
        return {"found": True, "state": 5, "isPlayable": False, "errorCode": 150}

    monkeypatch.setattr(player, "_eval", fake_eval)

    with pytest.raises(VideoNotPlayableError):
        await player.get_state(CFG)

# --- additional pure builder coverage ---
def test_js_load_playlist_contains_all_opts():
    js = player.js_load_playlist("PLabc123", 2, 30)
    assert "loadPlaylist" in js
    assert "'PLabc123'" in js
    assert "listType: 'playlist'" in js
    assert "index: 2" in js
    assert "startSeconds: 30" in js

def test_js_seek_contains_seek_to():
    assert "seekTo(12.5" in player.js_seek(12.5)

def test_js_simple_pause_contains_pause_video():
    assert "pauseVideo" in player.js_simple("pause")
