import os

from kenkufm_youtube_mcp import config


def test_load_dotenv_parses_keys(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# a comment\n"
        'YOUTUBE_MCP_AUTH_TOKEN="abcdef0123456789"\n'
        "export KENKU_CDP_URL=http://localhost:9999\n"
        "NOEQUALSLINE\n"
        "\n"
        "LOG_LEVEL=DEBUG\n"
    )
    env: dict[str, str] = {}
    config.load_dotenv(str(p), env)
    assert env["YOUTUBE_MCP_AUTH_TOKEN"] == "abcdef0123456789"  # surrounding quotes stripped
    assert env["KENKU_CDP_URL"] == "http://localhost:9999"      # `export ` prefix handled
    assert env["LOG_LEVEL"] == "DEBUG"
    assert "NOEQUALSLINE" not in env                            # lines without `=` are skipped


def test_load_dotenv_does_not_override_existing(tmp_path):
    p = tmp_path / ".env"
    p.write_text("KENKU_CDP_URL=http://from-file\n")
    env = {"KENKU_CDP_URL": "http://from-real-env"}
    config.load_dotenv(str(p), env)
    assert env["KENKU_CDP_URL"] == "http://from-real-env"       # real environment wins


def test_load_dotenv_missing_file_is_noop():
    env: dict[str, str] = {}
    config.load_dotenv("/nonexistent-dir-xyz/.env", env)
    assert env == {}


def test_load_dotenv_defaults_to_os_environ(tmp_path):
    p = tmp_path / ".env"
    p.write_text("KFYT_TEST_ONLY_KEY=hello\n")
    try:
        config.load_dotenv(str(p))
        assert os.environ.get("KFYT_TEST_ONLY_KEY") == "hello"
    finally:
        os.environ.pop("KFYT_TEST_ONLY_KEY", None)
