"""Give every Space its own wallpaper: a word repeated in a brick-offset grid,
each Space in its own calm hue, so the active desktop is identifiable at a glance.

    spacepaper status                              # displays, Spaces, current wallpaper
    spacepaper config --init                       # record which words go where
    spacepaper apply                               # render what is missing, then set
    spacepaper sheet                               # palette contact sheet, in a browser
    spacepaper reset                               # every Space back to the macOS default

    spacepaper make Code Write Mail Web            # render the PNGs
    spacepaper apply --display external --dry-run Code Write Mail Web
    spacepaper reset --display builtin
    spacepaper make "Web=lagoon" --contrast 0.7
    spacepaper make Code --display builtin         # sized to that screen

Rendering goes through headless Chrome so that macOS CoreText applies Hoefler
Text's AAT small caps -- real .small glyphs rather than scaled capitals. Pillow's
FreeType path cannot reach them without a libraqm build, and Hoefler Text has no
OpenType GSUB table for a non-Apple shaper to read.

With words given, `apply` paints one display, named by `--display`: `main`,
`builtin`, `external`, an index from `status`, or any part of the display's name.
With no words it follows the config, which may cover several displays. Either way
it writes `desktop id N`, so no screen it was not asked about is touched.

It switches to each Space with its Mission Control hotkey and sets the picture
there, because AppleScript writes only the *active* Space. That needs "Switch to
Desktop N" enabled in System Settings > Keyboard > Keyboard Shortcuts > Mission
Control, and Accessibility permission for the terminal running it.
"""

import shutil
import subprocess
import tempfile
import time
import webbrowser
from html import escape
from pathlib import Path
from string import Template
from typing import Annotated

import typer

from . import config as cfg
from . import displays as dsp

# Two families, each (ground, word). Words are lifted well clear of their ground;
# --contrast dials that lift back down.
#
# BRIGHT is the default, because in practice a wallpaper is seen as slivers peeking
# out around open windows, and hue is the wrong thing to lean on there: at low
# lightness the eye barely resolves it. DARK held lightness near-constant on purpose
# and paid for it -- its grounds span an L* range of 3.2 and its closest pair sits at
# CIEDE2000 5.2, which is around the threshold of "just noticeable" side by side and
# invisible in a sliver. BRIGHT instead spreads L* across 26 points and keeps every
# pair past 20, so the cue survives being seen a few pixels at a time.
#
# Order matters as much as color: palettes are assigned by position, so a four-Space
# setup only ever sees the first four. Those are sequenced to be maximally separated
# (worst pair CIEDE2000 27) rather than listed by hue, which would have marched
# blue -> teal -> green -> yellow and handed the common case its four closest members.
BRIGHT: dict[str, tuple[str, str]] = {
    "sky":     ("#5C9BD6", "#0F2A44"),
    "meadow":  ("#8CC65E", "#274313"),
    "apricot": ("#F0A063", "#572C0C"),
    "blush":   ("#EFA0B4", "#5C1E2E"),
    "lagoon":  ("#5FC5B8", "#0E3F39"),
    "stone":   ("#D6D0C4", "#45403A"),
    "butter":  ("#F5DE6B", "#554614"),
    "lilac":   ("#AE96E6", "#33225A"),
}

DARK: dict[str, tuple[str, str]] = {
    "slate":    ("#333A46", "#A8B4C6"),
    "pine":     ("#2C3F3B", "#9DBDB2"),
    "moss":     ("#373F2C", "#B2BC96"),
    "ochre":    ("#453B2B", "#C7B18A"),
    "clay":     ("#47352F", "#C9A697"),
    "plum":     ("#40313F", "#BFA3BE"),
    "indigo":   ("#363448", "#ABA6CC"),
    "graphite": ("#3B3D40", "#B2B6BB"),
}

PALETTE_SETS: dict[str, dict[str, tuple[str, str]]] = {"bright": BRIGHT, "dark": DARK}

# Names are unique across both families, so WORD=palette resolves without needing to
# know which set it came from; --set only chooses the rotation used by position.
PALETTES: dict[str, tuple[str, str]] = {**BRIGHT, **DARK}

# Virtual key codes for the number row, indexed by desktop number. Confirmed
# against com.apple.symbolichotkeys ids 118-126 ("Switch to Desktop N").
KEY_CODES = {1: 18, 2: 19, 3: 20, 4: 21, 5: 23, 6: 22, 7: 26, 8: 28, 9: 25}

# Seconds to let the Space animation finish before writing the picture.
SETTLE = 1.0

# The release default wallpaper. This symlink is the stable way to name it: it is
# repointed by each macOS release, so it stays correct across upgrades where a
# hardcoded "Sonoma.heic" would rot. On macOS 26 it lands on DefaultAerial.heic.
DEFAULT_PICTURE = Path("/System/Library/CoreServices/DefaultDesktop.heic")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

# One layout routine serves both the wallpaper and the contact sheet: it fills
# whatever box it is handed, deriving type size from that box's own width so the
# rhythm is identical at any scale.
FILL_JS = """
function fill(el, word, cols, tracking) {
  const colW  = el.clientWidth / cols;
  const fs    = colW * 0.1708;          // word occupies ~0.72 of its column
  const pitch = fs * 1.88;              // vertical rhythm, in ems of fs
  el.style.fontSize = fs + 'px';
  el.style.letterSpacing = tracking + 'em';

  // Overfill by a column and a row on every side so the brick offset bleeds off
  // the edges and reads as an infinite field rather than a centered panel.
  const nRows = Math.ceil(el.clientHeight / pitch) + 2;
  const y0    = (el.clientHeight - (nRows - 1) * pitch) / 2;

  for (let r = 0; r < nRows; r++) {
    const shift = (r % 2) ? colW / 2 : 0;
    for (let c = 0; c < cols + 2; c++) {
      const w = document.createElement('span');
      w.className = 'w';
      w.textContent = word;
      w.style.left = (-colW + c * colW + colW / 2 + shift) + 'px';
      w.style.top  = (y0 + r * pitch) + 'px';
      el.appendChild(w);
    }
  }
}
"""

WALLPAPER_HTML = Template("""<!doctype html>
<meta charset="utf-8"><title>$word</title>
<style>
  * { margin: 0; padding: 0; }
  html, body { width: 100%; height: 100%; background: $ground; overflow: hidden; }
  /* The field stops short of the menu bar rather than running under it. Lettering
     behind the menu bar fights the menu titles for legibility, and the bar cannot
     be moved -- so the wallpaper yields, leaving a clean band of ground behind it. */
  #field {
    position: absolute; top: ${menubar}px; left: 0; right: 0; bottom: 0;
    /* The field deliberately overfills its box on every side so the brick offset
       bleeds off the edges; without clipping, that overfill spills back over the
       menu bar band and undoes the point of reserving it. */
    overflow: hidden;
    font-family: "$font", serif; font-variant-caps: small-caps;
    color: $wordcolor; -webkit-font-smoothing: antialiased;
  }
  /* letter-spacing leaves a trailing gap after the final glyph; cancel it so
     translate(-50%) centers on the letterforms, not on the advance box */
  .w { position: absolute; margin-right: -${tracking}em;
       transform: translate(-50%, -50%); line-height: 1; white-space: nowrap; }
  /* The Space's name, drawn in both left corners. Two of them because neither spot
     is reliably visible on its own: the top corner is prime window real estate, and
     the bottom one is only clear while the Dock stays narrower than the screen --
     which, at 35 items, it does not. Whichever corner happens to be uncovered
     answers the question. Both sit *outside* the menu bar and Dock bands rather than
     within them, since anything inside is drawn over by the bar or the Dock. */
  .badge {
    position: absolute; left: ${badge_left}px;
    display: flex; align-items: center;
    height: ${badge_height}px; padding: 0 ${badge_pad}px;
    border-radius: ${badge_radius}px;
    background: $chip; color: $chiptext;
    /* A hairline so the chip has an edge on *any* ground. Lightness alone cannot
       carry it: on an already-light ground such as stone or butter, a near-white
       chip has nowhere left to go and dissolves into its background. */
    border: ${badge_border}px solid $chiptext;
    font-family: "$font", serif; font-variant-caps: small-caps;
    font-size: ${badge_size}px; letter-spacing: ${badge_track}em;
    line-height: 1; white-space: nowrap; -webkit-font-smoothing: antialiased;
  }
  #badge-top { top: ${badge_top}px; }
  #badge-bottom { bottom: ${badge_bottom}px; }
</style>
<div id="field"></div>
$badge_html
<script>
$fill_js
fill(document.getElementById('field'), "$word", $cols, $tracking);
</script>
""")

SHEET_HTML = Template("""<!doctype html>
<meta charset="utf-8"><title>Palettes</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0E0F11; font-family: -apple-system, sans-serif;
         display: grid; grid-template-columns: repeat(2, 1fr); gap: 28px; padding: 28px; }
  figure { position: relative; }
  .tile { position: relative; height: 300px; overflow: hidden; border-radius: 8px;
          font-family: "$font", serif; font-variant-caps: small-caps;
          -webkit-font-smoothing: antialiased; }
  .w { position: absolute; margin-right: -${tracking}em;
       transform: translate(-50%, -50%); line-height: 1; white-space: nowrap; }
  figcaption { color: #8A8F96; font-size: 19px; padding-top: 10px;
               display: flex; justify-content: space-between; }
  figcaption b { color: #D6DAE0; font-weight: 600; }
  code { color: #6E747C; font: 400 16px ui-monospace, monospace; }
</style>
<div id="sheet"></div>
<script>
$fill_js
const PALETTES = $palettes;
const sheet = document.getElementById('sheet');
sheet.replaceWith(...PALETTES.map(([name, ground, wordcolor]) => {
  const fig = document.createElement('figure');
  fig.innerHTML = `<div class="tile" style="background:$${ground};color:$${wordcolor}"></div>
    <figcaption><b>$${name}</b><code>$${ground} &nbsp;/&nbsp; $${wordcolor}</code></figcaption>`;
  document.body.appendChild(fig);
  fill(fig.querySelector('.tile'), "$word", 4, $tracking);
  return fig;
}));
</script>
""")

app = typer.Typer(add_completion=False, help=__doc__)


def find_chrome() -> str:
    """Locate a Chrome/Chromium binary, or explain what to install."""
    for path in CHROME_CANDIDATES:
        if Path(path).is_file():
            return path
    if found := shutil.which("chromium") or shutil.which("google-chrome"):
        return found
    raise typer.BadParameter(
        "no Chrome or Chromium found; install Google Chrome or pass one on PATH"
    )


def mix(ground: str, word: str, t: float) -> str:
    """Blend the word color toward its ground. t=1 is the palette as designed,
    t=0 makes the word vanish into the background entirely."""
    g = [int(ground[i:i + 2], 16) for i in (1, 3, 5)]
    w = [int(word[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a + (b - a) * t):02X}" for a, b in zip(g, w))


def rotation(name: str) -> list[str]:
    """Palette names in positional order for one family."""
    if name not in PALETTE_SETS:
        raise typer.BadParameter(f"unknown set {name!r} (have: {', '.join(PALETTE_SETS)})")
    return list(PALETTE_SETS[name])


def luminance(color: str) -> float:
    """WCAG relative luminance, used only to tell a palette's light end from its dark."""
    channels = []
    for i in (1, 3, 5):
        c = int(color[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def chip_colors(ground: str, word: str) -> tuple[str, str]:
    """A light chip and dark text for the badge, whichever way the palette runs.

    The bright family puts the dark tone in the word and the light one in the ground;
    the dark family is the other way about. Sorting by luminance rather than by role
    keeps the badge dark-on-light in both, instead of inverting with the set.
    """
    light, dark = (ground, word) if luminance(ground) > luminance(word) else (word, ground)
    # Pushed most of the way to white rather than merely lightened: at half strength
    # the chip reads as another shade of the ground instead of a label sitting on it.
    return mix(light, "#FFFFFF", 0.82), mix(dark, "#000000", 0.25)


def wallpaper_html(
    word: str,
    palette: str,
    height: int,
    *,
    contrast: float = 1.0,
    menubar: int = 0,
    dock: int = 0,
    badge: bool = True,
    cols: int = 8,
    tracking: float = 0.18,
    font: str = "Hoefler Text",
) -> str:
    """Build the page for one wallpaper: word field, menu bar band, and Space badge."""
    ground, full = PALETTES[palette]
    chip, chiptext = chip_colors(ground, full)

    # The badge is sized against the Dock band so it reads at the same scale as the
    # UI beside it; displays without a Dock get a proportional band instead. It is
    # then placed *clear* of both bands rather than inside either, because the Dock
    # and menu bar are drawn over the wallpaper, not under it.
    band = dock or max(96, round(height * 0.07))
    badge_height = round(band * 0.72)
    gap = round(badge_height * 0.40)

    chip_html = ""
    if badge:
        label = escape(word)
        chip_html = (
            f'<div class="badge" id="badge-top">{label}</div>\n'
            f'<div class="badge" id="badge-bottom">{label}</div>'
        )

    return WALLPAPER_HTML.substitute(
        word=word,
        ground=ground,
        wordcolor=mix(ground, full, contrast),
        font=font,
        cols=cols,
        tracking=tracking,
        fill_js=FILL_JS,
        menubar=menubar,
        chip=chip,
        chiptext=chiptext,
        badge_html=chip_html,
        badge_height=badge_height,
        badge_size=round(band * 0.40),
        badge_pad=round(badge_height * 0.42),
        badge_radius=round(badge_height / 2),
        badge_border=max(2, round(badge_height * 0.035)),
        badge_top=menubar + gap,
        badge_bottom=dock + gap,
        badge_left=round(badge_height * 0.55),
        badge_track=0.10,
    )


def parse_word(spec: str, position: int, names: list[str]) -> tuple[str, str]:
    """Parse `Word` (palette by position) or `Word=palette` (explicit palette)."""
    if "=" in spec:
        word, _, palette = spec.rpartition("=")
        word, palette = word.strip(), palette.strip().lower()
        if palette not in PALETTES:
            raise typer.BadParameter(
                f"{spec!r}: unknown palette {palette!r} (have: {', '.join(PALETTES)})"
            )
    else:
        word, palette = spec.strip(), names[(position - 1) % len(names)]

    if not word:
        raise typer.BadParameter(f"{spec!r}: word is empty")
    return word, palette


def shoot(html: str, target: Path, width: int, height: int) -> None:
    """Render one HTML string to a PNG at exactly width x height."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
        tmp.write(html)
        page = Path(tmp.name)
    try:
        result = subprocess.run(
            [find_chrome(), "--headless", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={width},{height}",
             f"--screenshot={target}", page.as_uri()],
            capture_output=True, text=True,
        )
    finally:
        page.unlink(missing_ok=True)

    if not target.exists():
        typer.echo(f"render failed: {result.stderr.strip()[:400]}", err=True)
        raise typer.Exit(1)


@app.command()
def make(
    words: Annotated[
        list[str],
        typer.Argument(help="Words in Space order, or WORD=PALETTE to pick the hue."),
    ] = None,
    out: Annotated[
        Path, typer.Option(help="Directory to write the PNGs into.")
    ] = Path.home() / "Pictures/Wallpapers",
    display: Annotated[
        str, typer.Option(help="Size and lay out for this display.")
    ] = "main",
    palette_set: Annotated[
        str, typer.Option("--set", help=f"Palette family: {', '.join(PALETTE_SETS)}.")
    ] = "bright",
    width: Annotated[int, typer.Option(help="Pixel width; 0 uses the display's native width.")] = 0,
    height: Annotated[int, typer.Option(help="Pixel height; 0 uses the display's native height.")] = 0,
    contrast: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Word lift; 1.0 is the palette as designed.")
    ] = 1.0,
    badge: Annotated[
        bool, typer.Option(help="Show the Space name on a chip beside the Dock.")
    ] = True,
    cols: Annotated[int, typer.Option(min=1, help="Words across.")] = 8,
    tracking: Annotated[float, typer.Option(help="Letter-spacing, in ems.")] = 0.18,
    font: Annotated[str, typer.Option(help="Font family (needs real small caps).")] = "Hoefler Text",
) -> None:
    """Write one wallpaper PNG per word."""
    words = words or ["Desktop"]
    pairs = [parse_word(spec, i, rotation(palette_set)) for i, spec in enumerate(words, start=1)]

    # A display's native pixels, not its scaled point size: a 4K panel running a
    # "looks like 1920x1080" mode still wants a 3840x2160 picture. The menu bar and
    # Dock come from the same screen, so the band and badge land where they belong.
    screen = pick(display)
    width = width or screen.width
    height = height or screen.height
    typer.echo(
        f"{screen.name}: {width}x{height}, menu bar {screen.menubar}px, Dock {screen.dock}px\n"
    )

    if len({w for w, _ in pairs}) != len(pairs):
        raise typer.BadParameter("words must be unique (they name the output files)")

    for word, palette in pairs:
        ground, full = PALETTES[palette]
        target = out / f"{word.lower()}-{palette}-{width}x{height}.png"
        shoot(
            wallpaper_html(
                word, palette, height, contrast=contrast, menubar=screen.menubar,
                dock=screen.dock, badge=badge, cols=cols, tracking=tracking, font=font,
            ),
            target, width, height,
        )
        typer.echo(f"  {word:<12} {palette:<9} {ground} on {mix(ground, full, contrast)}  ->  {target.name}")

    # Regenerating a file some Space already points at would otherwise leave the old
    # picture on screen, since the desktop caches by path.
    refresh_wallpaper()
    typer.echo(f"\nWrote {len(pairs)} wallpaper(s) to {out}")


@app.command()
def sheet(
    palette_set: Annotated[
        str, typer.Option("--set", help=f"Family to show: {', '.join(PALETTE_SETS)}, or all.")
    ] = "all",
    word: Annotated[str, typer.Option(help="Word to show in each swatch.")] = "Desktop",
    tracking: Annotated[float, typer.Option(help="Letter-spacing, in ems.")] = 0.18,
    font: Annotated[str, typer.Option(help="Font family.")] = "Hoefler Text",
    out: Annotated[
        Path | None, typer.Option(help="Write a PNG here instead of opening a browser.")
    ] = None,
) -> None:
    """Show a contact sheet of every palette, for choosing between them.

    Opens in the browser rather than writing a file: the sheet is something to look
    at while deciding, not an artifact to keep, and it has no business sitting in a
    wallpapers directory next to the real output. It is already HTML, so the
    headless-Chrome round trip that the wallpapers need buys nothing here.
    """
    if palette_set != "all" and palette_set not in PALETTE_SETS:
        raise typer.BadParameter(
            f"unknown set {palette_set!r} (have: {', '.join(PALETTE_SETS)}, all)"
        )
    families = PALETTE_SETS if palette_set == "all" else {palette_set: PALETTE_SETS[palette_set]}
    rows = [
        [f"{name}  ({family})", g, w]
        for family, palettes in families.items()
        for name, (g, w) in palettes.items()
    ]
    html = SHEET_HTML.substitute(
        word=word, font=font, tracking=tracking, fill_js=FILL_JS,
        palettes=repr(rows).replace("'", '"'),
    )

    if out:
        height = 28 + (len(rows) + 1) // 2 * (300 + 44 + 28)
        shoot(html, out, 1500, height)
        typer.echo(f"Wrote {out}")
        return

    # Kept out of the wallpapers directory and off the caller's hands entirely; the
    # directory survives this process because the browser reads it after we exit.
    page = Path(tempfile.mkdtemp(prefix="spacepaper-")) / "palettes.html"
    page.write_text(html)
    webbrowser.open(page.as_uri())
    typer.echo(f"Opened {len(rows)} palettes in your browser.")


def osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


def as_string(value: object) -> str:
    """Quote a value as an AppleScript string literal. AppleScript accepts only
    double quotes, so Python's repr() is not interchangeable here."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def pick(selector: str) -> dsp.Display:
    """Resolve a --display selector, reporting failure as a usage error."""
    try:
        return dsp.resolve(selector)
    except dsp.DisplayError as exc:
        raise typer.BadParameter(str(exc)) from exc


def goto(screen: dsp.Display, space: int, settle: float = SETTLE) -> None:
    """Switch one display to one of its Spaces, or explain why it did not move.

    The pointer is parked on the target screen first: with "Displays have separate
    Spaces" on, Control-N pages whichever display has focus, so without this a run
    aimed at one screen quietly pages another.

    osascript exits 0 even when macOS drops the synthetic key for want of
    Accessibility permission, so the Space layout is re-read rather than trusted.
    Skipping that check is how every Space ends up painted the last word while the
    run still claims success.
    """
    # A single-Space display is already where it needs to be, and paging it would
    # only disturb whichever display actually holds focus.
    if len(screen.spaces) < 2:
        return

    dsp.focus(screen)
    osascript(
        f'tell application "System Events" to key code {KEY_CODES[space]} using control down'
    )
    time.sleep(settle)

    landed = dsp.resolve(screen.uuid).current_space
    if landed and landed != space:
        typer.echo(
            f"\nStopped: asked for Space {space} but stayed on Space {landed} "
            f"of {len(screen.spaces)} on {screen.name}.\n"
            "Two things cause this. Either the terminal lacks Accessibility "
            "permission, so macOS dropped the keystroke:\n"
            "  System Settings > Privacy & Security > Accessibility\n"
            f"or the frontmost window is not on {screen.name} -- Control-N pages "
            "the display holding keyboard focus, which the pointer alone does not "
            "move. Click a window on that display, then re-run.\n"
            "(osascript reports success either way, so this is checked rather "
            "than assumed.)",
            err=True,
        )
        raise typer.Exit(1)


def set_picture(screen: dsp.Display, picture: Path) -> str:
    """Put a picture on the active Space of one display. Returns "ok" or the error.

    `desktop id N` is the whole point: the obvious `every desktop` repaints every
    screen attached to the machine, including ones the caller never named.
    """
    result = osascript(
        f'tell application "System Events" to set picture of desktop id {screen.cg_id} '
        f"to {as_string(picture)}"
    )
    return "ok" if result.returncode == 0 else result.stderr.strip()[:60]


def refresh_wallpaper() -> None:
    """Make macOS re-read wallpaper files whose contents changed.

    The desktop picture is cached by *path*. Rewriting a file that a Space already
    points at therefore changes nothing on screen: the assignment is correct, the
    file is correct, and the old render stays up -- which looks exactly like the new
    artwork having failed to apply. Restarting the agent forces the re-read. It is
    launched on demand, so this is a nudge rather than a shutdown.
    """
    subprocess.run(["killall", "WallpaperAgent"], capture_output=True)


def go_home(screen: dsp.Display, home: int, settle: float = SETTLE) -> None:
    """Return a display to a chosen Space once the walk is done; 0 stays put.

    Waits for the switch to land, so the summary printed afterward reports the Space
    the user is actually looking at rather than the one they just left.
    """
    if home and home in KEY_CODES and len(screen.spaces) > 1:
        dsp.focus(screen)
        osascript(
            f'tell application "System Events" to key code {KEY_CODES[home]} using control down'
        )
        time.sleep(settle)


def show(display: dsp.Display, verbose: bool = False) -> None:
    """Print one display and the wallpaper on each of its Spaces."""
    typer.echo(f"{display.name}  [{display.kind}{', main' if display.main else ''}]")
    typer.echo(f"  {display.width}x{display.height} native   desktop id {display.cg_id}")
    if verbose:
        typer.echo(f"  uuid {display.uuid}")

    if not display.spaces:
        typer.echo("  (no Spaces reported for this display)")
        return
    for space in display.spaces:
        marker = "*" if space.current else " "
        typer.echo(f"   {marker} Space {space.number}  {space.wallpaper}")
        if verbose:
            typer.echo(f"       uuid {space.uuid}")


@app.command()
def status(
    display: Annotated[
        str, typer.Option(help="Limit to one display; omit to show them all.")
    ] = "",
    verbose: Annotated[bool, typer.Option(help="Also show display and Space UUIDs.")] = False,
) -> None:
    """Show every display, its Spaces, and the wallpaper each one carries.

    A Space marked `inherits global` has never been given a picture of its own, so
    it follows the system-wide wallpaper. `*` marks the Space active right now on
    that display -- one per screen, since each display has its own current Space.
    """
    found = [pick(display)] if display else dsp.displays()
    if not found:
        typer.echo("No active displays found.", err=True)
        raise typer.Exit(1)

    for i, screen in enumerate(found):
        if i:
            typer.echo()
        show(screen, verbose)

    typer.echo(
        f"\n{len(found)} display(s), "
        f"{sum(len(s.spaces) for s in found)} Space(s). "
        "Name one with --display: main, builtin, external, a name, or an index."
    )


@app.command()
def apply(
    words: Annotated[
        list[str],
        typer.Argument(help="Words in Space order, or WORD=PALETTE. Space N gets word N."),
    ] = None,
    display: Annotated[
        str,
        typer.Option(help="Which screen to paint: main, builtin, external, a name, or an index."),
    ] = "",
    palette_set: Annotated[
        str, typer.Option("--set", help=f"Palette family: {', '.join(PALETTE_SETS)}.")
    ] = "bright",
    badge: Annotated[
        bool, typer.Option(help="Show the Space name on a chip beside the Dock.")
    ] = True,
    out: Annotated[
        Path, typer.Option(help="Directory holding (or to receive) the PNGs.")
    ] = Path.home() / "Pictures/Wallpapers",
    width: Annotated[
        int, typer.Option(help="Pixel width; 0 uses the display's native width.")
    ] = 0,
    height: Annotated[
        int, typer.Option(help="Pixel height; 0 uses the display's native height.")
    ] = 0,
    contrast: Annotated[float, typer.Option(min=0.0, max=1.0, help="Word lift.")] = 1.0,
    settle: Annotated[
        float, typer.Option(help="Seconds to wait for the Space animation before setting.")
    ] = 1.0,
    generate: Annotated[
        bool, typer.Option(help="Render any missing wallpaper before applying it.")
    ] = True,
    home: Annotated[
        int, typer.Option(help="Space to return to when finished; 0 to stay put.")
    ] = 1,
    dry_run: Annotated[
        bool, typer.Option(help="Show the plan and change nothing.")
    ] = False,
) -> None:
    """Set each Space's wallpaper, one Space at a time.

    With words given, one display is painted -- whichever --display names, or the
    main one. With no words the config decides, which may cover several displays;
    any it lists with an empty word list is passed over untouched.

    Only displays actually chosen are written: the picture goes to `desktop id N`,
    never to `every desktop`, so other screens keep what they have. Switching to each
    Space with its Mission Control hotkey is still necessary, because AppleScript
    writes only the *active* Space.

    Requires "Switch to Desktop N" enabled in System Settings > Keyboard >
    Keyboard Shortcuts > Mission Control, and Accessibility permission for the
    terminal running this. Turn OFF "Automatically rearrange Spaces based on most
    recent use", or Space numbering drifts under you.
    """
    for screen, plan_words, plan_set, plan_badge in build_plan(words, display, palette_set, badge):
        paint(
            screen, plan_words, plan_set, plan_badge, out=out, width=width, height=height,
            contrast=contrast, settle=settle, generate=generate, home=home, dry_run=dry_run,
        )


def paint(
    screen: dsp.Display,
    words: list[str],
    palette_set: str,
    badge: bool,
    *,
    out: Path,
    width: int,
    height: int,
    contrast: float,
    settle: float,
    generate: bool,
    home: int,
    dry_run: bool,
) -> None:
    """Walk one display's Spaces, setting each one's wallpaper."""
    pairs = [parse_word(spec, i, rotation(palette_set)) for i, spec in enumerate(words, start=1)]
    width = width or screen.width
    height = height or screen.height

    if len(pairs) > len(KEY_CODES):
        raise typer.BadParameter(f"at most {len(KEY_CODES)} Spaces are addressable")

    # Refuse rather than guess: with more words than Spaces the extra words would
    # silently overwrite whatever Space the hotkey failed to leave.
    if not screen.spaces:
        raise typer.BadParameter(
            f"no Spaces found for {screen.name}; run `spacepaper status` to see the layout"
        )
    if len(pairs) > len(screen.spaces):
        raise typer.BadParameter(
            f"{len(pairs)} words but {screen.name} has {len(screen.spaces)} Space(s). "
            "Add Spaces in Mission Control, or pass fewer words."
        )

    rendered = False
    typer.echo(f"{screen.label} -- {len(pairs)} of {len(screen.spaces)} Space(s), {width}x{height}")
    if len(pairs) < len(screen.spaces):
        typer.echo(f"  Spaces {len(pairs) + 1}-{len(screen.spaces)} left untouched.")

    for space, (word, palette) in enumerate(pairs, start=1):
        ground, full = PALETTES[palette]
        target = out / f"{word.lower()}-{palette}-{width}x{height}.png"

        if dry_run:
            state = "have" if target.is_file() else ("render" if generate else "MISSING")
            typer.echo(f"  Space {space}  {word:<12} {palette:<9} {state:<7} {target.name}")
            continue

        if not target.is_file():
            if not generate:
                typer.echo(f"  Space {space}: missing {target.name}; skipped", err=True)
                continue
            shoot(
                wallpaper_html(
                    word, palette, height, contrast=contrast, menubar=screen.menubar,
                    dock=screen.dock, badge=badge,
                ),
                target, width, height,
            )
            rendered = True

        goto(screen, space, settle)
        state = set_picture(screen, target)
        typer.echo(f"  Space {space}  {word:<12} {palette:<9} {state}")

    if dry_run:
        typer.echo("\nDry run: nothing was changed.")
        return

    if rendered:
        refresh_wallpaper()
    go_home(screen, home, settle)
    typer.echo()
    show(dsp.resolve(screen.uuid))
    landed = sum(1 for s in dsp.resolve(screen.uuid).spaces if s.picture)
    if landed < len(pairs):
        typer.echo(
            f"\nOnly {landed} of {len(pairs)} Space(s) carry an image. Usual causes: the "
            '"Switch to Desktop N" hotkeys are not enabled, or the terminal lacks '
            "Accessibility permission.",
            err=True,
        )


def recover_word(picture: Path | None) -> str | None:
    """Recover the word from a wallpaper this tool wrote, by its file name.

    Files are named `word-palette-WxH.png`, so a Space already carrying one tells us
    what it was called. That makes `config --init` reflect a setup that is already in
    place instead of inventing names the user then has to correct.
    """
    if picture is None:
        return None
    parts = picture.stem.split("-")
    if len(parts) < 3 or parts[-2] not in PALETTES:
        return None
    return "-".join(parts[:-2]).capitalize() or None


def proposed_config() -> cfg.Config:
    """Build a config from what is on screen right now.

    Words come from wallpapers this tool already set, where it can read them, and
    from placeholders otherwise. The built-in display is seeded empty: a laptop panel
    is the one people most often want left alone, and an empty list means exactly
    that.
    """
    seeds = ["Main", "Work", "Write", "Read", "Play", "Side", "Spare", "Extra", "Last"]
    screens = []
    for screen in dsp.displays():
        words = [] if screen.builtin else [
            recover_word(space.picture) or seeds[i % len(seeds)]
            for i, space in enumerate(screen.spaces)
        ]
        screens.append(cfg.Screen(match=screen.name, words=words))
    return cfg.Config(screens=screens)


def ensure_config() -> cfg.Config | None:
    """Load the config, offering to write one when it is missing.

    Returns None if there is no config and the user declines to create one, leaving
    the caller to fall back to its command-line arguments.
    """
    if cfg.exists():
        return cfg.load()

    typer.echo(f"No config at {cfg.path()}.")
    proposal = proposed_config()
    typer.echo("\nDetected right now:")
    for screen in proposal.screens:
        words = ", ".join(screen.words) if screen.words else "(left alone)"
        typer.echo(f"  {screen.match:<34} {words}")

    if not typer.confirm("\nWrite this as your starting config?", default=True):
        return None
    target = cfg.save(proposal)
    typer.echo(f"Wrote {target}. Edit the words to taste, then re-run.")
    return cfg.load()


def build_plan(
    words: list[str] | None, display: str, palette_set: str, badge: bool
) -> list[tuple[dsp.Display, list[str], str, bool]]:
    """Work out which displays to paint with what.

    Words on the command line win outright and target one display. With no words the
    config decides, which is what lets `spacepaper apply` on its own do the right
    thing across several screens -- and lets a display with an empty word list be
    passed over rather than painted with something arbitrary.
    """
    if words:
        return [(pick(display or "main"), words, palette_set, badge)]

    loaded = ensure_config()
    if loaded is None:
        raise typer.BadParameter(
            "no words given and no config. Pass words, or run `spacepaper config --init`."
        )

    wanted = pick(display) if display else None
    plan = []
    for screen in loaded.screens:
        if not screen.words:
            continue
        try:
            resolved = dsp.resolve(screen.match)
        except dsp.DisplayError:
            typer.echo(f"  {screen.match}: not connected; skipped", err=True)
            continue
        if wanted and resolved.cg_id != wanted.cg_id:
            continue
        plan.append((
            resolved,
            screen.words,
            screen.palette_set or loaded.palette_set,
            loaded.badge if screen.badge is None else screen.badge,
        ))

    if not plan:
        where = f" matching {display!r}" if display else ""
        raise typer.BadParameter(
            f"config lists no display{where} with words to apply. "
            f"Edit {cfg.path()} or pass words directly."
        )
    return plan


@app.command()
def config(
    init: Annotated[bool, typer.Option(help="Write a config from the current setup.")] = False,
    force: Annotated[bool, typer.Option(help="Overwrite an existing config.")] = False,
) -> None:
    """Show the config file, or create one from what is on screen now.

    The file records only intent -- which words belong on which display. Everything
    macOS can report (resolution, menu bar and Dock size, Space counts) is measured
    on every run instead, so docking a laptop or adding a Space needs no edit here.
    """
    target = cfg.path()

    if init:
        if target.is_file() and not force:
            raise typer.BadParameter(f"{target} exists; pass --force to overwrite")
        typer.echo(f"Wrote {cfg.save(proposed_config())}")
        return

    if not target.is_file():
        typer.echo(f"No config at {target}.")
        typer.echo("Create one with:  spacepaper config --init")
        raise typer.Exit(1)

    try:
        loaded = cfg.load()
    except cfg.ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"{target}\n")
    typer.echo(f"  default set   {loaded.palette_set}")
    typer.echo(f"  default badge {loaded.badge}")
    for screen in loaded.screens:
        words = ", ".join(screen.words) if screen.words else "(left alone)"
        typer.echo(f"\n  {screen.match}")
        typer.echo(f"    words {words}")
        if screen.palette_set:
            typer.echo(f"    set   {screen.palette_set}")
        if screen.badge is not None:
            typer.echo(f"    badge {screen.badge}")


@app.command()
def reset(
    display: Annotated[
        str,
        typer.Option(help="Which screen to reset; omit to reset every display."),
    ] = "",
    picture: Annotated[
        Path,
        typer.Option(help="Picture to put everywhere; defaults to the macOS release default."),
    ] = DEFAULT_PICTURE,
    settle: Annotated[
        float, typer.Option(help="Seconds to wait for the Space animation before setting.")
    ] = SETTLE,
    home: Annotated[
        int, typer.Option(help="Space to return to when finished; 0 to stay put.")
    ] = 1,
    dry_run: Annotated[bool, typer.Option(help="Show the plan and change nothing.")] = False,
) -> None:
    """Put one picture on every Space of every display -- by default, the macOS default.

    System Settings' "same on all Spaces" is not scriptable: System Events' desktop
    class exposes no such property, and the underlying `Linked` state belongs to
    WallpaperAgent. So this does the equivalent the long way, walking each Space and
    setting the same file on each, which is indistinguishable once it lands.

    The default picture follows /System/Library/CoreServices/DefaultDesktop.heic,
    the symlink macOS repoints on each release, so this keeps working after upgrades.
    """
    if not picture.is_file():
        raise typer.BadParameter(f"{picture} does not exist")
    picture = picture.resolve()

    screens = [pick(display)] if display else dsp.displays()
    if not screens:
        typer.echo("No active displays found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Resetting to {picture}\n")
    for i, screen in enumerate(screens):
        if i:
            typer.echo()
        typer.echo(f"{screen.label} -- {len(screen.spaces)} Space(s)")
        if not screen.spaces:
            typer.echo("  (no Spaces reported; skipped)")
            continue

        for space in screen.spaces:
            if space.number not in KEY_CODES:
                typer.echo(f"  Space {space.number}: beyond the addressable range; skipped", err=True)
                continue
            if dry_run:
                typer.echo(f"  Space {space.number}  would set {picture.name}")
                continue
            goto(screen, space.number, settle)
            typer.echo(f"  Space {space.number}  {set_picture(screen, picture)}")

        if not dry_run:
            go_home(screen, home, settle)

    if dry_run:
        typer.echo("\nDry run: nothing was changed.")
        return

    typer.echo()
    for i, screen in enumerate(dsp.displays()):
        if i:
            typer.echo()
        show(screen)


if __name__ == "__main__":
    app()
