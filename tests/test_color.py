"""Color helpers: blending, luminance, and the badge's chip colors."""

import pytest

from space_paper.cli import BRIGHT, DARK, chip_colors, luminance, mix

from .colorimetry import contrast_ratio


class TestMix:
    def test_t_of_one_is_the_destination(self):
        assert mix("#000000", "#FFFFFF", 1.0) == "#FFFFFF"

    def test_t_of_zero_is_the_source(self):
        assert mix("#336699", "#FFFFFF", 0.0) == "#336699"

    def test_midpoint_is_halfway_per_channel(self):
        assert mix("#000000", "#FFFFFF", 0.5) == "#808080"

    def test_output_is_uppercase_six_digit_hex(self):
        result = mix("#123456", "#abcdef", 0.37)
        assert result.startswith("#") and len(result) == 7
        assert result[1:] == result[1:].upper()

    @pytest.mark.parametrize("t", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_channels_stay_in_range(self, t):
        for i in (1, 3, 5):
            assert 0 <= int(mix("#FF0000", "#0000FF", t)[i:i + 2], 16) <= 255


class TestLuminance:
    def test_black_and_white_anchor_the_scale(self):
        assert luminance("#000000") == pytest.approx(0.0)
        assert luminance("#FFFFFF") == pytest.approx(1.0)

    def test_green_weighs_more_than_blue(self):
        """The coefficients are perceptual, not equal thirds."""
        assert luminance("#00FF00") > luminance("#FF0000") > luminance("#0000FF")


class TestChipColors:
    """The badge must stay dark-on-light whichever way its palette runs.

    The bright family puts the dark tone in the word and the light one in the
    ground; the dark family is the other way about. Sorting by role would invert
    the badge between families, so it sorts by luminance instead.
    """

    @pytest.mark.parametrize("name", sorted(BRIGHT))
    def test_bright_family_gives_light_chip_dark_text(self, name):
        chip, text = chip_colors(*BRIGHT[name])
        assert luminance(chip) > luminance(text)

    @pytest.mark.parametrize("name", sorted(DARK))
    def test_dark_family_also_gives_light_chip_dark_text(self, name):
        chip, text = chip_colors(*DARK[name])
        assert luminance(chip) > luminance(text)

    @pytest.mark.parametrize("name", sorted({**BRIGHT, **DARK}))
    def test_label_is_legible_on_its_chip(self, name):
        chip, text = chip_colors(*{**BRIGHT, **DARK}[name])
        assert contrast_ratio(chip, text) >= 7.0

    @pytest.mark.parametrize("name", sorted({**BRIGHT, **DARK}))
    def test_chip_is_never_darker_than_its_ground(self, name):
        """The chip is the light element; it must not invert on any palette."""
        ground, _ = {**BRIGHT, **DARK}[name]
        chip, _ = chip_colors(*{**BRIGHT, **DARK}[name])
        assert luminance(chip) >= luminance(ground)

    @pytest.mark.parametrize("name", sorted({**BRIGHT, **DARK}))
    def test_badge_is_delineated_from_its_ground(self, name):
        """The badge needs an edge, and which element supplies it varies.

        On a dark ground the near-white chip carries it outright. On an already-light
        ground -- stone, butter -- the chip has nowhere left to go and dissolves,
        and the border (drawn in the text color) carries it instead. Requiring both
        is impossible; requiring either is the actual guarantee.
        """
        ground, word = {**BRIGHT, **DARK}[name]
        chip, border = chip_colors(ground, word)
        fill_edge = contrast_ratio(ground, chip)
        line_edge = contrast_ratio(ground, border)
        assert max(fill_edge, line_edge) >= 3.0, (
            f"{name}: chip/ground {fill_edge:.2f}:1 and border/ground "
            f"{line_edge:.2f}:1 -- the badge has no visible edge on this ground"
        )

    def test_order_of_arguments_does_not_flip_the_result(self):
        assert chip_colors("#5C9BD6", "#0F2A44") == chip_colors("#0F2A44", "#5C9BD6")
