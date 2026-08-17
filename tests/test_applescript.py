"""AppleScript generation, including the regression pin that matters most.

The original bug in this tool was `tell every desktop to set picture`, which writes
*every display attached to the machine*. It looked correct, ran without error, and
quietly repainted screens the user had not named. Nothing but an explicit assertion
will stop that from coming back, since the broken form is the more obvious one.
"""

from pathlib import Path

import pytest

from space_paper import cli


class Result:
    """Stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def scripts(monkeypatch):
    """Capture generated AppleScript instead of running osascript."""
    captured = []

    def fake(script: str):
        captured.append(script)
        return Result()

    monkeypatch.setattr(cli, "osascript", fake)
    return captured


class TestAsString:
    def test_wraps_in_double_quotes(self):
        assert cli.as_string("plain") == '"plain"'

    def test_escapes_embedded_quotes(self):
        """AppleScript has no single-quoted form, so Python's repr will not do."""
        assert cli.as_string('say "hi"') == '"say \\"hi\\""'

    def test_escapes_backslashes_before_quotes(self):
        assert cli.as_string("back\\slash") == '"back\\\\slash"'

    def test_accepts_a_path(self):
        assert cli.as_string(Path("/tmp/a b.png")) == '"/tmp/a b.png"'

    def test_a_path_with_a_quote_cannot_break_out(self):
        script = cli.as_string(Path('/tmp/ev"il.png'))
        assert script.count('"') == 3  # two delimiters, one escaped
        assert script.endswith('"') and script.startswith('"')


class TestSetPicture:
    def test_targets_one_display_by_id(self, scripts, external):
        cli.set_picture(external, Path("/tmp/x.png"))
        assert f"desktop id {external.cg_id}" in scripts[0]

    def test_never_addresses_every_desktop(self, scripts, external):
        """The regression pin. `every desktop` repaints every attached screen."""
        cli.set_picture(external, Path("/tmp/x.png"))
        assert "every desktop" not in scripts[0]

    def test_quotes_the_path(self, scripts, external):
        cli.set_picture(external, Path("/tmp/a b.png"))
        assert '"/tmp/a b.png"' in scripts[0]

    def test_reports_ok_on_success(self, scripts, external):
        assert cli.set_picture(external, Path("/tmp/x.png")) == "ok"

    def test_surfaces_the_error_text_on_failure(self, monkeypatch, external):
        monkeypatch.setattr(cli, "osascript", lambda s: Result(1, "  -1743 not allowed  "))
        assert cli.set_picture(external, Path("/tmp/x.png")) == "-1743 not allowed"


class TestGoto:
    def test_single_space_display_is_never_paged(self, scripts, builtin):
        """Paging a one-Space display would only disturb whichever screen has focus."""
        cli.goto(builtin, 1, settle=0)
        assert scripts == []

    def test_uses_the_control_hotkey_for_the_requested_space(self, monkeypatch, external):
        captured = []
        monkeypatch.setattr(cli, "osascript", lambda s: captured.append(s) or Result())
        monkeypatch.setattr(cli.dsp, "resolve", lambda uuid: external)
        cli.goto(external, 1, settle=0)
        assert f"key code {cli.KEY_CODES[1]}" in captured[0]
        assert "control down" in captured[0]
