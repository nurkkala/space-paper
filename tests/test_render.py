"""Render a real wallpaper and check the layout guarantees in its pixels.

These are the only tests that would have caught the menu bar bug: the word field
deliberately overfills its box so the pattern bleeds off every edge, and without
clipping that overfill spilled straight back over the band reserved for the menu
bar. The HTML looked right; only the pixels showed otherwise.

Rendered small -- the layout is proportional, so a 1200x800 sheet exercises the same
geometry as a 4K one in a fraction of the time.
"""

import pytest

from space_paper.cli import BRIGHT, PALETTES, chip_colors, shoot, wallpaper_html

from .conftest import needs_chrome

pytestmark = [pytest.mark.render, needs_chrome]

WIDTH, HEIGHT = 1200, 800
MENUBAR, DOCK = 24, 60
WORD, PALETTE = "Athena", "meadow"


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    from PIL import Image

    target = tmp_path_factory.mktemp("render") / "wallpaper.png"
    shoot(
        wallpaper_html(WORD, PALETTE, HEIGHT, menubar=MENUBAR, dock=DOCK, badge=True),
        target, WIDTH, HEIGHT,
    )
    return Image.open(target).convert("RGB")


@pytest.fixture(scope="module")
def unbadged(tmp_path_factory):
    from PIL import Image

    target = tmp_path_factory.mktemp("render") / "plain.png"
    shoot(
        wallpaper_html(WORD, PALETTE, HEIGHT, menubar=MENUBAR, dock=DOCK, badge=False),
        target, WIDTH, HEIGHT,
    )
    return Image.open(target).convert("RGB")


def first_lettered_row(image) -> int:
    """Topmost row carrying anything other than flat ground."""
    ground = rgb(PALETTES[PALETTE][0])
    width, height = image.size
    for y in range(height):
        if any(image.getpixel((x, y)) != ground for x in range(0, width, 2)):
            return y
    return height


def count(image, color, box) -> int:
    left, top, right, bottom = box
    want = rgb(color)
    return sum(
        1
        for y in range(top, bottom)
        for x in range(left, right)
        if image.getpixel((x, y)) == want
    )


class TestCanvas:
    def test_renders_at_the_requested_size(self, rendered):
        assert rendered.size == (WIDTH, HEIGHT)


class TestMenuBarBand:
    def test_the_band_is_solid_ground(self, rendered):
        """Every pixel above the menu bar line, not merely most of them."""
        ground = rgb(PALETTES[PALETTE][0])
        for y in range(MENUBAR):
            for x in range(0, WIDTH, 3):
                assert rendered.getpixel((x, y)) == ground, f"lettering at y={y}"

    def test_lettering_resumes_immediately_below_the_band(self, rendered):
        """The band must be a clean reservation, not the field pushed far down."""
        ground = rgb(PALETTES[PALETTE][0])
        strip = [
            rendered.getpixel((x, y))
            for y in range(MENUBAR, MENUBAR + 60)
            for x in range(0, WIDTH, 3)
        ]
        assert any(p != ground for p in strip)

    def test_a_zero_height_band_lets_lettering_ride_higher(self, tmp_path):
        """The band is what holds lettering down, not some incidental margin.

        Stated as a comparison rather than "lettering reaches row 0": the topmost
        glyph row is centered part-way down whatever box it is given, so an absolute
        threshold would assert an accident of the type size instead of the band.
        """
        from PIL import Image

        target = tmp_path / "noband.png"
        shoot(
            wallpaper_html(WORD, PALETTE, HEIGHT, menubar=0, dock=DOCK, badge=False),
            target, WIDTH, HEIGHT,
        )
        unbanded = first_lettered_row(Image.open(target).convert("RGB"))
        assert unbanded < MENUBAR, (
            f"without a band, lettering still starts at row {unbanded}; "
            "the band is not what is holding it down"
        )

    def test_the_band_pushes_lettering_to_exactly_its_edge(self, rendered):
        assert first_lettered_row(rendered) == MENUBAR


class TestBadges:
    def test_a_chip_appears_in_the_top_left(self, rendered):
        chip, _ = chip_colors(*PALETTES[PALETTE])
        box = (0, MENUBAR, WIDTH // 3, HEIGHT // 2)
        assert count(rendered, chip, box) > 200

    def test_a_chip_appears_in_the_bottom_left(self, rendered):
        chip, _ = chip_colors(*PALETTES[PALETTE])
        box = (0, HEIGHT // 2, WIDTH // 3, HEIGHT - DOCK)
        assert count(rendered, chip, box) > 200

    def test_neither_chip_intrudes_on_the_menu_bar_band(self, rendered):
        chip, _ = chip_colors(*PALETTES[PALETTE])
        assert count(rendered, chip, (0, 0, WIDTH, MENUBAR)) == 0

    def test_neither_chip_hides_under_the_dock(self, rendered):
        """The Dock is drawn over the wallpaper, so anything inside its band is lost."""
        chip, _ = chip_colors(*PALETTES[PALETTE])
        assert count(rendered, chip, (0, HEIGHT - DOCK, WIDTH, HEIGHT)) == 0

    def test_the_chip_carries_a_border(self, rendered):
        """Its edge on light grounds, where a near-white fill cannot separate."""
        _, border = chip_colors(*PALETTES[PALETTE])
        box = (0, MENUBAR, WIDTH // 3, HEIGHT // 2)
        assert count(rendered, border, box) > 50

    def test_no_badge_means_no_chip_anywhere(self, unbadged):
        chip, _ = chip_colors(*PALETTES[PALETTE])
        assert count(unbadged, chip, (0, 0, WIDTH, HEIGHT)) == 0


class TestPalettesRender:
    @pytest.mark.parametrize("name", list(BRIGHT))
    def test_every_bright_palette_produces_its_own_ground(self, tmp_path, name):
        """Catches a palette whose colors never reach the page at all."""
        from PIL import Image

        target = tmp_path / f"{name}.png"
        shoot(
            wallpaper_html("Word", name, 400, menubar=10, dock=20, badge=False),
            target, 400, 400,
        )
        image = Image.open(target).convert("RGB")
        assert image.getpixel((200, 4)) == rgb(PALETTES[name][0])
