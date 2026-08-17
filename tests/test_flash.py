"""Deciding what to flash, and where.

Only the pure half is exercised: which displays moved, and which word a Space gets.
Putting a window on screen is AppKit's business and would flash on the machine
running the tests.
"""

import dataclasses
from pathlib import Path

import pytest

from space_paper import cli
from space_paper import config as cfg
from space_paper import displays as dsp
from space_paper import flash

from .conftest import make_display, make_space


def at(display: dsp.Display, space: int) -> dsp.Display:
    """The same display, with `space` as its current Space (0 for none current)."""
    spaces = tuple(make_space(s.number, current=(s.number == space)) for s in display.spaces)
    return dataclasses.replace(display, spaces=spaces)


class TestLandings:
    def test_a_display_whose_space_changed_is_reported_once(self, external):
        before = {external.uuid: 1}
        found = flash.landings(before, [at(external, 3)])
        assert found == [flash.Landing(display=at(external, 3), space=3)]

    def test_a_display_that_did_not_move_is_skipped(self, external):
        assert flash.landings({external.uuid: 2}, [at(external, 2)]) == []

    def test_only_the_display_that_moved_flashes(self, external, builtin):
        """Swapping Space on one screen must not flash on the other."""
        before = {external.uuid: 1, builtin.uuid: 1}
        found = flash.landings(before, [at(external, 4), at(builtin, 1)])
        assert [(f.display.uuid, f.space) for f in found] == [(external.uuid, 4)]

    def test_a_display_absent_from_the_snapshot_counts_as_changed(self, external, builtin):
        """A screen just plugged in: saying where it is beats staying quiet."""
        before = {external.uuid: 1}
        found = flash.landings(before, [at(external, 1), at(builtin, 1)])
        assert [f.display.uuid for f in found] == [builtin.uuid]

    def test_a_display_with_no_current_space_is_skipped(self, external):
        """No current Space means nothing to name, whatever the snapshot said."""
        assert flash.landings({external.uuid: 2}, [at(external, 0)]) == []
        assert flash.landings({}, [make_display(spaces=0)]) == []


class TestSnapshot:
    def test_keys_each_display_by_uuid_to_its_current_space(self, monkeypatch, external, builtin):
        monkeypatch.setattr(dsp, "displays", lambda: [at(external, 3), at(builtin, 1)])
        assert flash.snapshot() == {external.uuid: 3, builtin.uuid: 1}


class TestWordFor:
    """Which word a landing gets: the config first, then the wallpaper's file name."""

    def picture(self, display, space, name):
        spaces = tuple(
            dataclasses.replace(s, picture=Path(name) if s.number == space else s.picture)
            for s in display.spaces
        )
        return dataclasses.replace(display, spaces=spaces)

    def test_config_wins_when_it_covers_the_space(self, monkeypatch, external):
        loaded = cfg.Config(screens=[cfg.Screen(match="ACME", words=["Code", "Write=clay"])])
        monkeypatch.setattr(dsp, "resolve", lambda match: external)
        assert cli.word_for(external, 1, loaded) == ("Code", list(cli.BRIGHT)[0])
        assert cli.word_for(external, 2, loaded) == ("Write", "clay")

    def test_a_space_beyond_the_configured_words_gets_nothing(self, monkeypatch, external):
        loaded = cfg.Config(screens=[cfg.Screen(match="ACME", words=["Code"])])
        monkeypatch.setattr(dsp, "resolve", lambda match: external)
        assert cli.word_for(external, 2, loaded) is None

    def test_falls_back_to_the_wallpaper_file_name(self, external):
        """Before a config exists, the file names this tool wrote carry the answer."""
        screen = self.picture(external, 2, "/x/write-meadow-3840x2160.png")
        assert cli.word_for(screen, 2, None) == ("Write", "meadow")

    @pytest.mark.parametrize("name", [None, "/x/DefaultAerial.heic", "/x/holiday.png"])
    def test_a_space_with_neither_says_nothing(self, external, name):
        screen = self.picture(external, 2, name) if name else external
        assert cli.word_for(screen, 2, None) is None
