from __future__ import annotations


class KenkuYoutubeError(RuntimeError):
    """Base for user-facing errors. str(err) is shown to the MCP client."""


class KenkuUnreachableError(KenkuYoutubeError):
    """Kenku's CDP endpoint or the page WebSocket could not be reached."""


class NoYouTubeViewError(KenkuYoutubeError):
    """No youtube.com page target is open in Kenku FM."""


class PlayerNotReadyError(KenkuYoutubeError):
    """The #movie_player element is not present/ready on the page."""


class VideoNotPlayableError(KenkuYoutubeError):
    """The loaded video reports it is not playable."""


class InvalidInputError(KenkuYoutubeError):
    """A tool argument could not be parsed/validated."""
