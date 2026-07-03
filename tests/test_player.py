import pytest
import kenkufm_youtube_mcp.youtube.player as player
from kenkufm_youtube_mcp.config import Config
from kenkufm_youtube_mcp.errors import (
    PlayerNotReadyError,
    InvalidInputError,
    VideoNotPlayableError,
    PlaylistFetchError,
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

def test_js_set_loop_scopes_query_and_guards_getvideodata():
    # Scope the <video> lookup to #movie_player (not a bare document query that
    # could hit an ad/mini-player node), and guard getVideoData() in try/catch
    # like READ_JS since it can throw mid-load.
    js = player.js_set_loop(True)
    assert "p.querySelector('video" in js
    assert "document.querySelector('video')" not in js
    assert "try {" in js and "getVideoData()" in js
    assert "currentSrc" in js  # "loaded" allows a media source, not just video_id

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

    out = await player.play_video(CFG, "DyhYzRRMBSU", loop=True)
    assert any("loadVideoById" in c for c in calls)  # reliable load path
    assert any("v.loop = true" in c for c in calls)   # loop applied after load
    assert out["loop"] is True  # return reflects that looping was applied

async def test_play_video_loop_not_applied_reports_false(monkeypatch):
    # If the media element isn't ready when the loop eval runs, js_set_loop
    # returns noVideo — play_video must report loop=False, not blind success.
    async def fake_eval(cfg, expression, **kw):
        if "v.loop" in expression:
            return {"found": True, "noVideo": True}
        return {"found": True, "state": 1, "videoId": "DyhYzRRMBSU",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    out = await player.play_video(CFG, "DyhYzRRMBSU", loop=True)
    assert out["loop"] is False

async def test_play_video_no_loop_skips_loop_eval(monkeypatch):
    calls = []
    async def fake_eval(cfg, expression, **kw):
        calls.append(expression)
        return {"found": True, "state": 1, "videoId": "DyhYzRRMBSU",
                "isPlayable": True, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)
    async def no_sleep(*a, **k): return None
    monkeypatch.setattr(player.asyncio, "sleep", no_sleep)

    out = await player.play_video(CFG, "DyhYzRRMBSU", loop=False)
    assert not any("v.loop" in c for c in calls)
    assert out["loop"] is False  # consistent, self-describing return shape

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

async def test_set_loop_disable_no_video_is_noop(monkeypatch):
    # Disabling looping when nothing is loaded is idempotent — it must not raise.
    async def fake_eval(cfg, expression, **kw):
        if "v.loop" in expression:
            return {"found": True, "noVideo": True}
        return {"found": True, "state": -1, "videoId": None,
                "isPlayable": None, "errorCode": None}
    monkeypatch.setattr(player, "_eval", fake_eval)

    out = await player.set_loop(CFG, False)
    assert out["loop"] is False

async def test_set_volume_out_of_range_raises():
    with pytest.raises(InvalidInputError):
        await player.set_volume(CFG, 150)

# --- _eval retry loop (real _eval, dependencies monkeypatched) ---
async def test_eval_retry_exhaustion_raises(monkeypatch):
    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def always_not_found(ws_url, expression, **kw):
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

    async def flaky_evaluate(ws_url, expression, **kw):
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

# --- list_playlist: pure js builder ---
def test_js_list_playlist_builds_fetch_expression():
    js = player.js_list_playlist("PLabc123", 500)
    assert "youtubei/v1/browse" in js  # InnerTube endpoint
    assert "ytcfg" in js               # reads api key + context from the page
    assert "'PLabc123'" in js          # validated list id, interpolated
    assert "continuation" in js        # paginates through continuation tokens
    assert "lockupViewModel" in js     # current playlist-item format
    assert "playlistVideoRenderer" in js  # legacy fallback still handled

def test_js_list_playlist_cap_is_integer_literal():
    # cap is coerced to a bare int literal, never a quoted/raw string —
    # keeps interpolation injection-safe.
    js = player.js_list_playlist("PLabc123", 250)
    assert "250" in js
    assert "'250'" not in js

def test_js_list_playlist_scopes_continuation_to_item_list():
    # Regression: the continuation token must be taken from the array that holds
    # the video items, not from any continuationItemViewModel anywhere in the
    # response. A playlist page carries unrelated continuations (e.g. side
    # sections); grabbing one of those stops pagination after page 1.
    js = player.js_list_playlist("PLabc123", 500)
    assert "isVideoItem" in js          # detects the video-list array
    assert "node.some(isVideoItem)" in js  # token only from that array

def test_js_list_playlist_collects_only_the_first_video_array():
    # Regression: a page may also carry a recommended/related shelf of video
    # items. Only the first (primary) video array is collected, so that shelf
    # can't inflate the list or overwrite the pagination token.
    js = player.js_list_playlist("PLabc123", 500)
    assert "primaryCollected" in js

def test_js_list_playlist_truncated_covers_failure_and_overshoot():
    # Regression: truncated must be true when a continuation fetch fails
    # mid-run, when a page overshoots the cap, or when a token remains — not
    # `!!token` alone, which misses the first two and silently returns a
    # partial list as complete.
    js = player.js_list_playlist("PLabc123", 500)
    assert "incomplete" in js                 # failed-mid-pagination signal
    assert "incomplete || !!token || videos.length > CAP" in js

def test_js_list_playlist_authenticates_request():
    # Regression: private/unlisted (owner-only) playlists 403 with
    # PERMISSION_DENIED unless the InnerTube POST carries the page's
    # SAPISIDHASH auth header, derived from the session cookie.
    js = player.js_list_playlist("PLabc123", 500)
    assert "SAPISIDHASH" in js       # auth scheme
    assert "SAPISID" in js           # reads the session cookie
    assert "Authorization" in js     # sets the auth header on the fetch

# --- list_playlist: async shaping/error-mapping (deps monkeypatched) ---
async def test_list_playlist_shapes_videos(monkeypatch):
    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def fake_eval(ws_url, expression, **kw):
        return {"ok": True, "title": "Tavern", "truncated": False, "videos": [
            {"videoId": "abc12345678", "title": "Fire"},
            {"videoId": "def12345678", "title": "Crackle"},
        ]}

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", fake_eval)

    out = await player.list_playlist(CFG, "PLabc123")
    assert out["playlistId"] == "PLabc123"
    assert out["title"] == "Tavern"
    assert out["count"] == 2
    assert out["truncated"] is False
    assert out["videos"][0] == {
        "videoId": "abc12345678",
        "title": "Fire",
        "url": "https://www.youtube.com/watch?v=abc12345678",
    }
    assert out["videos"][1]["videoId"] == "def12345678"

async def test_list_playlist_passes_truncated_through(monkeypatch):
    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def fake_eval(ws_url, expression, **kw):
        return {"ok": True, "title": "Big", "truncated": True, "videos": [
            {"videoId": "abc12345678", "title": "x"},
        ]}

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", fake_eval)

    out = await player.list_playlist(CFG, "PLabc123")
    assert out["truncated"] is True

async def test_list_playlist_uses_extended_timeout(monkeypatch):
    # The fetch loop can do several continuation round-trips, so this call must
    # use a larger timeout than the 8s default.
    seen = {}

    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def fake_eval(ws_url, expression, **kw):
        seen.update(kw)
        return {"ok": True, "title": "T", "truncated": False, "videos": [
            {"videoId": "abc12345678", "title": "x"},
        ]}

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", fake_eval)

    await player.list_playlist(CFG, "PLabc123")
    assert seen.get("timeout", 8.0) > 8.0

@pytest.mark.parametrize("raw", [
    {"ok": False, "reason": "notFound"},
    {"ok": False, "reason": "notYouTube"},
    {"ok": False, "reason": "forbidden"},
    {"ok": False, "reason": "parse"},
    {"ok": False, "reason": "weird"},
    None,
])
async def test_list_playlist_failure_raises(monkeypatch, raw):
    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def fake_eval(ws_url, expression, **kw):
        return raw

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", fake_eval)

    with pytest.raises(PlaylistFetchError):
        await player.list_playlist(CFG, "PLabc123")

async def test_list_playlist_forbidden_has_distinct_message(monkeypatch):
    # A 403 (private playlist, session not authorized) maps to its own message,
    # not the generic notFound/parse text.
    async def fake_resolve_ws(cfg):
        return "ws://x"

    async def fake_eval(ws_url, expression, **kw):
        return {"ok": False, "reason": "forbidden"}

    monkeypatch.setattr(player, "_resolve_ws", fake_resolve_ws)
    monkeypatch.setattr(player.cdp_client, "evaluate", fake_eval)

    with pytest.raises(PlaylistFetchError) as ei:
        await player.list_playlist(CFG, "PLabc123")
    assert "signed in" in str(ei.value).lower()
