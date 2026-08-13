"""The palette design, stated as assertions.

These thresholds are the reason `bright` exists. They were arrived at by measuring
candidate colors, and until now lived only in a comment -- which means one careless
hex edit could quietly undo the work. Each number below is a design decision, not an
observation of current behavior, so a failure here is a question ("is this still the
design?") rather than a bug report.
"""

import itertools

import pytest

from space_paper.cli import BRIGHT, DARK, PALETTE_SETS, PALETTES

from .colorimetry import ciede2000, contrast_ratio, lightness, srgb_to_lab

# A wallpaper is mostly seen as slivers around open windows. Two grounds closer than
# this are not tellable apart through a gap, whatever they look like side by side.
MIN_SEPARATION = 20.0

# Palettes are assigned by position, so a four-Space setup only ever sees the first
# four. They carry a higher bar because they are the common case.
MIN_SEPARATION_FIRST_FOUR = 25.0
FIRST_N = 4

# Lightness is the cue that survives being seen a few pixels at a time.
MIN_LIGHTNESS_SPREAD = 25.0

# Large decorative text, but the word should read cleanly on its ground.
MIN_CONTRAST = 4.5


def pairs(names):
    return itertools.combinations(names, 2)


def separation(family, a, b):
    return ciede2000(srgb_to_lab(family[a][0]), srgb_to_lab(family[b][0]))


class TestBrightFamily:
    def test_every_pair_is_distinguishable_in_a_sliver(self):
        worst = min((separation(BRIGHT, a, b), a, b) for a, b in pairs(BRIGHT))
        distance, a, b = worst
        assert distance >= MIN_SEPARATION, (
            f"{a} and {b} are only {distance:.1f} apart (CIEDE2000); "
            f"the bright family requires {MIN_SEPARATION}"
        )

    def test_the_first_four_are_held_to_a_higher_bar(self):
        first = list(BRIGHT)[:FIRST_N]
        worst = min((separation(BRIGHT, a, b), a, b) for a, b in pairs(first))
        distance, a, b = worst
        assert distance >= MIN_SEPARATION_FIRST_FOUR, (
            f"{a} and {b} open the rotation but are only {distance:.1f} apart; "
            f"a four-Space setup sees exactly these. Reorder the family."
        )

    def test_lightness_is_spread_not_held_constant(self):
        levels = [lightness(ground) for ground, _ in BRIGHT.values()]
        spread = max(levels) - min(levels)
        assert spread >= MIN_LIGHTNESS_SPREAD, (
            f"L* spans only {spread:.1f}; holding lightness constant is precisely "
            "what made the dark family unreadable in a sliver"
        )


class TestBothFamilies:
    @pytest.mark.parametrize("name", sorted(PALETTES))
    def test_word_reads_on_its_ground(self, name):
        ground, word = PALETTES[name]
        ratio = contrast_ratio(ground, word)
        assert ratio >= MIN_CONTRAST, f"{name}: word/ground contrast is only {ratio:.2f}:1"

    @pytest.mark.parametrize("name", sorted(PALETTES))
    def test_colors_are_six_digit_hex(self, name):
        for color in PALETTES[name]:
            assert len(color) == 7 and color[0] == "#"
            int(color[1:], 16)

    def test_names_are_unique_across_families(self):
        """WORD=palette resolves without naming a family, which needs unique names."""
        overlap = set(BRIGHT) & set(DARK)
        assert not overlap, f"ambiguous palette name(s): {sorted(overlap)}"
        assert len(PALETTES) == len(BRIGHT) + len(DARK)

    def test_every_family_is_reachable_by_name(self):
        assert set(PALETTE_SETS) == {"bright", "dark"}
        assert PALETTE_SETS["bright"] is BRIGHT

    def test_dark_is_kept_but_is_not_the_default(self):
        """Documented as the weaker family; retained deliberately, not by accident."""
        worst = min(separation(DARK, a, b) for a, b in pairs(DARK))
        assert worst < MIN_SEPARATION
        assert list(PALETTE_SETS)[0] == "bright"
