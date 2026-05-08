"""CLI smoke — `--help` returns 0 + usage text."""


from youtube_market_brief import cli


def test_version_prints_and_exits_zero(capsys):
    """--version uses argparse which raises SystemExit(0). Verify exit code + output."""
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "ymb" in captured.out


def test_help_shows_subcommands(capsys):
    rc = cli.main([])
    captured = capsys.readouterr()
    assert rc == 0
    out = captured.out
    for sub in ("health", "config", "run", "discover", "analyze"):
        assert sub in out


def test_config_show_runs(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    rc = cli.main(["config", "show"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "project_root" in captured.out
