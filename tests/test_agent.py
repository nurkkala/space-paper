"""The login agent definition.

Only the plist is exercised. Actually loading it is launchd's business and would
mean starting a real background process from a test run.
"""

import os
import plistlib

import pytest

from space_paper import agent


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(agent.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(agent, "LOG", tmp_path / "Library/Logs/spacepaper.log")
    return tmp_path


@pytest.fixture
def fake_binary(tmp_path, monkeypatch):
    binary = tmp_path / "bin" / "spacepaper"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr(agent, "executable", lambda: binary)
    return binary


class TestLocation:
    def test_plist_goes_in_the_user_launchagents_directory(self, fake_home):
        assert agent.plist_path() == fake_home / "Library/LaunchAgents" / f"{agent.LABEL}.plist"

    def test_domain_is_the_current_user_gui_session(self):
        """Per-user, so nothing here needs privileges."""
        assert agent.domain() == f"gui/{os.getuid()}"

    def test_not_installed_before_anything_is_written(self, fake_home):
        assert agent.is_installed() is False


class TestPlist:
    def read(self):
        return plistlib.loads(agent.plist_path().read_bytes())

    def test_writes_a_readable_plist(self, fake_home, fake_binary):
        agent.write_plist([])
        assert self.read()["Label"] == agent.LABEL

    def test_names_the_binary_by_absolute_path(self, fake_home, fake_binary):
        """launchd has none of the caller's PATH or virtualenv."""
        agent.write_plist([])
        argv = self.read()["ProgramArguments"]
        assert argv[0] == str(fake_binary)
        assert os.path.isabs(argv[0])

    def test_runs_the_watch_command(self, fake_home, fake_binary):
        agent.write_plist([])
        assert self.read()["ProgramArguments"][1] == "watch"

    def test_carries_appearance_options_through(self, fake_home, fake_binary):
        """The agent should flash exactly as the command that installed it would."""
        agent.write_plist(["--hold", "1.5", "--scale", "1.4"])
        assert self.read()["ProgramArguments"][2:] == ["--hold", "1.5", "--scale", "1.4"]

    def test_starts_at_login(self, fake_home, fake_binary):
        agent.write_plist([])
        assert self.read()["RunAtLoad"] is True

    def test_restarts_on_crash_but_not_on_a_clean_stop(self, fake_home, fake_binary):
        """KeepAlive must not fight `--uninstall`."""
        agent.write_plist([])
        assert self.read()["KeepAlive"] == {"SuccessfulExit": False}

    def test_logs_somewhere_findable(self, fake_home, fake_binary):
        agent.write_plist([])
        written = self.read()
        assert written["StandardOutPath"] == str(agent.LOG)
        assert written["StandardErrorPath"] == str(agent.LOG)

    def test_creates_the_launchagents_directory(self, fake_home, fake_binary):
        assert not agent.plist_path().parent.exists()
        agent.write_plist([])
        assert agent.plist_path().is_file()

    def test_rewriting_replaces_rather_than_appends(self, fake_home, fake_binary):
        agent.write_plist(["--hold", "2"])
        agent.write_plist([])
        assert self.read()["ProgramArguments"][2:] == []

    def test_refuses_when_the_binary_cannot_be_found(self, fake_home, monkeypatch):
        monkeypatch.setattr(agent, "executable", lambda: None)
        with pytest.raises(FileNotFoundError, match="cannot find"):
            agent.write_plist([])


class TestRemoval:
    def test_remove_is_safe_when_nothing_is_installed(self, fake_home):
        agent.remove()  # must not raise

    def test_remove_deletes_the_plist(self, fake_home, fake_binary):
        agent.write_plist([])
        agent.remove()
        assert not agent.is_installed()
