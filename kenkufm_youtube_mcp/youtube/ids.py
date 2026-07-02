from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..errors import InvalidInputError

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYLIST_ID_RE = re.compile(r"^(?:PL|UU|LL|OL|RD|FL|SI|OLAK)[A-Za-z0-9_-]{2,}$")
_PATH_VIDEO_RE = re.compile(r"^/(?:shorts|embed|v)/([A-Za-z0-9_-]{11})")


def parse_video_id(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise InvalidInputError("No video was provided.")
    if _VIDEO_ID_RE.fullmatch(v):
        return v
    u = urlparse(v)
    if u.scheme in ("http", "https"):
        host = (u.hostname or "").lower()
        if host == "youtu.be" or host.endswith(".youtu.be"):
            cand = u.path.lstrip("/").split("/", 1)[0]
            if _VIDEO_ID_RE.fullmatch(cand):
                return cand
        if (
            host == "youtube.com"
            or host.endswith(".youtube.com")
            or host == "youtube-nocookie.com"
            or host.endswith(".youtube-nocookie.com")
        ):
            qs = parse_qs(u.query)
            if qs.get("v") and _VIDEO_ID_RE.fullmatch(qs["v"][0]):
                return qs["v"][0]
            m = _PATH_VIDEO_RE.match(u.path)
            if m:
                return m.group(1)
    raise InvalidInputError(f"Could not extract a YouTube video ID from: {value!r}")


def parse_playlist_id(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise InvalidInputError("No playlist was provided.")
    u = urlparse(v)
    if u.query:
        qs = parse_qs(u.query)
        if qs.get("list") and _PLAYLIST_ID_RE.fullmatch(qs["list"][0]):
            return qs["list"][0]
    if _PLAYLIST_ID_RE.fullmatch(v):
        return v
    raise InvalidInputError(f"Could not extract a YouTube playlist ID from: {value!r}")
