"""Word-to-palette assignment, and reading words back out of file names."""

from pathlib import Path

import pytest
import typer

from space_paper.cli import BRIGHT, PALETTE_SETS, parse_word, recover_word, rotation

BRIGHT_ORDER = list(BRIGHT)


class TestRotation:
    def test_returns_declaration_order(self):
        assert rotation("bright") == BRIGHT_ORDER

    def test_families_are_addressable_by_name(self):
        for name in PALETTE_SETS:
            assert rotation(name) == list(PALETTE_SETS[name])

    def test_unknown_family_is_a_usage_error(self):
        with pytest.raises(typer.BadParameter, match="unknown set"):
            rotation("neon")


class TestParseWordByPosition:
    @pytest.mark.parametrize("position", range(1, 9))
    def test_position_selects_the_nth_palette(self, position):
        word, palette = parse_word("Any", position, BRIGHT_ORDER)
        assert palette == BRIGHT_ORDER[position - 1]

    def test_rotation_wraps_past_the_end(self):
        """Nine Spaces against eight palettes reuses the first, rather than failing."""
        _, ninth = parse_word("Any", 9, BRIGHT_ORDER)
        assert ninth == BRIGHT_ORDER[0]

    def test_the_first_four_are_the_separated_ones(self):
        """Guards the ordering: these are what a four-Space setup actually gets."""
        got = [parse_word("W", n, BRIGHT_ORDER)[1] for n in (1, 2, 3, 4)]
        assert got == ["sky", "meadow", "apricot", "blush"]

    def test_word_is_returned_unchanged(self):
        assert parse_word("Beacon", 1, BRIGHT_ORDER)[0] == "Beacon"

    def test_surrounding_whitespace_is_trimmed(self):
        assert parse_word("  Beacon  ", 1, BRIGHT_ORDER)[0] == "Beacon"


class TestParseWordExplicitPalette:
    def test_equals_form_overrides_position(self):
        word, palette = parse_word("Beacon=lagoon", 1, BRIGHT_ORDER)
        assert (word, palette) == ("Beacon", "lagoon")

    def test_palette_may_come_from_the_other_family(self):
        """Names are unique across families, so this resolves without --set."""
        assert parse_word("Beacon=slate", 1, BRIGHT_ORDER)[1] == "slate"

    def test_palette_name_is_case_insensitive(self):
        assert parse_word("Beacon=LAGOON", 1, BRIGHT_ORDER)[1] == "lagoon"

    def test_whitespace_around_the_equals_is_tolerated(self):
        assert parse_word(" Beacon = lagoon ", 1, BRIGHT_ORDER) == ("Beacon", "lagoon")

    def test_only_the_last_equals_separates(self):
        """rpartition, so a word may itself contain an equals sign."""
        assert parse_word("a=b=lagoon", 1, BRIGHT_ORDER) == ("a=b", "lagoon")

    def test_unknown_palette_is_a_usage_error(self):
        with pytest.raises(typer.BadParameter, match="unknown palette"):
            parse_word("Beacon=chartreuse", 1, BRIGHT_ORDER)

    def test_empty_word_is_a_usage_error(self):
        with pytest.raises(typer.BadParameter, match="word is empty"):
            parse_word("=lagoon", 1, BRIGHT_ORDER)


class TestRecoverWord:
    """`config --init` reads existing setups back out of the file names it wrote."""

    def test_reads_the_word_from_a_generated_name(self):
        assert recover_word(Path("main-sky-3840x2160.png")) == "Main"

    def test_returns_none_for_no_picture(self):
        assert recover_word(None) is None

    def test_ignores_files_this_tool_did_not_name(self):
        assert recover_word(Path("DefaultAerial.heic")) is None

    def test_ignores_names_whose_palette_is_unknown(self):
        """Guards against `beacon-4k-...` style strays being read as words."""
        assert recover_word(Path("beacon-4k-3840x2160.png")) is None

    def test_hyphenated_words_survive_the_round_trip(self):
        assert recover_word(Path("deep-work-sky-3840x2160.png")) == "Deep-work"

    def test_round_trips_with_the_name_apply_writes(self):
        word, palette = parse_word("Beacon", 5, BRIGHT_ORDER)
        assert recover_word(Path(f"{word.lower()}-{palette}-3840x2160.png")) == "Beacon"
