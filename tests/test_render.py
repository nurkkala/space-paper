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
WORD, PALETTE = "Beacon", "meadow"


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    from PIL import Image

    target = tmp_path_factory.mktemp("render") / "wallpaper.png"
    shoot(
        wallpaper_html(WORD, PALETTE, WIDTH, HEIGHT, menubar=MENUBAR, dock=DOCK, badge=True),
        target, WIDTH, HEIGHT,
    )
    return Image.open(target).convert("RGB")


@pytest.fixture(scope="module")
def unbadged(tmp_path_factory):
    from PIL import Image

    target = tmp_path_factory.mktemp("render") / "plain.png"
    shoot(
        wallpaper_html(WORD, PALETTE, WIDTH, HEIGHT, menubar=MENUBAR, dock=DOCK, badge=False),
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
            wallpaper_html(WORD, PALETTE, WIDTH, HEIGHT, menubar=0, dock=DOCK, badge=False),
            target, WIDTH, HEIGHT,
        )
        unbanded = first_lettered_row(Image.open(target).convert("RGB"))
        assert unbanded < MENUBAR, (
            f"without a band, lettering still starts at row {unbanded}; "
            "the band is not what is holding it down"
        )

    def test_lettering_starts_at_the_band_and_not_far_below(self, rendered):
        """A bound rather than an exact row.

        Where the first glyph lands inside the band's edge depends on the type
        metrics and how the rows happen to phase against the field height, so
        pinning an exact value would assert an accident. What matters is that
        nothing is above the band and the field is not pushed needlessly far down.
        """
        row = first_lettered_row(rendered)
        pitch = (WIDTH / 8) * 0.1708 * 1.88  # one row of the brick rhythm
        assert MENUBAR <= row <= MENUBAR + pitch, f"lettering starts at row {row}"


class TestDockBand:
    def test_the_dock_band_is_solid_ground(self, rendered):
        """The Dock is drawn over the wallpaper, so lettering behind it only
        fights the icons for legibility. Reserved exactly as the menu bar is."""
        ground = rgb(PALETTES[PALETTE][0])
        for y in range(HEIGHT - DOCK, HEIGHT):
            for x in range(0, WIDTH, 3):
                assert rendered.getpixel((x, y)) == ground, f"lettering at y={y}"

    def test_lettering_reaches_up_to_the_dock_band(self, rendered):
        ground = rgb(PALETTES[PALETTE][0])
        strip = [
            rendered.getpixel((x, y))
            for y in range(HEIGHT - DOCK - 60, HEIGHT - DOCK)
            for x in range(0, WIDTH, 3)
        ]
        assert any(p != ground for p in strip)


class TestBadgeClearance:
    """Words colliding with a badge are removed, not covered over.

    Masking hides the middle of a glyph and leaves its extremities poking past the
    edge -- stray partial letters floating beside the chip. Deleting the whole word
    leaves nothing to peek, which is what these assert.
    """

    def chip_box(self, image, chip):
        want = rgb(chip)
        xs, ys = [], []
        for y in range(0, image.size[1], 2):
            for x in range(0, image.size[0] // 2, 2):
                if image.getpixel((x, y)) == want:
                    xs.append(x)
                    ys.append(y)
        assert xs, "no chip found"
        return min(xs), min(ys), max(xs), max(ys)

    @pytest.mark.parametrize("half", ["top", "bottom"])
    def test_no_word_pixels_survive_near_a_badge(self, rendered, half):
        chip, _ = chip_colors(*PALETTES[PALETTE])
        word_color = rgb(PALETTES[PALETTE][1])
        top = MENUBAR if half == "top" else HEIGHT // 2
        bottom = HEIGHT // 2 if half == "top" else HEIGHT - DOCK
        region = rendered.crop((0, top, WIDTH // 3, bottom))

        left, up, right, down = self.chip_box(region, chip)

        # The outline is antialiased against the chip, and somewhere along that ramp
        # a pixel lands on exactly the word color. Those sit hard against the pill,
        # so the ring being examined starts outside them: a surviving letter would
        # be a solid cluster further out, not a lone pixel on the border.
        skin, margin = 5, 16
        width, height = region.size
        strays = [
            (x, y)
            for y in range(max(0, up - margin), min(height, down + margin))
            for x in range(max(0, left - margin), min(width, right + margin))
            if not (left - skin <= x <= right + skin and up - skin <= y <= down + skin)
            and region.getpixel((x, y)) == word_color
        ]
        assert not strays, (
            f"{len(strays)} word pixels beside the badge, e.g. {strays[:4]} -- "
            "a word that should have been suppressed is peeking out"
        )


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
            wallpaper_html("Word", name, 400, 400, menubar=10, dock=20, badge=False),
            target, 400, 400,
        )
        image = Image.open(target).convert("RGB")
        assert image.getpixel((200, 4)) == rgb(PALETTES[name][0])
