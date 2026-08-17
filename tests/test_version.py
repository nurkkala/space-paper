"""The version lives in one place and agrees with the tags.

pyproject.toml is the source; the installed metadata reads it; `--version` reports it;
and the git tags must not get ahead of it. Nothing here bumps anything -- that is the
release ritual's job -- it only notices when a bump and a tag have come apart.
"""

import re
import subprocess
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from space_paper.cli import app

ROOT = Path(__file__).resolve().parents[1]
TRIPLE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def pyproject_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def triple(text: str) -> tuple[int, int, int] | None:
    m = TRIPLE.match(text)
    return tuple(int(x) for x in m.groups()) if m else None


def git(*args: str) -> str | None:
    """Stdout of a git command run at the repo root, or None if it failed or is absent."""
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)
    except FileNotFoundError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def test_version_flag_reports_the_package_metadata():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"spacepaper {version('space-paper')}"


def test_installed_metadata_matches_pyproject():
    """One source. If these differ, the environment is stale, not the code."""
    assert version("space-paper") == pyproject_version()


def test_version_is_not_behind_the_newest_tag():
    tags = git("tag", "--list", "v*")
    if not tags:
        pytest.skip("no release tags (or no git)")
    newest = max(t for t in (triple(tag) for tag in tags.splitlines()) if t)
    assert triple(pyproject_version()) >= newest, (
        f"pyproject says {pyproject_version()} but v{'.'.join(map(str, newest))} is already tagged"
    )


def test_a_tagged_head_carries_its_own_version():
    tag = git("describe", "--tags", "--exact-match", "HEAD")
    if tag is None:
        pytest.skip("HEAD is not a release commit")
    assert tag == f"v{pyproject_version()}", f"HEAD is tagged {tag} but pyproject says {pyproject_version()}"
