# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server that controls the **real youtube.com web view running inside Kenku FM**
(an Electron/Chromium app) over the Chrome DevTools Protocol. Because it drives the
actual logged-in Premium page rather than an embed or API, playback is ad-free with no
embedding limits. Companion to a separate `spotify-mcp` for D&D game audio in Discord.

The server runs in WSL2; Kenku FM runs on Windows and must be launched with
`--remote-debugging-port=9222`, with WSL mirrored networking so `localhost:9222` reaches it.

## Commands

```bash
# Install (with dev deps for tests)
.venv/bin/pip install -e ".[dev]"

# Run the server (reads .env from cwd; listens on http://127.0.0.1:3940/mcp)
.venv/bin/python -m kenkufm_youtube_mcp

# Smoke test — connects to a running Kenku, prints YouTube view state as JSON.
# Does NOT need YOUTUBE_MCP_AUTH_TOKEN (no HTTP server is started).
.venv/bin/python -m kenkufm_youtube_mcp.smoke

# Tests (pytest asyncio_mode = auto — async tests need no decorator)
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_ids.py                 # one file
.venv/bin/python -m pytest tests/test_ids.py::test_bare_id   # one test
```

The full unit suite runs without Kenku or a browser — every CDP/network boundary is
mocked. Only `smoke.py` requires a live Kenku instance.

## Architecture

Request flow for every tool call is a single, stateless round-trip — nothing is cached
between calls:

```
tool (server.py)
  → player op (youtube/player.py)
    → _resolve_ws:  cdp/targets.fetch_targets  (sync urllib GET /json/list, run in a thread)
                    cdp/targets.select_youtube_target  (pick the youtube.com page target)
    → cdp/client.evaluate  (async websocket, ONE Runtime.evaluate on that target)
```

Each layer has one job:

- **`config.py`** — frozen `Config` dataclass, `load_config` (validates token ≥16 chars,
  port range), and `load_dotenv`. **Real environment always wins over `.env`**
  (`os.environ.setdefault`); a missing `.env` is a silent no-op, so it's fully optional.
- **`server.py`** — `build_mcp` defines the 13 FastMCP tools; `BearerAuthASGI` is a
  pure-ASGI bearer-token wrapper; `build_app` composes them. Auth passes **non-HTTP scopes
  (lifespan, websocket) straight through** so the wrapped Starlette app's session-manager
  lifespan still runs — don't gate those or the server won't start.
- **`youtube/player.py`** — builds the JavaScript that calls methods on the page's
  `#movie_player` (`loadVideoById`, `playVideo`, `nextVideo`, `setVolume`, …), plus
  `normalize_state` (maps YouTube's numeric player states via `STATE_NAMES`).
- **`youtube/ids.py`** — parses/validates video and playlist IDs from URLs or bare IDs.
- **`cdp/`** — the only code that talks to Kenku. `targets.py` is sync (urllib);
  `client.py` is async (websockets).
- **`errors.py`** — every user-facing error subclasses `KenkuYoutubeError`, and
  **`str(err)` is what the MCP client sees.** Write error messages for the end user.

### Cross-cutting conventions to preserve

- **Error handling is centralized.** `server._guard` wraps each player coroutine and turns
  any `KenkuYoutubeError` into `{"error": str(exc)}`. ID-parse errors are caught *before*
  `_guard` inside the tool functions (see `play_video`/`play_playlist`). New tools should
  follow the same pattern; don't let exceptions escape a tool.
- **Player-readiness retry.** `player._eval` polls up to 6× (0.5s apart) while the page
  returns `{found: false}`, then raises `PlayerNotReadyError`. The injected JS must return
  `{found: false}` when `#movie_player` is absent and `{found: true}` otherwise for this to
  work — keep that contract when adding player operations.
- **JS-injection safety.** Player JS is built by string interpolation, so IDs must go
  through `ids.parse_*` (regex-constrained) first, and numeric args through `int()`/`float()`.
  Never interpolate raw user strings into the evaluate expression.
- After a video/playlist load, the code `sleep(0.6)`s before reading state to let the SPA
  swap in the new video.

## Configuration

All config is env-driven (via `.env` or real env). Full table is in `README.md`. The only
required var is `YOUTUBE_MCP_AUTH_TOKEN` (≥16 chars; generate with `openssl rand -hex 32`).
Clients connect to `http://127.0.0.1:3940/mcp` with `Authorization: Bearer <token>`
(Streamable HTTP transport).

## Design docs

`docs/superpowers/specs/` and `docs/superpowers/plans/` hold the original design spec and
implementation plan (gitignored). Read them for the "why" behind decisions.
