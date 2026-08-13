"""The user config: round-tripping, location, and rejecting malformed files."""

import pytest

from space_paper import config as cfg


class TestLocation:
    def test_honors_xdg_config_home(self, config_home):
        assert cfg.path() == config_home / "spacepaper" / "config.toml"

    def test_falls_back_to_dot_config(self, monkeypatch, tmp_path):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(cfg.Path, "home", classmethod(lambda cls: tmp_path))
        assert cfg.path() == tmp_path / ".config" / "spacepaper" / "config.toml"

    def test_path_does_not_depend_on_the_package_name(self):
        """Renaming the package must not orphan existing configs."""
        assert cfg.path().parent.name == "spacepaper"

    def test_exists_is_false_before_anything_is_written(self, config_home):
        assert cfg.exists() is False


class TestRoundTrip:
    def test_defaults_when_there_is_no_file(self, config_home):
        loaded = cfg.load()
        assert loaded.palette_set == "bright"
        assert loaded.badge is True
        assert loaded.screens == []

    def test_save_then_load_preserves_everything(self, config_home):
        original = cfg.Config(
            palette_set="dark",
            badge=False,
            screens=[
                cfg.Screen(match="ACME 27", words=["Code", "Write"]),
                cfg.Screen(match="builtin", words=[]),
            ],
        )
        cfg.save(original)
        loaded = cfg.load()
        assert loaded.palette_set == "dark"
        assert loaded.badge is False
        assert [s.match for s in loaded.screens] == ["ACME 27", "builtin"]
        assert loaded.screens[0].words == ["Code", "Write"]

    def test_empty_word_list_survives_and_means_leave_alone(self, config_home):
        """The mechanism that keeps a laptop panel untouched; must not vanish."""
        cfg.save(cfg.Config(screens=[cfg.Screen(match="builtin", words=[])]))
        assert cfg.load().screens[0].words == []

    def test_per_display_overrides_round_trip(self, config_home):
        cfg.save(cfg.Config(screens=[
            cfg.Screen(match="ACME 27", words=["A"], palette_set="dark", badge=False),
        ]))
        screen = cfg.load().screens[0]
        assert screen.palette_set == "dark"
        assert screen.badge is False

    def test_absent_overrides_stay_none_rather_than_defaulting(self, config_home):
        """None means "inherit"; False would be a real per-display choice."""
        cfg.save(cfg.Config(screens=[cfg.Screen(match="ACME 27", words=["A"])]))
        screen = cfg.load().screens[0]
        assert screen.palette_set is None
        assert screen.badge is None

    def test_save_creates_missing_directories(self, config_home):
        assert not cfg.path().parent.exists()
        cfg.save(cfg.Config())
        assert cfg.path().is_file()

    @pytest.mark.parametrize("name", [
        "DELL U2720Q", 'Odd "Quoted" Display', "Back\\slash", "Built-in Retina Display",
    ])
    def test_display_names_needing_escapes_round_trip(self, config_home, name):
        cfg.save(cfg.Config(screens=[cfg.Screen(match=name, words=["X"])]))
        assert cfg.load().screens[0].match == name


class TestLookup:
    def test_for_display_finds_by_exact_match(self):
        config = cfg.Config(screens=[cfg.Screen(match="ACME 27", words=["A"])])
        assert config.for_display("ACME 27").words == ["A"]

    def test_for_display_returns_none_when_absent(self):
        assert cfg.Config().for_display("Nothing") is None


class TestMalformed:
    def test_broken_toml_is_reported_not_swallowed(self, config_home):
        cfg.path().parent.mkdir(parents=True)
        cfg.path().write_text("this is not = = toml")
        with pytest.raises(cfg.ConfigError):
            cfg.load()

    def test_display_entry_must_be_a_table(self, config_home):
        cfg.path().parent.mkdir(parents=True)
        cfg.path().write_text('[displays]\n"ACME 27" = "not a table"\n')
        with pytest.raises(cfg.ConfigError, match="not a table"):
            cfg.load()

    def test_words_must_be_a_list_of_strings(self, config_home):
        cfg.path().parent.mkdir(parents=True)
        cfg.path().write_text('[displays."ACME 27"]\nwords = [1, 2]\n')
        with pytest.raises(cfg.ConfigError, match="list of strings"):
            cfg.load()

    def test_words_must_not_be_a_bare_string(self, config_home):
        cfg.path().parent.mkdir(parents=True)
        cfg.path().write_text('[displays."ACME 27"]\nwords = "Code"\n')
        with pytest.raises(cfg.ConfigError, match="list of strings"):
            cfg.load()


class TestRendering:
    def test_output_carries_the_explanatory_header(self, config_home):
        """The file is meant to be hand-edited, so it explains itself."""
        assert cfg.dumps(cfg.Config()).lstrip().startswith("#")

    def test_no_machine_measurements_are_written(self, config_home):
        """Only intent is stored; anything measurable goes stale and misleads.

        Comments are excluded deliberately: the header names these very things in
        order to say they are *not* recorded, so it must not trip its own check.
        """
        text = cfg.dumps(cfg.Config(screens=[cfg.Screen(match="ACME 27", words=["A"])]))
        data = "\n".join(
            line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
        ).lower()
        for leaked in ("3840", "2160", "menubar", "dock", "uuid", "resolution", "native"):
            assert leaked not in data, f"config records the measured value {leaked!r}"
