"""A user-level record of *intent*: which words belong on which display.

The distinction this file rests on: nothing macOS can tell us at run time is stored
here. Display ids, menu bar and Dock thickness, native resolution, and how many
Spaces a screen has are all measured on every run, because every one of them changes
under you -- docking a laptop, moving the Dock, adding a Space, changing resolution.
A config that cached them would go stale silently and paint the wrong screen, which
is the same class of bug as trusting com.apple.spaces for the current Space.

What macOS cannot know is which word you want on Space 3, and that is what lives
here. An empty word list is meaningful: it says "leave this display alone", which is
how a laptop screen stays untouched while an external monitor gets painted.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FILENAME = "config.toml"
APP = "spacepaper"

HEADER = """\
# spacepaper configuration
#
# Only intent is recorded here. Display resolution, menu bar and Dock size, and the
# number of Spaces on each screen are measured at run time, never stored, because
# they change whenever you dock, undock, or rearrange things.
#
# Match a display by name, or by "main", "builtin", "external", an index, or a UUID.
# An empty `words` list means: leave that display alone.
"""


class ConfigError(Exception):
    """The config file exists but could not be understood."""


@dataclass
class Screen:
    """What the user wants on one display."""

    match: str
    words: list[str] = field(default_factory=list)
    palette_set: str | None = None
    badge: bool | None = None


@dataclass
class Config:
    """Defaults plus a per-display intent."""

    palette_set: str = "bright"
    badge: bool = True
    screens: list[Screen] = field(default_factory=list)

    def for_display(self, name: str) -> Screen | None:
        return next((s for s in self.screens if s.match == name), None)


def path() -> Path:
    """Where the config lives, honoring XDG_CONFIG_HOME when it is set."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP / FILENAME


def exists() -> bool:
    return path().is_file()


def load() -> Config:
    """Read the config, or return defaults when there is none."""
    target = path()
    if not target.is_file():
        return Config()
    try:
        raw = tomllib.loads(target.read_text())
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigError(f"{target}: {exc}") from exc

    screens = []
    for match, body in (raw.get("displays") or {}).items():
        if not isinstance(body, dict):
            raise ConfigError(f"{target}: [displays.{match!r}] is not a table")
        words = body.get("words", [])
        if not isinstance(words, list) or any(not isinstance(w, str) for w in words):
            raise ConfigError(f"{target}: words for {match!r} must be a list of strings")
        screens.append(
            Screen(
                match=match,
                words=words,
                palette_set=body.get("set"),
                badge=body.get("badge"),
            )
        )
    return Config(
        palette_set=raw.get("set", "bright"),
        badge=raw.get("badge", True),
        screens=screens,
    )


def _quote(value: str) -> str:
    """A TOML basic string. Display names carry spaces and the odd quote."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dumps(config: Config) -> str:
    """Render a config back to TOML. Hand-rolled: the shape is small and fixed, and
    the standard library writes no TOML."""
    lines = [HEADER, f"set = {_quote(config.palette_set)}", f"badge = {str(config.badge).lower()}"]
    for screen in config.screens:
        lines.append(f"\n[displays.{_quote(screen.match)}]")
        words = ", ".join(_quote(w) for w in screen.words)
        lines.append(f"words = [{words}]")
        if screen.palette_set is not None:
            lines.append(f"set = {_quote(screen.palette_set)}")
        if screen.badge is not None:
            lines.append(f"badge = {str(screen.badge).lower()}")
    return "\n".join(lines) + "\n"


def save(config: Config) -> Path:
    """Write the config, creating its directory."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(config))
    return target
