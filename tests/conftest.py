"""Shared fixtures. Nothing here touches the real machine.

Display and Space are plain frozen dataclasses, so the whole discovery layer can be
stood up from literals -- which is the point of having separated it from the CLI.
"""

import shutil

import pytest

from space_paper import displays as dsp


def make_space(number: int, picture: str | None = None, current: bool = False) -> dsp.Space:
    from pathlib import Path

    return dsp.Space(
        uuid=f"space-{number:04d}",
        number=number,
        picture=Path(picture) if picture else None,
        current=current,
    )


def make_display(
    cg_id: int = 3,
    name: str = "ACME 27",
    *,
    builtin: bool = False,
    main: bool = True,
    width: int = 3840,
    height: int = 2160,
    menubar: int = 60,
    dock: int = 152,
    spaces: int = 4,
    uuid: str | None = None,
) -> dsp.Display:
    return dsp.Display(
        cg_id=cg_id,
        # Shaped like a real CGDisplay UUID and differing at the *first* character,
        # so prefix matching is exercised rather than defeated by a shared stem.
        uuid=uuid or f"{cg_id:X}A67C1F6-2652-40B3-88C7-8E8EEB0A6E95",
        name=name,
        builtin=builtin,
        main=main,
        width=width,
        height=height,
        menubar=menubar,
        dock=dock,
        bounds=(0.0, 0.0, width / 2, height / 2),
        spaces=tuple(make_space(n, current=(n == 1)) for n in range(1, spaces + 1)),
    )


@pytest.fixture
def external() -> dsp.Display:
    return make_display(cg_id=3, name="ACME 27", builtin=False, main=True, spaces=4)


@pytest.fixture
def builtin() -> dsp.Display:
    return make_display(
        cg_id=1, name="Built-in Display", builtin=True, main=False,
        width=3024, height=1964, menubar=64, dock=0, spaces=1,
    )


@pytest.fixture
def two_screens(external, builtin) -> list[dsp.Display]:
    return [external, builtin]


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Point the config at a temp directory, so tests never touch the real one."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


needs_chrome = pytest.mark.skipif(
    not (
        shutil.which("chromium")
        or shutil.which("google-chrome")
        or any(
            __import__("pathlib").Path(p).is_file()
            for p in [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    ),
    reason="no Chrome or Chromium available to render with",
)
