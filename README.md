# kenkufm-youtube-mcp

An MCP server that controls the **real youtube.com web view running inside
Kenku FM** via the Chrome DevTools Protocol. Companion to `spotify-mcp` for
running D&D game audio into Discord.

## How it works

Kenku FM is an Electron/Chromium app. Launched with a remote-debugging port, its
youtube.com browser view is a CDP `page` target. Each tool resolves that target
(`GET /json/list`), opens a WebSocket to it, and runs one `Runtime.evaluate`
calling a method on the page's `#movie_player` (`loadVideoById`, `playVideo`,
`pauseVideo`, `nextVideo`, `setVolume`, ...). Because it drives the real,
logged-in Premium page, playback is ad-free and there are no embedding limits.

## One-time setup

1. **Launch Kenku FM with remote debugging** (Windows). Fully quit Kenku first
   (Electron's single-instance lock will otherwise just focus the running
   window). Append the flag to the Start Menu shortcut target:
   ```
   C:\Users\<you>\AppData\Local\kenku-fm-win32-x64\kenku-fm.exe --remote-debugging-port=9222
   ```
2. **WSL mirrored networking** must be enabled so `localhost:9222` from WSL2
   reaches Kenku on Windows. Verify:
   ```bash
   curl -s http://localhost:9222/json/version
   ```
3. **Install** (WSL2):
   ```bash
   cd ~/projects/youtube-mcp
   python3 -m venv .venv
   .venv/bin/pip install -e .
   ```
4. **Smoke test** with a video playing in a Kenku YouTube view:
   ```bash
   .venv/bin/python -m kenkufm_youtube_mcp.smoke
   ```
   Expected: JSON with `"state": "playing"` and the video title.

## Run

Configuration is read from a `.env` file in the project directory (gitignored),
falling back to real environment variables. Create one from the template:

```bash
cp .env.example .env
# edit .env and set YOUTUBE_MCP_AUTH_TOKEN (generate one: openssl rand -hex 32)
chmod 600 .env
```

Then start the server:

```bash
.venv/bin/python -m kenkufm_youtube_mcp
# -> listening on http://127.0.0.1:3940/mcp
```

### As a systemd user service

The service runs from the project directory and reads the same `.env` there, so
no separate environment file is needed:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/kenkufm-youtube-mcp.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kenkufm-youtube-mcp
```

## MCP client config

Connect to `http://127.0.0.1:3940/mcp` with header
`Authorization: Bearer <your-token>` (Streamable HTTP transport).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `YOUTUBE_MCP_AUTH_TOKEN` | **required** | Bearer token (≥16 chars) |
| `YOUTUBE_MCP_PORT` | `3940` | Loopback HTTP port |
| `YOUTUBE_MCP_HOST` | `127.0.0.1` | Bind host |
| `KENKU_CDP_URL` | `http://localhost:9222` | Kenku CDP base |
| `YOUTUBE_VIEW_URL_MATCH` | `youtube.com` | Substring to find the YouTube target |
| `LOG_LEVEL` | `INFO` | Log level |

## Tools

`get_playback_state`, `play_video`, `play_playlist`, `pause`, `resume`, `next`,
`previous`, `seek`, `set_volume`, `mute`, `unmute`, `set_loop`.

`play_video` accepts `loop=true` to repeat a single video infinitely, and
`set_loop(enabled)` toggles looping of the currently playing video. Looping is
single-video only (it uses the HTML5 `<video>.loop` property); looping a
playlist is left to the client (e.g. replaying videos by ID).
