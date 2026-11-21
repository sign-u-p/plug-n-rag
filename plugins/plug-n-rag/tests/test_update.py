"""Newer version at session start, `plug-n-rag aktualisieren` (network and `claude` simulated)."""

import json
import subprocess
import time

import pytest

from plug_n_rag import __version__, update as up
from plug_n_rag.cli import main
from plug_n_rag.config import load_config


def bump(v: str) -> str:
    parts = [int(x) for x in v.split(".")]
    parts[-1] += 1
    return ".".join(map(str, parts))


NEWER = bump(__version__)
CACHE_ROOT = "/home/x/.claude/plugins/cache/plug-n-rag/plug-n-rag/"


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setenv("PLUG_N_RAG_PLUGIN_ROOT", CACHE_ROOT + __version__)
    monkeypatch.setenv("PLUG_N_RAG_UPDATES", "")


def latest(v):
    return [lambda: v]


def test_versions_compare_numerically():
    assert up.parse_version("0.10.0") > up.parse_version("0.9.9")
    assert up.UpdateInfo("0.9.3", "0.9.4").newer and not up.UpdateInfo("0.9.3", "0.9.3").newer
    assert not up.UpdateInfo("0.9.3", None).newer


def test_check_is_remembered_and_failures_are_quiet():
    calls = []

    def fetch():
        calls.append(1)
        return NEWER

    assert up.check(fetchers=[fetch]).latest == NEWER
    assert up.check(fetchers=[fetch]).latest == NEWER
    assert len(calls) == 1  # second time from the cache
    assert up.check(force=True, fetchers=[lambda: (_ for _ in ()).throw(OSError("offline"))]).latest is None


def test_http_failure_falls_back_to_git():
    def blocked():
        raise OSError("403 blocked by proxy")

    info = up.check(force=True, fetchers=[blocked, lambda: NEWER])
    assert info.latest == NEWER


def test_session_start_asks_by_default(installed):
    notes = up.session_notes({}, fetchers=latest(NEWER))
    assert len(notes) == 1
    assert f"Neue Version von plug-n-rag verfügbar: {NEWER} (installiert: {__version__})" in notes[0]
    assert "einmal fragen" in notes[0] and "`plug-n-rag aktualisieren`" in notes[0]
    assert "--spaeter" in notes[0]


def test_session_start_is_silent_when_current_off_or_skipped(installed):
    assert up.session_notes({}, fetchers=latest(__version__)) == []
    assert up.session_notes({"updates": "aus"}, fetchers=latest(NEWER)) == []
    assert up.session_notes({"updates": False}, fetchers=latest(NEWER)) == []  # YAML reads `off` as false
    assert up.session_notes({"updates_skip": NEWER}, fetchers=latest(NEWER)) == []
    # a version after the skipped one is offered again
    up._cache_path().unlink()
    assert up.session_notes({"updates_skip": NEWER}, fetchers=latest(bump(NEWER)))


def test_session_start_updates_in_background_when_automatic(installed):
    spawned = []
    notes = up.session_notes({"updates": "automatisch"}, spawn=lambda: spawned.append(1), fetchers=latest(NEWER))
    assert spawned == [1]
    assert "im Hintergrund" in notes[0] and "/reload-plugins" in notes[0]


def test_plugin_from_a_folder_is_only_told_about_git_pull(monkeypatch):
    monkeypatch.setenv("PLUG_N_RAG_PLUGIN_ROOT", "/home/user/plug-n-rag/plugins/plug-n-rag")
    monkeypatch.setenv("PLUG_N_RAG_UPDATES", "automatisch")
    spawned = []
    notes = up.session_notes({}, spawn=lambda: spawned.append(1), fetchers=latest(NEWER))
    assert not spawned and "git pull" in notes[0]


class FakeClaude:
    """Stands in for the `claude` command: records calls, installs NEWER on `plugin update`."""

    def __init__(self, display=False, fail=False):
        self.calls = []
        self.version = __version__
        self.display = display
        self.fail = fail

    def __call__(self, args, timeout=180.0):
        self.calls.append(args)
        if args[:2] == ["plugin", "list"]:
            out = [{"id": up.PLUGIN_ID, "version": self.version, "scope": "user",
                    "installPath": CACHE_ROOT + self.version}]
            if self.display:
                out.append({"id": up.DISPLAY_ID, "version": "0.2.3", "scope": "user"})
            return subprocess.CompletedProcess(args, 0, json.dumps(out), "")
        if args[:2] == ["plugin", "update"]:
            if self.fail:
                return subprocess.CompletedProcess(args, 1, "", "Error: network unreachable")
            if args[2] == up.PLUGIN_ID:
                self.version = NEWER
        return subprocess.CompletedProcess(args, 0, "", "")


def test_update_runs_claude_code_commands_and_moves_the_launcher(installed, monkeypatch):
    monkeypatch.setattr(up.shutil, "which", lambda name: "/usr/bin/" + name)
    fake = FakeClaude(display=True)
    ok, lines = up.update(run=fake, fetchers=latest(NEWER))
    assert ok
    assert ["plugin", "marketplace", "update", "plug-n-rag"] in fake.calls
    assert ["plugin", "update", up.PLUGIN_ID, "-s", "user"] in fake.calls
    assert ["plugin", "update", up.DISPLAY_ID, "-s", "user"] in fake.calls
    assert lines[0] == (f"plug-n-rag aktualisiert: {__version__} → {NEWER}. Die neue Version gilt nach "
                        "/reload-plugins oder ab der nächsten Sitzung.")
    from plug_n_rag.util import user_cache_dir

    assert CACHE_ROOT + NEWER in (user_cache_dir() / "plug-n-rag").read_text(encoding="utf-8")


def test_update_reports_failure(installed, monkeypatch):
    monkeypatch.setattr(up.shutil, "which", lambda name: "/usr/bin/" + name)
    ok, lines = up.update(run=FakeClaude(fail=True), fetchers=latest(NEWER))
    assert not ok
    assert any("Aktualisierung fehlgeschlagen (Error: network unreachable)" in ln for ln in lines)


def test_update_when_current_does_nothing(installed):
    fake = FakeClaude()
    ok, lines = up.update(run=fake, fetchers=latest(__version__))
    assert not ok and lines == [f"plug-n-rag ist aktuell ({__version__})."]
    assert fake.calls == []


def test_later_remembers_the_version_in_the_vault(layout, installed, monkeypatch, capsys):
    monkeypatch.setattr(up, "check", lambda **k: up.UpdateInfo(__version__, NEWER))
    main(["--ordner", str(layout.root), "aktualisieren", "--spaeter"])
    assert f"Version {NEWER} wird nicht mehr angeboten" in capsys.readouterr().out
    assert load_config(layout.config_path)["updates_skip"] == NEWER


def test_session_start_hook_shows_the_offer(layout, installed, monkeypatch, capsys):
    monkeypatch.setattr(up, "check", lambda **k: up.UpdateInfo(__version__, NEWER))
    main(["--ordner", str(layout.root), "session-start"])
    out = capsys.readouterr().out
    assert f"Hinweis: Neue Version von plug-n-rag verfügbar: {NEWER}" in out


def test_status_names_the_version(layout, installed, monkeypatch):
    from plug_n_rag.status import status

    monkeypatch.setattr(up, "check", lambda **k: up.UpdateInfo(__version__, NEWER))
    assert f"Version: {__version__} · neu verfügbar: {NEWER}" in status(layout)
