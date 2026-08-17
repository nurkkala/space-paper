# space-paper

Give every macOS Space its own wallpaper — a single word repeated in a
brick-offset grid, each Space in its own color — so a glance at the desktop tells
you where you are. And when you switch Spaces, flash the name of the one you have
just reached.

```
spacepaper config --init      # record which words go on which display
spacepaper apply              # render anything missing, then set every Space
spacepaper watch --install    # flash the Space's name whenever you switch
```

Each wallpaper reserves clean bands behind the menu bar and the Dock, and shows
the Space's name on a chip (the **badge**) in both left corners, outside those
bands.

The flash is that same chip, larger and centered low on the display that changed;
it stays for about a second, then fades. Where the badge identifies the Space in
front of you, the flash says where you have just arrived, at the moment when the
eye is still moving and the badge may be behind a window. Every route between Spaces
triggers it: a hotkey, a swipe, Mission Control, a jump to a window on another
Space. Noticing them takes no Accessibility permission. `watch --install` keeps it
running from login onward. The section
[Flashing the Space name on switching](#flashing-the-space-name-on-switching) has
the details.

## Commands

| Command | What it does |
| --- | --- |
| `status` | Show every display, its Spaces, and the wallpaper each one carries |
| `config` | Show the config, or write one from the current setup with `--init` |
| `make WORDS...` | Render one PNG per word into `~/Pictures/Wallpapers` |
| `sheet` | Open a contact sheet of every palette in your browser |
| `apply [WORDS...]` | Set each Space's wallpaper; with no words, follow the config |
| `reset` | Put one picture (by default the macOS default) on every Space |
| `watch` | Flash the Space's name on switching; `--install` to run at login |

Words take an optional palette: `spacepaper make "Web=lagoon" "Code=clay"`.
Without one, a word takes the palette at its position in the
[palette tables](#palettes).

Useful options: `--set` (palette family), `--contrast` (0–1, dials the lettering
toward its background), `--no-badge`, `--width`/`--height`, `--cols`,
`--tracking`, `--font`, `--settle` (seconds to wait for the Space animation
before setting the picture), and `--dry-run` on anything that writes.

## Configuration

`spacepaper apply` with no words follows `~/.config/spacepaper/config.toml`
(`$XDG_CONFIG_HOME` is honored). If none exists, it shows what it detected and
offers to write one. `config --init` seeds the words from wallpapers this tool
already set (it reads them back out of the file names). It records an existing
setup instead of inventing one.

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

Only *intent* is stored. The tool measures resolution, menu bar and Dock
thickness, and Space counts on every run and never writes them here, because all
of them change when you dock, undock, resize the Dock, or add a Space. A config
that cached them would go stale silently and paint the wrong screen.

### Machine-local state

No state file records what was made or where it went. A wallpaper's file name
(`word-palette-WxH.png`) identifies it, the Space-to-picture assignment belongs to
macOS, and the Space layout comes live from the window server. So a checkout
carries no monitor models, Space names, or paths.

Everything specific to a machine lives outside the repo:

| What | Where |
| --- | --- |
| Your display/word assignments | `~/.config/spacepaper/config.toml` |
| The rendered wallpapers | `~/Pictures/Wallpapers/` |
| The palette contact sheet | a temporary directory, discarded by the OS |
| The `watch` login agent | `~/Library/LaunchAgents/com.spacepaper.watch.plist` |
| The watcher's log | `~/Library/Logs/spacepaper.log` |

If you fork this repo, the one thing to watch is documentation. An example that
mentions your own monitor or Spaces is how details leak into a public repo. The
examples here are deliberately generic.

## Choosing a display

Every command that touches a screen takes `--display`, which accepts `main`,
`builtin`, `external`, a display's position in the `status` listing (1-based, main
display first), part of its name, or its UUID. Ambiguity is an error rather than a
guess.

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

`*` marks the Space active right now on that display (one per screen, since each
display has its own current Space). A Space reading `inherits global` has never
had a picture of its own and follows the system-wide wallpaper.

With words, `apply` writes one display (the one `--display` selects, or the main
one) and refuses to start when you hand it more words than that display has
Spaces. `make --display builtin` sizes the PNGs to that screen's **native** pixels
rather than its scaled point size. A 4K panel running a "looks like 1920×1080"
mode still wants a 3840×2160 picture.

## Palettes

`spacepaper sheet` opens every palette in a browser tab. It is something to
consult while deciding, not an artifact to keep, so it writes nothing to your
wallpapers directory. Pass `--out FILE.png` if you do want one saved.

`--set` chooses between two families. Names are unique across both, so
`Web=lagoon` needs no family prefix.

### `bright` (default)

| palette | ground | word | hue |
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

| palette | ground | word | hue |
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

A wallpaper is mostly seen as slivers peeking out around open windows. Hue is the
wrong cue for slivers, because at low lightness the eye barely resolves it. The
`dark` family held lightness near-constant on purpose and paid for it:

| family | lightness range (L\*) | closest pair (CIEDE2000) |
| --- | --- | --- |
| `dark` | 3.2 | 5.2 — `slate` / `graphite` |
| `bright` | 26.2 | 20.1 — `sky` / `lilac` |

A ΔE around 5 is roughly the threshold of "just noticeable" with two patches side
by side, and imperceptible through a gap between windows. `bright` spreads
lightness across 26 points and keeps every pair past 20.

Order matters as much as color. Position assigns the palette, so a four-Space
setup only ever sees the first four. Those four are ordered for maximum separation
(worst pair ΔE 27) rather than by hue, which would have marched blue, teal, green,
yellow and handed that setup its four closest members.

## Requirements

Rendering needs **headless Chrome**, and not as a matter of taste. Hoefler Text
has real small caps as `.small` glyphs, but delivers them through Apple's AAT
`morx` table rather than an OpenType `GSUB` table. CoreText reads `morx`; Chrome
on macOS uses CoreText. A FreeType-based renderer such as Pillow cannot reach
those glyphs at all without a `libraqm` build, and even then only for a font that
exposes small caps the OpenType way.

**For `apply` and `reset` only:**

1. "Switch to Desktop N" enabled in System Settings → Keyboard → Keyboard
   Shortcuts → Mission Control.
2. Accessibility permission for the terminal that runs the command. Without it
   macOS silently drops the synthetic keystroke, and the run stops at the first
   Space that did not switch (see [How it works](#how-it-works)).
3. **The frontmost window on the display you are targeting.** Control-N (the
   "Switch to Desktop N" hotkey) pages the display that holds keyboard *focus*,
   which the pointer alone does not move. If your terminal is frontmost on a
   different display, the run stops rather than page the wrong screen.
4. "Automatically rearrange Spaces based on most recent use" turned **off**, or
   Space numbering drifts underneath you.

## How it works

macOS 26 keeps wallpaper configuration in
`~/Library/Application Support/com.apple.wallpaper/Store/Index.plist`, as nested
binary plists. This tool never writes that file; it only reads it, to report what
each Space currently carries. Writing goes through the supported AppleScript API,
which has one useful property: `set picture` affects only the *currently active*
Space. So `apply` switches to each Space in turn and sets the picture there.

One smaller detail keeps a run honest. `apply` re-reads the Space layout after
each switch, because `osascript` exits 0 even when macOS drops the synthetic
keystroke for want of Accessibility permission — without that check, every Space
gets painted the last word and the run still claims success.

The tool joins four system sources, because no one of them is complete:

| Source | Supplies |
| --- | --- |
| CoreGraphics | display id, UUID, built-in flag, native pixels, screen bounds |
| AppKit `NSScreen` | display name, menu bar height, Dock thickness |
| SkyLight | which Spaces sit on which display, and which is current |
| the wallpaper store | which image, if any, each Space carries |

**On SkyLight.** `com.apple.spaces` records the same Space layout and is a public
preference file, but its `Current Space` is a *cache* that lags reality — it will
report Space 2 while you are looking at Space 3. Verifying a Space switch against
that value, as this tool's first version did, reports failures that never happened
and aborts runs that were working. So the tool reads the layout from SkyLight, the
private framework behind the window server that the Dock and Mission Control
themselves use.

That dependency is deliberately narrow. The tool only ever **reads** SkyLight,
never writes it; every change it makes still goes through public AppleScript. If
the framework is missing or changes shape, the read falls back to
`com.apple.spaces` and the tool keeps working, just with the stale `Current Space`
caveat.

`CGDirectDisplayID` is the join that matters: it is also what System Events calls
`desktop id`, so `set picture of desktop id 3` paints one resolved display and no
other. The obvious `tell every desktop` instead repaints *every* screen
attached to the machine, which is how a run aimed at one display overwrites
another.

### The wallpaper cache

macOS caches the desktop picture **by path**. Rewriting a file already assigned to
a Space changes nothing on screen. The file is right, the assignment is right, and
the previous render stays up. It looks as if the new artwork had failed to apply.
`make` and `apply` therefore restart `WallpaperAgent` after rendering, which
forces the re-read; it relaunches on demand.

A wallpaper that "didn't change" therefore wants two checks: the file's pixels and
the live screen can disagree.

## Wallpaper layout

Two parts of the wallpaper take their place from measurements, not guesses: the
bands and the badge.

The **menu bar band** and the **Dock band** are strips of plain ground at the top
and bottom, as tall as the menu bar and as thick as the Dock on that display.
Lettering behind the menu bar fights the menu titles for legibility, and lettering
behind the Dock fights the icons, so the wallpaper yields to both. The word field
overfills its box so the brick offset bleeds off the edges, which
means it must also be clipped — otherwise the overfill spills straight back over
the bands.

The **badge** is the chip that carries the Space's name, dark on near-white. It
appears in *both* left corners, because neither spot is reliably visible on its
own. The top corner is prime window real estate; the bottom one is clear only
while the Dock stays narrower than the screen, which a Dock with 30-odd items does
not. Whichever corner happens to be uncovered answers the question.

Both badges sit outside the bands. macOS draws the menu bar and the Dock *over*
the wallpaper, so anything inside those bands is hidden (including the gap that
appears to the left of the Finder icon, which belongs to the Dock's panel). Badge
size follows the Dock band's thickness so it reads at the same scale as the UI
beside it. `--no-badge` turns it off.

Both band thicknesses come from `NSScreen`. The gap between a screen's `frame` and
its `visibleFrame` is the only thing that reports them, and they vary with display,
macOS version, and Dock settings.

## Flashing the Space name on switching

The badge on each wallpaper identifies the Space in front of you; it cannot say
where you *just landed*, since at the moment of switching the eye is still moving
and the badge may be behind a window. `watch` flashes the name briefly on the
badge's own chip, in that Space's colors, centered low on the display that
changed. The word comes from the config, or failing that from the file name of the
wallpaper already on that Space, so the flash works before any config exists. A
Space with neither says nothing.

```
spacepaper watch              # foreground, Ctrl-C to stop
spacepaper watch --install    # register with launchd: starts at login
spacepaper watch --status     # installed? loaded? running?
spacepaper watch --uninstall  # stop it and forget it
```

`watch` hangs off `NSWorkspaceActiveSpaceDidChangeNotification`, which is public
API and fires for **every** route between Spaces: the Control-N hotkeys, a trackpad
swipe, Mission Control, a jump to a window on another Space. A keyboard hook
instead would catch only the hotkeys and would need Accessibility permission to
do it. The notification does not say *which* display changed, so `watch` works out
which by diffing a remembered snapshot of each display's current Space against a
fresh reading.

`--install` records the appearance options (`--hold`, `--fade`, `--scale`, `--font`)
into the launchd plist, so the agent flashes exactly as the command that installed
it would have. The plist records the executable's absolute path, because launchd
has none of your PATH or virtualenv. Move or delete the checkout and the agent
breaks until you re-run `--install`. Output goes to
`~/Library/Logs/spacepaper.log`.

## Resetting

```
spacepaper reset                    # every display, every Space
spacepaper reset --display builtin  # just that screen
```

The default picture follows `/System/Library/CoreServices/DefaultDesktop.heic`,
the symlink macOS repoints on each release, so it stays correct across upgrades
where a hardcoded `Sonoma.heic` would rot. Pass `--picture` for anything else.

System Settings' "same on all Spaces" is **not** scriptable. System Events'
`desktop` class exposes no such property, and the underlying `Linked` state
belongs to WallpaperAgent. `reset` therefore does the equivalent the long way. It
walks each Space and sets the same file on each; on screen the result is
indistinguishable, though underneath each Space keeps an assignment of its own
([known limitation 1](#known-limitations)).

## Uninstalling

The tool can put back everything it changed, except the macOS settings you changed
by hand to let it run and one piece of wallpaper state that only System Settings
can restore. The tool wrote nothing else; it only ever reads the wallpaper store,
`com.apple.spaces`, and SkyLight. Take the steps in the order below, because the
earlier steps need things the later ones remove.

1. **Stop the watcher.** `spacepaper watch --uninstall` boots the login agent out
   of launchd and deletes its plist. Do this step while the checkout still exists,
   because the plist records the executable's absolute path. If that binary is
   already gone, do the equivalent by hand:

   ```
   launchctl bootout gui/$(id -u)/com.spacepaper.watch
   rm ~/Library/LaunchAgents/com.spacepaper.watch.plist
   ```

2. **Put the wallpapers back.** `spacepaper reset` sets the macOS default picture
   on every Space of every display, and needs the same hotkeys, Accessibility
   permission, and frontmost window as `apply`. Nothing records what each Space
   carried before `apply` ran, so to restore your previous picture, hand it to
   `reset --picture FILE` or choose it in System Settings. Each Space keeps an
   assignment of its own afterward rather than following the global wallpaper
   again — [known limitation 1](#known-limitations).

3. **Delete the files it wrote**, all outside the repo and all listed under
   [Machine-local state](#machine-local-state):

   ```
   rm ~/Pictures/Wallpapers/*-*-[0-9]*x[0-9]*.png   # only the rendered wallpapers
   rm -r ~/.config/spacepaper                       # or $XDG_CONFIG_HOME/spacepaper
   rm ~/Library/Logs/spacepaper.log
   ```

   The wallpapers directory may hold other pictures, so delete by pattern
   (`word-palette-WxH.png`) rather than removing the directory. Delete them after
   step 2; otherwise a Space is left pointing at a file that no longer exists.

4. **Delete the checkout**, which holds the virtualenv and with it the `spacepaper`
   command.

5. **Undo the settings you changed for it**, if you did: Accessibility permission
   for your terminal (System Settings → Privacy & Security → Accessibility), the
   "Switch to Desktop N" shortcuts, and "Automatically rearrange Spaces based on
   most recent use". The tool never touched these settings, and cannot tell
   whether you did.

## Tests

```
uv run pytest                      # everything
uv run pytest -m "not render"      # skip the Chrome renders; the rest runs in 0.1 s
```

The suite has two tiers. Most tests are pure and instant; those marked `render`
drive headless Chrome and take about half a minute. They earn that half minute
because the layout guarantees here live in *pixels*, and the HTML has twice looked
correct while the output was wrong: once when the field's overfill spilled back
over the menu bar band, and once when a bottom-anchored badge moved between
measurement and screenshot.

The suite asserts the palette thresholds rather than merely documenting them, so an
edit that weakens the separation, lightness spread, or word contrast fails the
suite instead of shipping.

## Known limitations

1. **A Space cannot be returned to `inherits global`.** Once a Space has a
   picture of its own, `reset` can point it at the default image, but only System
   Settings can restore the `Linked` state that makes it follow the global
   wallpaper.
2. **At most nine Spaces per display**, the range the "Switch to Desktop N"
   hotkeys cover.
3. **Column width, not word length, fixes the type size**, so short words sit in
   airier fields than long ones. The unevenness is arguably a feature (density
   becomes a second identification cue), but the rhythm is not identical across
   Spaces.
