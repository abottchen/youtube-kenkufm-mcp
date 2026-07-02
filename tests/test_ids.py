import pytest
from kenkufm_youtube_mcp.youtube.ids import parse_video_id, parse_playlist_id
from kenkufm_youtube_mcp.errors import InvalidInputError

VID = "DyhYzRRMBSU"  # 11 chars

@pytest.mark.parametrize("value", [
    VID,
    f"https://www.youtube.com/watch?v={VID}",
    f"https://www.youtube.com/watch?v={VID}&list=PLxyz&index=3",
    f"https://youtu.be/{VID}",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"https://music.youtube.com/watch?v={VID}",
])
def test_parse_video_id_ok(value):
    assert parse_video_id(value) == VID

@pytest.mark.parametrize("value", [
    "",
    "   ",
    "not a url",
    "https://example.com/watch?v=abc",
    # Spoofed hosts must not be treated as YouTube.
    f"https://evilyoutube.com/watch?v={VID}",
    "https://notyoutube.com.evil.com/watch?v=DyhYzRRMBSU",
    # Trailing newline (URL-encoded) must not slip through a $-anchored regex.
    f"https://www.youtube.com/watch?v={VID}%0A",
])
def test_parse_video_id_rejects(value):
    with pytest.raises(InvalidInputError):
        parse_video_id(value)

@pytest.mark.parametrize("value,expected", [
    ("PLwLatQMJ3ug9Y7-Sj0kEChZQjK3nfWm1", "PLwLatQMJ3ug9Y7-Sj0kEChZQjK3nfWm1"),
    ("https://www.youtube.com/playlist?list=PLabc123DEF", "PLabc123DEF"),
    ("https://www.youtube.com/watch?v=DyhYzRRMBSU&list=PLabc123DEF", "PLabc123DEF"),
])
def test_parse_playlist_id_ok(value, expected):
    assert parse_playlist_id(value) == expected

@pytest.mark.parametrize("value", [
    "",
    "randomtext",
    "https://example.com/x",
    # A list= value that is not a well-formed playlist ID must be rejected,
    # never returned (it later gets interpolated into JS).
    "https://www.youtube.com/watch?v=DyhYzRRMBSU&list=');alert(1);//",
])
def test_parse_playlist_id_rejects(value):
    with pytest.raises(InvalidInputError):
        parse_playlist_id(value)
