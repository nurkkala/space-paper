"""Flash the Space's name on screen when the active Space changes.

The wallpaper badge answers "which Space am I on" at any moment; this answers "where
did I just land" at the moment of landing, when the eye is still moving and the badge
may well be behind a window.

It hangs off NSWorkspaceActiveSpaceDidChangeNotification, which is public API and
fires for *every* way of changing Space -- the Control-N hotkeys, a trackpad swipe,
clicking in Mission Control, following a window to another desktop. Hooking the
hotkeys themselves would catch only the first of those, and would need an
Accessibility event tap to do it.

Which display changed is not in the notification, so it is worked out by diffing a
remembered snapshot of each display's current Space against a fresh reading.
"""

from dataclasses import dataclass

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSMakeRect,
    NSScreen,
    NSScreenSaverWindowLevel,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWorkspace,
    NSWorkspaceActiveSpaceDidChangeNotification,
)
from Foundation import NSObject, NSTimer
import objc

from . import displays as dsp

# AAT feature selectors for real small caps, the same glyphs the wallpaper uses.
# Hoefler Text carries them through `morx` rather than an OpenType GSUB table.
LETTER_CASE_FEATURE = 3
SMALL_CAPS_SELECTOR = 3


@dataclass(frozen=True)
class Landing:
    """A display, and the Space just arrived at on it."""

    display: dsp.Display
    space: int


def color(hex_string: str, alpha: float = 1.0):
    """NSColor from a #RRGGBB string."""
    r, g, b = (int(hex_string[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def small_caps_font(name: str, size: float):
    """The named font in small caps, or plain if the face has no such feature."""
    base = NSFont.fontWithName_size_(name, size)
    if base is None:
        return NSFont.systemFontOfSize_(size)
    try:
        descriptor = base.fontDescriptor().fontDescriptorByAddingAttributes_(
            {
                "NSCTFontFeatureSettingsAttribute": [
                    {
                        "CTFeatureTypeIdentifier": LETTER_CASE_FEATURE,
                        "CTFeatureSelectorIdentifier": SMALL_CAPS_SELECTOR,
                    }
                ]
            }
        )
        return NSFont.fontWithDescriptor_size_(descriptor, size) or base
    except Exception:
        return base


def screen_for(cg_id: int):
    """The NSScreen whose display id matches, or None if it has gone away."""
    for screen in NSScreen.screens():
        try:
            if int(screen.deviceDescription()["NSScreenNumber"]) == cg_id:
                return screen
        except (KeyError, TypeError, ValueError):
            continue
    return None


def snapshot() -> dict[str, int]:
    """Each display's current Space number, keyed by display UUID."""
    return {screen.uuid: screen.current_space for screen in dsp.displays()}


def landings(before: dict[str, int], after: list[dsp.Display]) -> list[Landing]:
    """Displays whose current Space changed since the snapshot.

    A display absent from `before` counts as changed: that is a screen just plugged
    in, and saying where it landed is more useful than staying quiet. Displays that
    did not move are skipped, so swapping Space on one screen does not flash on the
    other.
    """
    moved = []
    for screen in after:
        if not screen.current_space:
            continue
        if before.get(screen.uuid) != screen.current_space:
            moved.append(Landing(display=screen, space=screen.current_space))
    return moved


class Overlay:
    """A borderless, click-through chip that fades itself out."""

    def __init__(self, *, font: str = "Hoefler Text", scale: float = 1.0):
        self.font_name = font
        self.scale = scale
        self._windows = []

    def show(self, word: str, chip: str, text: str, screen, hold: float, fade: float):
        frame = screen.frame()
        height = round(min(frame.size.height, frame.size.width) * 0.085 * self.scale)
        size = height * 0.46
        field = NSTextField.labelWithString_(word)
        field.setFont_(small_caps_font(self.font_name, size))
        field.setTextColor_(color(text))
        field.sizeToFit()

        pad = height * 0.55
        width = field.frame().size.width + pad * 2
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(
                frame.origin.x + (frame.size.width - width) / 2,
                frame.origin.y + frame.size.height * 0.16,
                width,
                height,
            ),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setLevel_(NSScreenSaverWindowLevel)
        window.setHasShadow_(False)
        # Click-through, and present on whatever Space the user lands on -- without
        # this the window would belong to the Space it was created on and be
        # invisible exactly when it is needed.
        window.setIgnoresMouseEvents_(True)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
        )

        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        view.setWantsLayer_(True)
        layer = view.layer()
        layer.setCornerRadius_(height / 2)
        layer.setBackgroundColor_(color(chip, 0.96).CGColor())
        layer.setBorderWidth_(max(1.0, height * 0.035))
        layer.setBorderColor_(color(text).CGColor())

        box = field.frame()
        field.setFrameOrigin_(((width - box.size.width) / 2, (height - box.size.height) / 2))
        view.addSubview_(field)
        window.setContentView_(view)
        window.orderFrontRegardless()

        self._windows.append(window)
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            hold, False, lambda timer: self._fade(window, fade)
        )

    def _fade(self, window, fade: float):
        from AppKit import NSAnimationContext

        def finish():
            window.orderOut_(None)
            if window in self._windows:
                self._windows.remove(window)

        NSAnimationContext.runAnimationGroup_completionHandler_(
            lambda context: (context.setDuration_(fade), window.animator().setAlphaValue_(0.0)),
            finish,
        )


class Watcher(NSObject):
    """Bridges the workspace notification to the overlay."""

    def initWithFlasher_(self, flasher):
        self = objc.super(Watcher, self).init()
        if self is None:
            return None
        self._flasher = flasher
        return self

    def spaceChanged_(self, notification):
        self._flasher()
