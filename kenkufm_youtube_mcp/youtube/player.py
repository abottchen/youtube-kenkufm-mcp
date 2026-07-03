from __future__ import annotations

import asyncio

from ..cdp import client as cdp_client
from ..cdp import targets as cdp_targets
from ..config import Config
from ..errors import (
    InvalidInputError,
    PlayerNotReadyError,
    PlaylistFetchError,
    VideoNotPlayableError,
)

STATE_NAMES = {-1: "unstarted", 0: "ended", 1: "playing", 2: "paused",
               3: "buffering", 5: "cued"}

# Stop paginating a playlist after this many items (safety bound on very long
# playlists). If more remain, list_playlist flags the result truncated.
# NOTE: this number is also stated in prose in server.list_playlist's docstring
# and in README.md — keep those in sync if you change it.
PLAYLIST_ITEM_CAP = 500
# The playlist fetch loop can do several continuation round-trips, so it needs a
# larger ceiling than cdp_client.evaluate's 8s default.
PLAYLIST_EVAL_TIMEOUT = 25.0

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


def js_list_playlist(list_id: str, cap: int) -> str:
    """Async in-page expression: fetch a playlist's items via YouTube's internal
    InnerTube API and return {ok, title, videos, truncated}.

    Runs in the youtube.com page context, so it is same-origin with the API and
    carries the logged-in cookies. It never touches #movie_player, so current
    playback is undisturbed.

    A recursive walk over each response collects the playlist's items and its
    continuation token. YouTube's current playlist page renders items as
    `lockupViewModel` (videoId in `contentId`, title in
    `metadata.lockupMetadataViewModel.title.content`); the older
    `playlistVideoRenderer` is handled too in case it's still served. Walking
    the tree — rather than hard-coding deep paths — resists YouTube's frequent
    format churn.

    The continuation token is taken *only* from the array that holds the video
    items (the token is a sibling of the items in that list). A playlist page
    also carries unrelated continuations elsewhere; picking one of those would
    stop pagination after the first page.

    `list_id` must be pre-validated (ids.parse_playlist_id) and `cap` an int, so
    interpolating them into the expression stays injection-safe.
    """
    return """(async () => {
  try {
    if (typeof ytcfg === 'undefined' || !ytcfg.get) return {ok:false, reason:'notYouTube'};
    const key = ytcfg.get('INNERTUBE_API_KEY');
    const context = ytcfg.get('INNERTUBE_CONTEXT');
    if (!key || !context) return {ok:false, reason:'notYouTube'};
    const CAP = %(cap)d;
    const listId = '%(list_id)s';
    const videos = [];
    let title = null;
    let token = null;

    // YouTube's InnerTube API treats a bare {context, key} POST as logged-out,
    // so private / unlisted (owner-only) playlists 403 with PERMISSION_DENIED.
    // Authenticate the way the page itself does: an
    //   Authorization: SAPISIDHASH <ts>_<sha1(ts + ' ' + SAPISID + ' ' + origin)>
    // header derived from the session cookie. Public playlists work either way;
    // if no cookie is available we simply omit it and stay logged-out.
    const origin = location.origin;
    const cookie = (n) => (document.cookie.match(new RegExp('(?:^|; )' + n + '=([^;]+)')) || [])[1];
    const sapisid = cookie('SAPISID') || cookie('__Secure-3PAPISID') || cookie('__Secure-1PAPISID');
    let auth = null;
    if (sapisid && typeof crypto !== 'undefined' && crypto.subtle) {
      const ts = Math.floor(Date.now() / 1000);
      const digest = await crypto.subtle.digest(
        'SHA-1', new TextEncoder().encode(ts + ' ' + sapisid + ' ' + origin));
      const hex = Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
      auth = 'SAPISIDHASH ' + ts + '_' + hex;
    }

    // Find a continuation `token` string anywhere under a node — robust to the
    // exact nesting (the view-model era buries it deeper than the old renderer).
    const findToken = (n) => {
      if (!n || typeof n !== 'object') return null;
      if (typeof n.token === 'string') return n.token;
      for (const k in n) { const t = findToken(n[k]); if (t) return t; }
      return null;
    };

    // A renderer title may be a bare string or a {simpleText|runs} object,
    // depending on era — normalize both to a plain string (or null).
    const asText = (t) => (typeof t === 'string' ? t
      : (t && (t.simpleText || (t.runs && t.runs[0] && t.runs[0].text))) || null);

    // Is this array element a playlist video item (either format)?
    const isVideoItem = (x) => !!(x && typeof x === 'object' && (
      (x.lockupViewModel && x.lockupViewModel.contentType === 'LOCKUP_CONTENT_TYPE_VIDEO'
        && x.lockupViewModel.contentId)
      || (x.playlistVideoRenderer && x.playlistVideoRenderer.videoId)));

    const pushItem = (x) => {
      if (x.lockupViewModel) {
        const l = x.lockupViewModel;
        const mv = l.metadata && l.metadata.lockupMetadataViewModel;
        videos.push({videoId: l.contentId, title: (mv && mv.title && mv.title.content) || null});
      } else {
        const r = x.playlistVideoRenderer, t = r.title || {};
        const name = (t.runs && t.runs[0] && t.runs[0].text) || t.simpleText || null;
        videos.push({videoId: r.videoId, title: name});
      }
    };

    let primaryCollected = false;
    const walk = (node) => {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) {
        if (node.some(isVideoItem)) {
          // The first video-item array in a page is the playlist's own list:
          // collect only from it, and take the continuation token only from its
          // sibling continuation entry. A page can also carry a recommended /
          // related shelf of video items; pulling those in would inflate the
          // result and hijack pagination onto the wrong feed.
          if (!primaryCollected) {
            primaryCollected = true;
            for (const x of node) {
              if (isVideoItem(x)) pushItem(x);
              else if (x && (x.continuationItemViewModel || x.continuationItemRenderer)) {
                const tok = findToken(x.continuationItemViewModel || x.continuationItemRenderer);
                if (tok) token = tok;
              }
            }
          }
          return;
        }
        for (const x of node) walk(x);
        return;
      }
      if (title === null && node.playlistMetadataRenderer) {
        title = asText(node.playlistMetadataRenderer.title);
      }
      if (title === null && node.playlistHeaderRenderer) {
        title = asText(node.playlistHeaderRenderer.title);
      }
      if (title === null && node.pageHeaderRenderer
          && typeof node.pageHeaderRenderer.pageTitle === 'string') {
        title = node.pageHeaderRenderer.pageTitle;
      }
      for (const k in node) walk(node[k]);
    };

    // Reset the per-page "primary list already taken" latch before each page.
    const collectPage = (node) => { primaryCollected = false; walk(node); };

    let lastStatus = 0;
    const post = async (body) => {
      const headers = {'Content-Type': 'application/json'};
      if (auth) { headers['Authorization'] = auth; headers['X-Goog-AuthUser'] = '0'; headers['X-Origin'] = origin; }
      const resp = await fetch('/youtubei/v1/browse?key=' + encodeURIComponent(key), {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
      lastStatus = resp.status;
      if (!resp.ok) return null;
      return await resp.json();
    };

    let data = await post({context, browseId: 'VL' + listId});
    if (!data) return {ok:false, reason: lastStatus === 403 ? 'forbidden' : 'notFound'};
    collectPage(data);
    if (videos.length === 0) return {ok:false, reason:'notFound'};

    let incomplete = false;
    while (token && videos.length < CAP) {
      const next = token;
      token = null;
      data = await post({context, continuation: next});
      if (!data) { incomplete = true; break; }  // a page failed to load mid-run
      collectPage(data);
    }
    // The list is truncated if a continuation fetch failed part-way, more pages
    // remained when we hit the CAP, or a page overshot the CAP (tail dropped
    // below). Deriving this from `token` alone would miss the first and third.
    const truncated = incomplete || !!token || videos.length > CAP;
    if (videos.length > CAP) videos.length = CAP;
    return {ok:true, title, videos, truncated};
  } catch (e) {
    return {ok:false, reason:'parse'};
  }
})()""" % {"cap": int(cap), "list_id": list_id}


def js_set_loop(enabled: bool) -> str:
    # Loop the current video via the HTML5 media element's `loop` property.
    # The player's setLoop() does not loop on the Kenku watch page (neither a
    # single video nor a playlist wraps — verified live), so it is not used;
    # looping is single-video only. Playlist looping is left to the client.
    #
    # Scope the query to #movie_player's own <video> (a bare document query can
    # hit an ad/mini-player node), guard getVideoData() like READ_JS does (it
    # can throw mid-load), and treat the video as "loaded" when it has either a
    # video_id or a media source — video_id is briefly absent right after a load.
    flag = "true" if enabled else "false"
    body = (
        "const v = p.querySelector('video.html5-main-video')"
        " || p.querySelector('video');"
        " let d = {};"
        " try { d = p.getVideoData() || {}; } catch (e) {}"
        " if (!v || !(d.video_id || v.currentSrc)) return {found:true, noVideo:true};"
        f" v.loop = {flag}; return {{found:true}};"
    )
    return js_call(body)


def js_simple(action: str) -> str:
    return js_call(f"{_SIMPLE[action]} return {{found:true}};")


def js_seek(seconds: float) -> str:
    return js_call(f"p.seekTo({float(seconds)}, true); return {{found:true}};")


def js_set_volume(volume: int) -> str:
    return js_call(f"p.setVolume({int(volume)}); return {{found:true}};")


async def _resolve_ws(cfg: Config) -> str:
    targets = await asyncio.to_thread(cdp_targets.fetch_targets, cfg.cdp_url)
    return cdp_targets.select_youtube_target(targets, cfg.view_match)


async def _eval(cfg: Config, expression: str, retries: int = 6, delay: float = 0.5,
                timeout: float = 8.0):
    ws_url = await _resolve_ws(cfg)
    for _ in range(retries):
        result = await cdp_client.evaluate(ws_url, expression, timeout=timeout)
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


async def play_video(cfg: Config, video_id: str, start_seconds: int | None = None,
                     loop: bool = False) -> dict:
    await _eval(cfg, js_load_video(video_id, start_seconds))
    await asyncio.sleep(0.6)  # let the SPA swap in the new video before reading
    state = await get_state(cfg)
    applied = False
    if loop:
        # Set video.loop only after the player is ready — loadVideoById resets
        # the media element's loop flag while the new video is loading. Reflect
        # whether it actually took (the media element may not be ready yet)
        # rather than reporting success blindly.
        result = await _eval(cfg, js_set_loop(True))
        applied = not (isinstance(result, dict) and result.get("noVideo"))
    return {**state, "loop": applied}


async def play_playlist(cfg: Config, list_id: str, index: int | None = None,
                        start_seconds: int | None = None) -> dict:
    await _eval(cfg, js_load_playlist(list_id, index, start_seconds))
    await asyncio.sleep(0.6)
    return await get_state(cfg)


_PLAYLIST_FETCH_MESSAGES = {
    "notYouTube": (
        "The Kenku view isn't on a real youtube.com page, so the playlist "
        "could not be read. Open a youtube.com page in Kenku and try again."
    ),
    "notFound": (
        "Playlist not found or not accessible — it may be private, empty, or "
        "the ID may be wrong."
    ),
    "forbidden": (
        "The playlist is private or unlisted and the Kenku YouTube session "
        "isn't authorized to read it. Make sure Kenku is signed in to the "
        "account that owns the playlist."
    ),
    "parse": (
        "Could not read the playlist data from YouTube (unexpected response "
        "format)."
    ),
}


async def list_playlist(cfg: Config, list_id: str) -> dict:
    """List a playlist's videos without disturbing playback.

    Reads the playlist out-of-band via an in-page fetch (see js_list_playlist),
    so #movie_player is never touched. Returns
    {playlistId, title, count, truncated, videos:[{videoId, title, url}]}.
    """
    raw = await _eval(
        cfg, js_list_playlist(list_id, PLAYLIST_ITEM_CAP),
        timeout=PLAYLIST_EVAL_TIMEOUT,
    )
    if not (isinstance(raw, dict) and raw.get("ok")):
        reason = raw.get("reason") if isinstance(raw, dict) else None
        raise PlaylistFetchError(
            _PLAYLIST_FETCH_MESSAGES.get(reason, _PLAYLIST_FETCH_MESSAGES["parse"])
        )
    videos = [
        {
            "videoId": v.get("videoId"),
            "title": v.get("title"),
            "url": f"https://www.youtube.com/watch?v={v.get('videoId')}",
        }
        for v in raw.get("videos") or []
    ]
    return {
        "playlistId": list_id,
        "title": raw.get("title"),
        "count": len(videos),
        "truncated": bool(raw.get("truncated")),
        "videos": videos,
    }


async def set_loop(cfg: Config, enabled: bool) -> dict:
    result = await _eval(cfg, js_set_loop(enabled))
    # Only enabling needs a loaded video; disabling is an idempotent no-op when
    # nothing is loaded, so don't error on it.
    if enabled and isinstance(result, dict) and result.get("noVideo"):
        raise InvalidInputError("No video is currently loaded to loop.")
    return {**(await get_state(cfg)), "loop": enabled}


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
