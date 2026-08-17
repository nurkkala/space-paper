"""Discover displays, the Spaces on each, and the wallpaper each Space carries.

Three system sources have to be joined, because no one of them is complete:

    CoreGraphics       display id, UUID, built-in flag, native pixels, bounds
    com.apple.spaces   which Spaces sit on which display, in Mission Control order
    wallpaper Store    which image, if any, each Space carries

CGDirectDisplayID is the join that matters most: it is also what System Events
calls `desktop id`, so a display resolved here can be written to by itself --
`set picture of desktop id 3` touches that screen and no other. That is the whole
reason this module exists. The obvious `tell every desktop` writes every display
at once, which silently repaints screens the caller never asked about.
"""

import ctypes
import ctypes.util
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

SPACES_DOMAIN = "com.apple.spaces"
STORE = Path.home() / "Library/Application Support/com.apple.wallpaper/Store/Index.plist"

# com.apple.spaces names the main display "Main" rather than by UUID; every other
# display is keyed by the same UUID CoreGraphics reports.
MAIN_SENTINEL = "Main"

_cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
_cs = ctypes.CDLL(ctypes.util.find_library("ColorSync"))
_cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


_cf.CFUUIDCreateString.restype = ctypes.c_void_p
_cf.CFUUIDCreateString.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_cf.CFRelease.argtypes = [ctypes.c_void_p]
_cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_cs.CGDisplayCreateUUIDFromDisplayID.restype = ctypes.c_void_p
_cs.CGDisplayCreateUUIDFromDisplayID.argtypes = [ctypes.c_uint32]
_cg.CGDisplayBounds.restype = _CGRect
_cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
_cg.CGDisplayCopyDisplayMode.restype = ctypes.c_void_p
_cg.CGDisplayCopyDisplayMode.argtypes = [ctypes.c_uint32]
_cg.CGDisplayModeRelease.argtypes = [ctypes.c_void_p]
_cg.CGDisplayModeGetPixelWidth.restype = ctypes.c_size_t
_cg.CGDisplayModeGetPixelWidth.argtypes = [ctypes.c_void_p]
_cg.CGDisplayModeGetPixelHeight.restype = ctypes.c_size_t
_cg.CGDisplayModeGetPixelHeight.argtypes = [ctypes.c_void_p]

_UTF8 = 0x08000100
_BINARY_PLIST = 200

# SkyLight is the private framework behind the window server -- the successor to the
# old CoreGraphics "CGS" window-management calls, and what the Dock and Mission
# Control themselves use. It is read from here and never written to, for one
# reason: com.apple.spaces is a *cached preference*, and its "Current Space" lags
# reality by seconds or longer. Verifying a Space switch against that stale value
# reports failures that did not happen, and would stop a run that was working. Every
# write this tool makes still goes through public API.
#
# Being private, it may vanish or change in any macOS release, so its absence is not
# an error: the plist fallback below is used instead, and the tool keeps working.
_SKYLIGHT_PATH = "/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight"


class DisplayError(Exception):
    """A display selector matched no display, or more than one."""


@dataclass(frozen=True)
class Space:
    """One Space (desktop) on one display."""

    uuid: str
    number: int  # position on its own display, 1-based, in Mission Control order
    picture: Path | None  # None when the Space inherits the global wallpaper
    current: bool

    @property
    def wallpaper(self) -> str:
        return self.picture.name if self.picture else "-- inherits global --"


@dataclass(frozen=True)
class Display:
    """One physical screen, with the Spaces macOS has given it."""

    cg_id: int  # CGDirectDisplayID; System Events calls this `desktop id`
    uuid: str
    name: str
    builtin: bool
    main: bool
    width: int  # native backing pixels, which is what a wallpaper wants
    height: int
    menubar: int  # native pixels the menu bar covers along the top edge
    dock: int  # native pixels the Dock covers along the bottom edge, 0 if elsewhere
    bounds: tuple[float, float, float, float]  # x, y, w, h in global points
    spaces: tuple[Space, ...]

    @property
    def kind(self) -> str:
        return "built-in" if self.builtin else "external"

    @property
    def label(self) -> str:
        tags = [self.kind] + (["main"] if self.main else [])
        return f"{self.name} ({', '.join(tags)})"

    @property
    def current_space(self) -> int:
        """Number of the active Space on this display, or 0 if unknown."""
        return next((s.number for s in self.spaces if s.current), 0)


def _cfstring(ref: int) -> str:
    buf = ctypes.create_string_buffer(256)
    _cf.CFStringGetCString(ref, buf, 256, _UTF8)
    return buf.value.decode()


def _display_uuid(cg_id: int) -> str:
    """UUID string for a display, as com.apple.spaces and the wallpaper Store key it."""
    ref = _cs.CGDisplayCreateUUIDFromDisplayID(cg_id)
    if not ref:
        return ""
    try:
        sref = _cf.CFUUIDCreateString(None, ref)
        try:
            return _cfstring(sref)
        finally:
            _cf.CFRelease(sref)
    finally:
        _cf.CFRelease(ref)


def _native_pixels(cg_id: int) -> tuple[int, int]:
    """Backing-store resolution, not the scaled point size. A 4K display running a
    1920x1080 "looks like" mode still wants a 3840x2160 wallpaper."""
    mode = _cg.CGDisplayCopyDisplayMode(cg_id)
    if not mode:
        return _cg.CGDisplayPixelsWide(cg_id), _cg.CGDisplayPixelsHigh(cg_id)
    try:
        return _cg.CGDisplayModeGetPixelWidth(mode), _cg.CGDisplayModeGetPixelHeight(mode)
    finally:
        _cg.CGDisplayModeRelease(mode)


def _online_displays(limit: int = 16) -> list[int]:
    count = ctypes.c_uint32()
    ids = (ctypes.c_uint32 * limit)()
    if _cg.CGGetOnlineDisplayList(limit, ids, ctypes.byref(count)) != 0:
        return []
    return [ids[i] for i in range(count.value) if _cg.CGDisplayIsActive(ids[i])]


def _screen_facts() -> dict[int, tuple[str, int, int]]:
    """Name, menu bar height, and Dock thickness per display id, in native pixels.

    Keyed by `NSScreenNumber`, which is the CGDirectDisplayID everything else here
    joins on. The insets are measured rather than assumed: both vary with display,
    macOS version, and the user's Dock settings, and a wallpaper that keeps its
    lettering clear of the menu bar has to know how tall that bar is on *this*
    screen. AppKit is the only thing that reports them, via the gap between a
    screen's frame and its visible frame.

    Returns an empty mapping if AppKit cannot be reached, leaving callers their own
    defaults rather than failing outright -- a wallpaper without a reserved band is
    degraded, not broken.
    """
    try:
        from AppKit import NSScreen
    except ImportError:
        return {}

    found = {}
    for screen in NSScreen.screens():
        try:
            cg_id = int(screen.deviceDescription()["NSScreenNumber"])
            frame, visible = screen.frame(), screen.visibleFrame()
            scale = screen.backingScaleFactor()
            dock = (visible.origin.y - frame.origin.y) * scale
            menubar = (frame.size.height * scale) - (dock + visible.size.height * scale)
            found[cg_id] = (str(screen.localizedName()), max(round(menubar), 0), max(round(dock), 0))
        except (KeyError, AttributeError, TypeError, ValueError):
            continue
    return found


def _skylight() -> ctypes.CDLL | None:
    """Load SkyLight, or None if it is unavailable on this system."""
    try:
        lib = ctypes.CDLL(_SKYLIGHT_PATH)
        lib.SLSMainConnectionID.restype = ctypes.c_int
        lib.SLSCopyManagedDisplaySpaces.restype = ctypes.c_void_p
        lib.SLSCopyManagedDisplaySpaces.argtypes = [ctypes.c_int]
    except (OSError, AttributeError):
        return None
    return lib


def _unwrap(ref: int):
    """Convert a CoreFoundation container to Python by round-tripping it as a plist."""
    _cf.CFPropertyListCreateData.restype = ctypes.c_void_p
    _cf.CFPropertyListCreateData.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p
    ]
    _cf.CFDataGetBytePtr.restype = ctypes.c_void_p
    _cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    _cf.CFDataGetLength.restype = ctypes.c_long
    _cf.CFDataGetLength.argtypes = [ctypes.c_void_p]

    data = _cf.CFPropertyListCreateData(None, ref, _BINARY_PLIST, 0, None)
    if not data:
        raise ValueError("layout is not a property list")
    try:
        return plistlib.loads(ctypes.string_at(_cf.CFDataGetBytePtr(data), _cf.CFDataGetLength(data)))
    finally:
        _cf.CFRelease(data)


def _live_layout() -> dict[str, tuple[list[str], str]]:
    """Space order and the *current* Space per display, straight from the window server.

    Returns display UUID -> (ordered Space UUIDs, current Space UUID). Empty when
    SkyLight is unavailable, which sends callers to the cached-plist fallback.

    Full-screen apps occupy Spaces of their own (type 4) that Mission Control does
    not number, so they are dropped -- counting them would shift every desktop
    number and send `apply` to the wrong Space.
    """
    lib = _skylight()
    if lib is None:
        return {}
    ref = lib.SLSCopyManagedDisplaySpaces(lib.SLSMainConnectionID())
    if not ref:
        return {}
    try:
        monitors = _unwrap(ref)
    except (ValueError, plistlib.InvalidFileException):
        return {}
    finally:
        _cf.CFRelease(ref)

    found: dict[str, tuple[list[str], str]] = {}
    for monitor in monitors:
        if not isinstance(monitor, dict):
            continue
        key = monitor.get("Display Identifier", "")
        spaces = [
            s["uuid"]
            for s in monitor.get("Spaces", [])
            if isinstance(s, dict) and "uuid" in s and s.get("type") == 0
        ]
        current = monitor.get("Current Space", {})
        if key and spaces:
            found[key] = (spaces, current.get("uuid", "") if isinstance(current, dict) else "")
    return found


def _spaces_by_display(main_uuid: str) -> dict[str, list[str]]:
    """Space UUIDs per display UUID, in Mission Control order.

    Stale monitor records accumulate in this plist for displays that have been
    unplugged; they are recognizable by carrying no Spaces at all, so they are
    dropped rather than colliding with the live record for the same UUID.
    """
    raw = subprocess.run(
        ["defaults", "export", SPACES_DOMAIN, "-"], capture_output=True
    ).stdout
    try:
        monitors = plistlib.loads(raw)["SpacesDisplayConfiguration"]["Management Data"]["Monitors"]
    except (KeyError, TypeError, ValueError):
        return {}

    found: dict[str, list[str]] = {}
    for monitor in monitors:
        spaces = [s["uuid"] for s in monitor.get("Spaces", []) if "uuid" in s]
        if not spaces:
            continue
        key = monitor.get("Display Identifier", "")
        found[main_uuid if key == MAIN_SENTINEL else key] = spaces
    return found


def _current_spaces() -> set[str]:
    """UUIDs of the active Space on each display -- one per screen."""
    raw = subprocess.run(
        ["defaults", "export", SPACES_DOMAIN, "-"], capture_output=True
    ).stdout
    try:
        monitors = plistlib.loads(raw)["SpacesDisplayConfiguration"]["Management Data"]["Monitors"]
    except (KeyError, TypeError, ValueError):
        return set()
    return {
        m["Current Space"]["uuid"]
        for m in monitors
        if isinstance(m.get("Current Space"), dict) and "uuid" in m["Current Space"]
    }


def _picture_of(node: dict) -> Path | None:
    """Pull the image path out of one wallpaper Store node.

    A Space that has never been given its own picture is `Linked`, meaning it
    follows the global wallpaper; that reads back as None rather than a path.
    The path itself is buried in a nested binary plist under `Configuration`.
    """
    try:
        choice = node["Desktop"]["Content"]["Choices"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if not str(choice.get("Provider", "")).endswith(".image"):
        return None
    config = choice.get("Configuration")
    if not config:
        return None
    try:
        url = plistlib.loads(config)["url"]["relative"]
    except (KeyError, TypeError, ValueError, plistlib.InvalidFileException):
        return None
    return Path(unquote(urlparse(url).path))


def _pictures(display_uuid: str) -> dict[str, Path | None]:
    """Wallpaper per Space UUID, as recorded for one display.

    Each Space keeps a per-display node plus a `Default`; the per-display node wins
    when present, since that is what the screen in question actually shows.
    """
    if not STORE.is_file():
        return {}
    try:
        store = plistlib.loads(STORE.read_bytes())
    except (ValueError, plistlib.InvalidFileException):
        return {}

    found: dict[str, Path | None] = {}
    for uuid, space in store.get("Spaces", {}).items():
        if not isinstance(space, dict):
            continue
        displays = space.get("Displays", {})
        node = displays.get(display_uuid) or space.get("Default", {})
        found[uuid] = _picture_of(node) if isinstance(node, dict) else None
    return found


def displays() -> list[Display]:
    """Every active display, main first, then by display id.

    The ordering makes the printed index a convenient handle, but it moves when the
    main display changes -- names and UUIDs are the stable way to name a screen.
    """
    facts = _screen_facts()
    uuids = {cg_id: _display_uuid(cg_id) for cg_id in _online_displays()}
    main_uuid = next(
        (u for cg_id, u in uuids.items() if _cg.CGDisplayIsMain(cg_id)), ""
    )

    # Prefer the window server's live answer; the cached plist is only a fallback,
    # since its "Current Space" can be stale enough to misreport a Space switch.
    live = _live_layout()
    if live:
        layout = {uuid: spaces for uuid, (spaces, _) in live.items()}
        current = {current for _, current in live.values() if current}
    else:
        layout = _spaces_by_display(main_uuid)
        current = _current_spaces()

    found = []
    for cg_id, uuid in uuids.items():
        pictures = _pictures(uuid)
        spaces = tuple(
            Space(
                uuid=space_uuid,
                number=n,
                picture=pictures.get(space_uuid),
                current=space_uuid in current,
            )
            for n, space_uuid in enumerate(layout.get(uuid, []), start=1)
        )
        rect = _cg.CGDisplayBounds(cg_id)
        width, height = _native_pixels(cg_id)
        builtin = bool(_cg.CGDisplayIsBuiltin(cg_id))
        name, menubar, dock = facts.get(
            cg_id, ("Built-in Display" if builtin else f"Display {cg_id}", 0, 0)
        )
        found.append(
            Display(
                cg_id=cg_id,
                uuid=uuid,
                name=name,
                builtin=builtin,
                main=bool(_cg.CGDisplayIsMain(cg_id)),
                width=width,
                height=height,
                menubar=menubar,
                dock=dock,
                bounds=(rect.origin.x, rect.origin.y, rect.size.width, rect.size.height),
                spaces=spaces,
            )
        )
    return sorted(found, key=lambda d: (not d.main, d.cg_id))


def resolve(selector: str, among: list[Display] | None = None) -> Display:
    """Find the one display a selector names.

    Accepts `main`, `builtin`/`internal`, `external`, a 1-based index as printed by
    `spacepaper status`, a UUID prefix, or any case-insensitive part of the display
    name. Ambiguity is an error rather than a guess, because guessing wrong here
    repaints the wrong screen.
    """
    found = among if among is not None else displays()
    if not found:
        raise DisplayError("no active displays found")

    key = selector.strip().lower()
    if key in {"main", "primary"}:
        matches = [d for d in found if d.main]
    elif key in {"builtin", "built-in", "internal", "laptop", "mac"}:
        matches = [d for d in found if d.builtin]
    elif key == "external":
        matches = [d for d in found if not d.builtin]
    elif key.isdigit() and 1 <= int(key) <= len(found):
        matches = [found[int(key) - 1]]
    else:
        matches = [d for d in found if d.uuid.lower().startswith(key)]
        matches = matches or [d for d in found if key in d.name.lower()]

    catalog = "; ".join(f"{i}={d.name}" for i, d in enumerate(found, start=1))
    if not matches:
        raise DisplayError(f"no display matches {selector!r}. Available: {catalog}")
    if len(matches) > 1:
        names = ", ".join(d.name for d in matches)
        raise DisplayError(f"{selector!r} is ambiguous -- matches {names}. Available: {catalog}")
    return matches[0]
