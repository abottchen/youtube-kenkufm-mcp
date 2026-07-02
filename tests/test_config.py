import pytest
from kenkufm_youtube_mcp.config import load_config, Config, ConfigError

BASE = {"YOUTUBE_MCP_AUTH_TOKEN": "x" * 16}

def test_defaults_applied():
    cfg = load_config(BASE)
    assert isinstance(cfg, Config)
    assert cfg.port == 3940
    assert cfg.host == "127.0.0.1"
    assert cfg.cdp_url == "http://localhost:9222"
    assert cfg.view_match == "youtube.com"
    assert cfg.log_level == "INFO"

def test_overrides_applied():
    cfg = load_config({
        **BASE,
        "YOUTUBE_MCP_PORT": "4000",
        "KENKU_CDP_URL": "http://localhost:9333",
        "YOUTUBE_MCP_HOST": "0.0.0.0",
        "YOUTUBE_VIEW_URL_MATCH": "music.youtube.com",
        "LOG_LEVEL": "DEBUG",
    })
    assert cfg.port == 4000
    assert cfg.cdp_url == "http://localhost:9333"
    assert cfg.host == "0.0.0.0"
    assert cfg.view_match == "music.youtube.com"
    assert cfg.log_level == "DEBUG"

def test_missing_token_raises():
    with pytest.raises(ConfigError):
        load_config({})

def test_short_token_raises():
    with pytest.raises(ConfigError):
        load_config({"YOUTUBE_MCP_AUTH_TOKEN": "short"})

def test_invalid_port_raises():
    with pytest.raises(ConfigError):
        load_config({"YOUTUBE_MCP_AUTH_TOKEN": "x" * 16, "YOUTUBE_MCP_PORT": "abc"})

def test_out_of_range_port_raises():
    with pytest.raises(ConfigError):
        load_config({"YOUTUBE_MCP_AUTH_TOKEN": "x" * 16, "YOUTUBE_MCP_PORT": "70000"})

def test_auth_token_not_in_repr():
    token = "s3cr3t-token-value-1234"
    cfg = load_config({"YOUTUBE_MCP_AUTH_TOKEN": token})
    assert token not in repr(cfg)
    assert token not in str(cfg)
