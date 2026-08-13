# space-paper

Give every macOS Space its own wallpaper — a single word repeated in a
brick-offset grid, each Space in its own color — so a glance at the desktop tells
you which Space you are on.

```
spacepaper config --init      # record which words go on which display
spacepaper apply              # render anything missing, then set every Space
```

Each wallpaper reserves a clean band behind the menu bar, and names the Space on a
chip in both left corners, clear of the menu bar and the Dock.

## Commands

| Command | What it does |
| --- | --- |
| `status` | Show every display, its Spaces, and the wallpaper each one carries |
| `config` | Show the config, or `--init` one from the current setup |
| `make WORDS...` | Render one PNG per word into `~/Pictures/Wallpapers` |
| `sheet` | Open a contact sheet of every palette in your browser |
| `apply [WORDS...]` | Set each Space's wallpaper; with no words, follow the config |
| `reset` | Put one picture — by default the macOS default — on every Space |
| `watch` | Flash the Space's name on switching; `--install` to run at login |

Words take an optional palette: `spacepaper make "Web=lagoon" "Code=clay"`.
Without one, palettes are assigned by position in the order below.

Useful options: `--set` (palette family), `--contrast` (0–1, dials the lettering
toward its background), `--no-badge`, `--width`/`--height`, `--cols`,
`--tracking`, `--font`, `--settle` (seconds to wait for the Space animation
before setting the picture), and `--dry-run` on anything that writes.

## Configuration

`spacepaper apply` with no words follows `~/.config/spacepaper/config.toml`
(`$XDG_CONFIG_HOME` is honored). If none exists, it shows what it detected and
offers to write one. `config --init` seeds the words from wallpapers this tool
already set, reading them back out of the file names, so an existing setup is
recorded rather than overwritten with invented names.

```toml
set = "bright"
badge = true

[displays."Studio Display"]
words = ["Code", "Write", "Mail", "Web"]

[displays."builtin"]
words = []
```

An **empty word list means leave that display alone** — which is how a laptop
panel stays untouched while an external monitor gets painted.

Only *intent* is stored. Resolution, menu bar and Dock thickness, and Space
counts are measured on every run and never written here, because all of them
change when you dock, undock, resize the Dock, or add a Space. A config that
cached them would go stale silently and paint the wrong screen.

### Nothing personal lives in this repo

There is no state file recording what was made or where it went. Wallpapers are
identified by their own file names (`word-palette-WxH.png`), the Space-to-picture
assignment belongs to macOS, and the Space layout is read live from the window
server. So a checkout carries no monitor models, Space names, or paths.

Everything specific to a machine is written outside the repo:

| What | Where |
| --- | --- |
| Your display/word assignments | `~/.config/spacepaper/config.toml` |
| The rendered wallpapers | `~/Pictures/Wallpapers/` |
| The palette contact sheet | a temporary directory, discarded by the OS |

If you fork this, the one thing to watch is documentation: examples naming your
own monitor or Spaces are the realistic way details leak into a public repo.
Those here are deliberately generic.

## Choosing a display

Every command that touches a screen takes `--display`, which accepts `main`,
`builtin`, `external`, an index from `status`, part of a display's name, or its
UUID. Ambiguity is an error rather than a guess.

```
$ spacepaper status
Studio Display  [external, main]
  3840x2160 native   desktop id 3
     Space 1  code-sky-3840x2160.png
   * Space 2  write-meadow-3840x2160.png
     Space 3  mail-apricot-3840x2160.png
     Space 4  web-blush-3840x2160.png

Built-in Display  [built-in]
  3024x1964 native   desktop id 1
   * Space 1  DefaultAerial.heic
```

`*` marks the Space active right now on that display — one per screen, since each
display has its own current Space. A Space reading `inherits global` has never
been given a picture of its own and follows the system-wide wallpaper.

`apply` writes only the display you name, and refuses to start when you hand it
more words than that display has Spaces. `make --display builtin` sizes the PNGs
to that screen's **native** pixels rather than its scaled point size — a 4K panel
running a "looks like 1920×1080" mode still wants a 3840×2160 picture.

## Palettes

`spacepaper sheet` opens every palette in a browser tab — something to look at
while deciding, not an artifact to keep, so it writes nothing to your wallpapers
directory. Pass `--out FILE.png` if you do want one saved.

There are two families, chosen with `--set`. Names are unique across both, so
`Web=lagoon` resolves without naming a family.

### `bright` (default)

| | ground | word | |
| --- | --- | --- | --- |
| `sky` | `#5C9BD6` | `#0F2A44` | blue |
| `meadow` | `#8CC65E` | `#274313` | green |
| `apricot` | `#F0A063` | `#572C0C` | orange |
| `blush` | `#EFA0B4` | `#5C1E2E` | pink |
| `lagoon` | `#5FC5B8` | `#0E3F39` | teal |
| `stone` | `#D6D0C4` | `#45403A` | warm neutral |
| `butter` | `#F5DE6B` | `#554614` | yellow |
| `lilac` | `#AE96E6` | `#33225A` | violet |

### `dark`

| | ground | word | |
| --- | --- | --- | --- |
| `slate` | `#333A46` | `#A8B4C6` | cool blue-gray |
| `pine` | `#2C3F3B` | `#9DBDB2` | green-teal |
| `moss` | `#373F2C` | `#B2BC96` | olive |
| `ochre` | `#453B2B` | `#C7B18A` | warm gold |
| `clay` | `#47352F` | `#C9A697` | terracotta |
| `plum` | `#40313F` | `#BFA3BE` | muted magenta |
| `indigo` | `#363448` | `#ABA6CC` | violet |
| `graphite` | `#3B3D40` | `#B2B6BB` | neutral |

### Why `bright` is the default

A wallpaper is mostly seen as slivers peeking out around open windows, and hue is
the wrong cue to lean on there — at low lightness the eye barely resolves it.
The `dark` family held lightness near-constant on purpose, and paid for it:

| | lightness range (L\*) | closest pair (CIEDE2000) |
| --- | --- | --- |
| `dark` | 3.2 | 5.2 — `slate` / `graphite` |
| `bright` | 26.2 | 20.1 — `sky` / `lilac` |

A ΔE around 5 is roughly the threshold of "just noticeable" with two patches side
by side, and nothing at all through a gap between windows. `bright` spreads
lightness across 26 points and keeps every pair past 20.

Order matters as much as color. Palettes are assigned by position, so a
four-Space setup only ever sees the first four — those are sequenced to be
maximally separated (worst pair ΔE 27) rather than listed by hue, which would
have marched blue → teal → green → yellow and handed the common case its four
closest members.

## Requirements

**Headless Chrome**, for rendering. Not an aesthetic choice: Hoefler Text carries
real small caps as `.small` glyphs, but delivers them through Apple's AAT `morx`
table rather than an OpenType `GSUB` table. CoreText reads `morx`; Chrome on
macOS uses CoreText. A FreeType-based renderer such as Pillow cannot reach those
glyphs at all without a `libraqm` build, and even then only for a font that
exposes small caps the OpenType way.

**For `apply` and `reset` only:**

- "Switch to Desktop N" enabled in System Settings → Keyboard → Keyboard
  Shortcuts → Mission Control.
- Accessibility permission for the terminal running the command. Without it
  macOS silently drops the synthetic keystroke — `osascript` still exits 0 — so
  every Space walk is verified and stops rather than painting one Space every
  word.
- **The frontmost window on the display you are targeting.** Control-N pages the
  display holding keyboard *focus*, and moving the pointer does not move focus.
  Targeting a display while your terminal sits on another one will stop the run
  rather than page the wrong screen.
- "Automatically rearrange Spaces based on most recent use" turned **off**, or
  Space numbering drifts underneath you.

## How it works

macOS 26 keeps wallpaper configuration in
`~/Library/Application Support/com.apple.wallpaper/Store/Index.plist`, as nested
binary plists. This tool never writes that file; it only reads it, to report what
each Space currently carries. Writing goes through the supported AppleScript API,
which has one useful property: `set picture` affects only the *currently active*
Space. So `apply` switches to each Space in turn and sets the picture there.

Three system sources are joined to work out the layout, because no one of them is
complete:

| Source | Supplies |
| --- | --- |
| CoreGraphics | display id, UUID, built-in flag, native pixels, screen bounds |
| AppKit `NSScreen` | display name, menu bar height, Dock thickness |
| SkyLight | which Spaces sit on which display, and which is current |
| the wallpaper store | which image, if any, each Space carries |

## Layout

Two parts of the wallpaper are placed from measurements, not guesses.

The **menu bar band** is a strip of plain ground at the top, as tall as the menu
bar on that display. Lettering behind the menu bar fights the menu titles for
legibility and the bar cannot be moved, so the wallpaper yields instead. The word
field deliberately overfills its box so the brick offset bleeds off the edges,
which means it must also be clipped — otherwise the overfill spills straight back
over the band.

The **badge** is the chip carrying the Space's name, dark on near-white. It is
drawn in *both* left corners, because neither spot is reliably visible on its own:
the top corner is prime window real estate, and the bottom one is only clear while
the Dock stays narrower than the screen — which a Dock with 30-odd items does not.
Whichever corner happens to be uncovered answers the question.

Both sit outside the menu bar and Dock bands rather than within them. The Dock and
menu bar are drawn *over* the wallpaper, so anything placed inside those bands is
simply hidden — including the gap that appears to the left of the Finder icon,
which belongs to the Dock's own panel. Badge size follows the Dock band's
thickness so it reads at the same scale as the UI beside it. `--no-badge` turns it
off.

Both come from `NSScreen`: the gap between a screen's `frame` and its
`visibleFrame` is the only thing that reports them, and both vary with display,
macOS version, and Dock settings.

**On SkyLight.** `com.apple.spaces` records the same Space layout and is a public
preference file, but its `Current Space` is a *cache* that lags reality — it will
happily report Space 2 while you are looking at Space 3. Verifying a Space switch
against that value reports failures that never happened and aborts runs that were
working, which is exactly the bug this tool shipped with. So the layout is read
from SkyLight, the private framework behind the window server that the Dock and
Mission Control themselves use.

That dependency is deliberately narrow: SkyLight is only ever **read**, never
written, and every change this tool makes still goes through public AppleScript.
If the framework is missing or changes shape, the read falls back to
`com.apple.spaces` and the tool keeps working, just with the staleness caveat
above.

`CGDirectDisplayID` is the join that matters: it is also what System Events calls
`desktop id`, so a resolved display can be written on its own with `set picture of
desktop id 3`. The obvious `tell every desktop` instead repaints *every* screen
attached to the machine, which is how a run aimed at one display silently
overwrites another.

### The wallpaper cache

macOS caches the desktop picture **by path**. Rewriting a file that a Space already
points at changes nothing on screen: the file is right, the assignment is right, and
the previous render stays up — which looks exactly like the new artwork having
failed to apply. `make` and `apply` therefore restart `WallpaperAgent` after
rendering, which forces the re-read; it relaunches on demand.

This is worth knowing before debugging a wallpaper that "didn't change". Check the
file's own pixels and the live screen separately — they can disagree.

Two smaller details keep a run honest. The pointer is warped onto the target
screen before each Control-N, because with "Displays have separate Spaces" the
hotkey pages whichever display has focus. And the Space layout is re-read after
each switch, because `osascript` exits 0 even when macOS drops the synthetic
keystroke for want of Accessibility permission — without that check, every Space
gets painted the last word and the run still claims success.

## Flashing the Space name on switching

The badge says which Space you are on; it cannot say where you *just landed*, since
at the moment of switching the eye is still moving and the badge may be behind a
window. `watch` flashes the name briefly, centred low on the display that changed.

```
spacepaper watch              # foreground, Ctrl-C to stop
spacepaper watch --install    # register with launchd: starts at login
spacepaper watch --status     # installed? loaded? running?
spacepaper watch --uninstall  # stop it and forget it
```

It hangs off `NSWorkspaceActiveSpaceDidChangeNotification`, which is public API and
fires for **every** route between Spaces — the Control-N hotkeys, a trackpad swipe,
Mission Control, following a window. Watching the keyboard instead would catch only
the hotkeys, and would need Accessibility permission to do it. The notification does
not say *which* display changed, so that is worked out by diffing a remembered
snapshot of each display's current Space against a fresh reading.

Appearance options (`--hold`, `--fade`, `--scale`, `--font`) are recorded into the
launchd plist by `--install`, so the agent flashes exactly as the command that
installed it would have. The plist names the executable by absolute path, because
launchd has none of your PATH or virtualenv — so moving or deleting the checkout
breaks the agent until you re-run `--install`. Output goes to
`~/Library/Logs/spacepaper.log`.

## Resetting

```
spacepaper reset                    # every display, every Space
spacepaper reset --display builtin  # just that screen
```

The default picture follows `/System/Library/CoreServices/DefaultDesktop.heic`,
the symlink macOS repoints on each release, so it stays correct across upgrades
where a hardcoded `Sonoma.heic` would rot. Pass `--picture` for anything else.

System Settings' "same on all Spaces" is **not** scriptable — System Events'
`desktop` class exposes no such property, and the underlying `Linked` state
belongs to WallpaperAgent. `reset` therefore does the equivalent the long way,
walking each Space and setting the same file on each, which is
indistinguishable once it lands.

## Tests

```
uv run pytest                      # everything
uv run pytest -m "not render"      # skip the Chrome renders (a tenth of a second)
```

Two tiers. Most are pure and instant; those marked `render` drive headless Chrome
and take about half a minute. They are worth their weight for a specific reason:
the layout guarantees here live in *pixels*, and the HTML has twice looked correct
while the output was wrong — once when the field's overfill spilled back over the
menu bar band, and once when a bottom-anchored badge moved between being measured
and being screenshotted.

The palette thresholds are asserted rather than merely documented, so an edit that
weakens the separation, lightness spread, or word contrast fails the suite instead
of quietly shipping.

## Known limitations

- **A Space cannot be returned to `inherits global`.** Once a Space has been given
  a picture, `reset` can point it at the default image, but only System Settings
  can restore the `Linked` state that makes it follow the global wallpaper.
- **At most nine Spaces per display**, the range the "Switch to Desktop N"
  hotkeys cover.
- **Type size is fixed by column width, not word length**, so short words sit in
  airier fields than long ones. Arguably a feature — density becomes a second
  identification cue — but the rhythm is not identical across Spaces.
