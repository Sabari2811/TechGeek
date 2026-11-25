from app.terminal import Terminal


def test_monitor_only_safety_hold_is_visible_on_every_terminal_refresh(monkeypatch, capsys):
    monkeypatch.setattr(Terminal, "clear", staticmethod(lambda: None))
    monkeypatch.setattr("app.terminal.kill_switch_status", lambda: (True, "unresolved order journal"))

    Terminal.set_safety_hold(True, "STARTUP SAFETY HOLD — 10 unresolved journal item(s).")
    try:
        Terminal.waiting(spot=24000.0, reason="Read-only market monitoring.")
        output = capsys.readouterr().out
        assert "MONITOR ONLY — ORDER EXECUTION DISABLED" in output
        assert "STARTUP SAFETY HOLD" in output
        assert "ENTRY KILL SWITCH" in output
        assert "Read-only market monitoring." in output
    finally:
        Terminal.set_safety_hold(False)
