"""Run the Space watcher as a login agent.

`spacepaper watch` in a terminal stops the moment that terminal does, which is the
wrong lifetime for something whose whole job is to be there when you switch Spaces.
launchd gives it the right one: started at login, restarted if it dies, stopped only
when asked.

Everything here is per-user (`gui/<uid>`), so nothing needs privileges and nothing
leaves the user's own domain.
"""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.spacepaper.watch"
LOG = Path.home() / "Library/Logs/spacepaper.log"


def plist_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def domain() -> str:
    return f"gui/{os.getuid()}"


def executable() -> Path | None:
    """Absolute path to the installed `spacepaper`.

    launchd has none of the caller's PATH or virtualenv, so the plist has to name
    the binary outright. Under `uv run` argv[0] is already the venv's console
    script, which is exactly the right thing to record.
    """
    candidate = Path(sys.argv[0]).resolve()
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    found = shutil.which("spacepaper")
    return Path(found).resolve() if found else None


def launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def is_installed() -> bool:
    return plist_path().is_file()


def is_loaded() -> bool:
    """Whether launchd currently knows about the agent."""
    return launchctl("print", f"{domain()}/{LABEL}").returncode == 0


def pid() -> int | None:
    """The running watcher's pid, or None if it is loaded but not running."""
    result = launchctl("print", f"{domain()}/{LABEL}")
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "pid = " in line:
            try:
                return int(line.split("=", 1)[1].strip())
            except ValueError:
                return None
    return None


def write_plist(options: list[str]) -> Path:
    """Record the agent definition, carrying the watcher's own options with it."""
    binary = executable()
    if binary is None:
        raise FileNotFoundError(
            "cannot find the spacepaper executable to point launchd at; "
            "install the project first (uv sync)"
        )

    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        plistlib.dumps(
            {
                "Label": LABEL,
                "ProgramArguments": [str(binary), "watch", *options],
                "RunAtLoad": True,
                # Restart if it dies, but do not fight a deliberate stop.
                "KeepAlive": {"SuccessfulExit": False},
                "ProcessType": "Interactive",
                "StandardOutPath": str(LOG),
                "StandardErrorPath": str(LOG),
            }
        )
    )
    return target


def load() -> subprocess.CompletedProcess:
    return launchctl("bootstrap", domain(), str(plist_path()))


def unload() -> subprocess.CompletedProcess:
    return launchctl("bootout", f"{domain()}/{LABEL}")


def remove() -> None:
    plist_path().unlink(missing_ok=True)
