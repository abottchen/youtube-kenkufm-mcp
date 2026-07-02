from __future__ import annotations

import asyncio

from ..cdp import client as cdp_client
from ..cdp import targets as cdp_targets
from ..config import Config
from ..errors import InvalidInputError, PlayerNotReadyError, VideoNotPlayableError

STATE_NAMES = {-1: "unstarted", 0: "ended", 1: "playing", 2: "paused",
               3: "buffering", 5: "cued"}

READ_JS = """(() => {
  const p = document.querySelector('#movie_player');
  if (!p || typeof p.getPlayerState !== 'function') return {found:false};
  const v = document.querySelector('video');
  let d = {};
  try { d = p.getVideoData() || {}; } catch (e) {}
  return {
    found: true,
    state: p.getPlayerState(),
    currentTime: p.getCurrentTime ? p.getCurrentTime() : (v ? v.currentTime : null),
    duration: p.getDuration ? p.getDuration() : (v ? v.duration : null),
    volume: p.getVolume ? p.getVolume() : null,
    muted: p.isMuted ? p.isMuted() : (v ? v.muted : null),
    videoId: d.video_id || null,
    title: d.title || null,
    author: d.author || null,
    isPlayable: ('isPlayable' in d) ? d.isPlayable : null,
    errorCode: d.errorCode || null
  };
})()"""

_SIMPLE = {
    "pause": "p.pauseVideo();",
    "resume": "p.playVideo();",
    "next": "p.nextVideo();",
    "previous": "p.previousVideo();",
    "mute": "p.mute();",
    "unmute": "p.unMute();",
}


def normalize_state(raw: dict | None) -> dict:
    raw = raw or {}
    if not raw.get("found"):
        raise PlayerNotReadyError("The YouTube player is not ready on the current page.")
    code = raw.get("state")
    return {
        "state": STATE_NAMES.get(code, f"unknown({code})"),
        "videoId": raw.get("videoId"),
        "title": raw.get("title"),
        "author": raw.get("author"),
        "isPlayable": raw.get("isPlayable"),
        "errorCode": raw.get("errorCode"),
        "currentTime": raw.get("currentTime"),
        "duration": raw.get("duration"),
        "volume": raw.get("volume"),
        "muted": raw.get("muted"),
    }


def js_call(body: str) -> str:
    return ("(() => { const p = document.querySelector('#movie_player');"
            " if (!p) return {found:false};"
            f" {body} }})()")


def js_load_video(video_id: str, start_seconds: int | None) -> str:
    args = "{videoId: '%s'%s}" % (
        video_id,
        "" if start_seconds is None else f", startSeconds: {int(start_seconds)}",
    )
    return js_call(f"p.loadVideoById({args}); return {{found:true}};")


def js_load_playlist(list_id: str, index: int | None, start_seconds: int | None) -> str:
    opts = [f"list: '{list_id}'", "listType: 'playlist'"]
    if index is not None:
        opts.append(f"index: {int(index)}")
    if start_seconds is not None:
        opts.append(f"startSeconds: {int(start_seconds)}")
    return js_call("p.loadPlaylist({%s}); return {found:true};" % ", ".join(opts))


def js_simple(action: str) -> str:
    return js_call(f"{_SIMPLE[action]} return {{found:true}};")


def js_seek(seconds: float) -> str:
    return js_call(f"p.seekTo({float(seconds)}, true); return {{found:true}};")


def js_set_volume(volume: int) -> str:
    return js_call(f"p.setVolume({int(volume)}); return {{found:true}};")


async def _resolve_ws(cfg: Config) -> str:
    targets = await asyncio.to_thread(cdp_targets.fetch_targets, cfg.cdp_url)
    return cdp_targets.select_youtube_target(targets, cfg.view_match)


async def _eval(cfg: Config, expression: str, retries: int = 6, delay: float = 0.5):
    ws_url = await _resolve_ws(cfg)
    for _ in range(retries):
        result = await cdp_client.evaluate(ws_url, expression)
        if isinstance(result, dict) and result.get("found") is False:
            await asyncio.sleep(delay)
            continue
        return result
    raise PlayerNotReadyError(
        "The YouTube player never became ready (no #movie_player on the page). "
        "Make sure a video or playlist is loaded in the Kenku YouTube view."
    )


async def get_state(cfg: Config) -> dict:
    state = normalize_state(await _eval(cfg, READ_JS))
    if state["isPlayable"] is False:
        raise VideoNotPlayableError(
            f"The current video is not playable (errorCode={state['errorCode']})."
        )
    return state


async def play_video(cfg: Config, video_id: str, start_seconds: int | None = None) -> dict:
    await _eval(cfg, js_load_video(video_id, start_seconds))
    await asyncio.sleep(0.6)  # let the SPA swap in the new video before reading
    return await get_state(cfg)


async def play_playlist(cfg: Config, list_id: str, index: int | None = None,
                        start_seconds: int | None = None) -> dict:
    await _eval(cfg, js_load_playlist(list_id, index, start_seconds))
    await asyncio.sleep(0.6)
    return await get_state(cfg)


async def simple_action(cfg: Config, action: str) -> dict:
    if action not in _SIMPLE:
        raise InvalidInputError(f"Unknown action: {action}")
    await _eval(cfg, js_simple(action))
    return await get_state(cfg)


async def seek(cfg: Config, seconds: float) -> dict:
    await _eval(cfg, js_seek(seconds))
    return await get_state(cfg)


async def set_volume(cfg: Config, volume: int) -> dict:
    if not 0 <= int(volume) <= 100:
        raise InvalidInputError("volume must be between 0 and 100")
    await _eval(cfg, js_set_volume(volume))
    return await get_state(cfg)
