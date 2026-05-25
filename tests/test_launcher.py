from client import launcher


def test_launcher_reports_missing_local_config(monkeypatch, capsys) -> None:
    monkeypatch.setattr(launcher, "CONFIG_PATH", launcher.ROOT / "server" / "missing.local.json")

    result = launcher.main()

    assert result == 1
    assert "Missing server/config.local.json" in capsys.readouterr().out
