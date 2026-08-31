"""Windows DPI awareness and Tk scaling helpers.

The module intentionally does not import Tkinter.  That keeps the helpers safe
to import from headless code and lets the desktop entry point opt into DPI
awareness before it creates the first ``Tk`` instance.
"""
from __future__ import annotations

import ctypes
import logging
import os
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("damage_gui.gui.dpi")
POINTS_PER_INCH = 72
PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_FUNCTION = 1
ERROR_INVALID_PARAMETER = 87
ERROR_CALL_NOT_IMPLEMENTED = 120
E_ACCESSDENIED = -2147024891
E_ACCESSDENIED_UNSIGNED = 0x80070005


@dataclass(frozen=True)
class DpiAwarenessResult:
    """Result of the best-effort process DPI-awareness bootstrap."""

    mode: str
    success: bool
    api: str


@dataclass(frozen=True)
class TkDpiInfo:
    """Observed and applied Tk scaling for one window."""

    actual_dpi: int | None
    before: float | None
    target: float | None
    after: float | None
    changed: bool
    source: str


def _is_windows() -> bool:
    return os.name == "nt"


def _context_value(value: int) -> ctypes.c_void_p:
    """Encode a signed DPI-awareness context as a pointer-sized value."""
    bits = ctypes.sizeof(ctypes.c_void_p) * 8
    return ctypes.c_void_p(value & ((1 << bits) - 1))


def enable_windows_dpi_awareness() -> DpiAwarenessResult:
    """Enable the strongest DPI mode supported by the current Windows host.

    The call is deliberately best effort.  A process manifest or an embedding
    host may already have selected DPI awareness; Windows reports that case as
    access denied, which is treated as an already-configured success.
    """
    if not _is_windows():
        return DpiAwarenessResult("non-windows", False, "none")

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        LOGGER.debug("Unable to load user32 for DPI awareness: %s", exc)
        return DpiAwarenessResult("unavailable", False, "user32")

    set_context = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if set_context is not None:
        try:
            set_context.argtypes = [ctypes.c_void_p]
            set_context.restype = ctypes.c_bool
            if set_context(_context_value(PER_MONITOR_AWARE_V2)):
                return DpiAwarenessResult("per-monitor-v2", True, "SetProcessDpiAwarenessContext")
            error = ctypes.get_last_error()
            if error == ERROR_ACCESS_DENIED:
                return DpiAwarenessResult("already-configured", True,
                                          "SetProcessDpiAwarenessContext")
            if error not in (ERROR_INVALID_FUNCTION, ERROR_INVALID_PARAMETER,
                             ERROR_CALL_NOT_IMPLEMENTED):
                LOGGER.debug("SetProcessDpiAwarenessContext failed with WinError %s", error)
        except (AttributeError, ctypes.ArgumentError, OSError) as exc:
            LOGGER.debug("SetProcessDpiAwarenessContext unavailable: %s", exc)

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        set_awareness = getattr(shcore, "SetProcessDpiAwareness", None)
        if set_awareness is not None:
            set_awareness.argtypes = [ctypes.c_int]
            set_awareness.restype = ctypes.c_long
            result = int(set_awareness(PROCESS_PER_MONITOR_DPI_AWARE))
            if result == 0:
                return DpiAwarenessResult("per-monitor", True, "SetProcessDpiAwareness")
            if result in (ERROR_ACCESS_DENIED, E_ACCESSDENIED, E_ACCESSDENIED_UNSIGNED):
                return DpiAwarenessResult("already-configured", True, "SetProcessDpiAwareness")
    except (AttributeError, ctypes.ArgumentError, OSError) as exc:
        LOGGER.debug("SetProcessDpiAwareness unavailable: %s", exc)

    try:
        set_aware = getattr(user32, "SetProcessDPIAware", None)
        if set_aware is not None:
            set_aware.argtypes = []
            set_aware.restype = ctypes.c_bool
            if set_aware():
                return DpiAwarenessResult("system-aware", True, "SetProcessDPIAware")
            if ctypes.get_last_error() == ERROR_ACCESS_DENIED:
                return DpiAwarenessResult("already-configured", True, "SetProcessDPIAware")
    except (AttributeError, ctypes.ArgumentError, OSError) as exc:
        LOGGER.debug("SetProcessDPIAware unavailable: %s", exc)

    return DpiAwarenessResult("unavailable", False, "none")


def inspect_tk_scaling(root: Any) -> float | None:
    """Read Tk's current pixels-per-point scaling without assuming a value."""
    try:
        return float(root.tk.call("tk", "scaling"))
    except (AttributeError, TypeError, ValueError):
        return None
    except Exception:  # TclError varies between Tk builds and is not import-safe here.
        LOGGER.debug("Unable to inspect Tk scaling", exc_info=True)
        return None


def dpi_to_tk_scaling(dpi: int | float) -> float:
    """Convert monitor DPI to Tk's documented pixels-per-point unit."""
    return float(dpi) / POINTS_PER_INCH


def get_window_dpi(window: Any) -> int | None:
    """Return the window's monitor DPI, with safe older-Windows fallbacks."""
    if not _is_windows():
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        LOGGER.debug("Unable to load user32 for monitor DPI: %s", exc)
        return None

    try:
        hwnd = int(window.winfo_id())
    except (AttributeError, TypeError, ValueError):
        hwnd = 0

    get_for_window = getattr(user32, "GetDpiForWindow", None)
    if get_for_window is not None and hwnd:
        try:
            get_for_window.argtypes = [ctypes.c_void_p]
            get_for_window.restype = ctypes.c_uint
            dpi = int(get_for_window(ctypes.c_void_p(hwnd)))
            if dpi > 0:
                return dpi
        except (AttributeError, ctypes.ArgumentError, OSError):
            LOGGER.debug("GetDpiForWindow unavailable", exc_info=True)

    get_for_system = getattr(user32, "GetDpiForSystem", None)
    if get_for_system is not None:
        try:
            get_for_system.argtypes = []
            get_for_system.restype = ctypes.c_uint
            dpi = int(get_for_system())
            if dpi > 0:
                return dpi
        except (AttributeError, ctypes.ArgumentError, OSError):
            LOGGER.debug("GetDpiForSystem unavailable", exc_info=True)

    # LOGPIXELSX is a final fallback for older Windows versions.
    try:
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        get_dc = getattr(user32, "GetDC", None)
        release_dc = getattr(user32, "ReleaseDC", None)
        get_device_caps = getattr(gdi32, "GetDeviceCaps", None)
        if get_dc is not None and release_dc is not None and get_device_caps is not None:
            get_dc.argtypes = [ctypes.c_void_p]
            get_dc.restype = ctypes.c_void_p
            release_dc.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            release_dc.restype = ctypes.c_int
            get_device_caps.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_device_caps.restype = ctypes.c_int
            hdc = get_dc(ctypes.c_void_p(0))
            if hdc:
                try:
                    dpi = int(get_device_caps(hdc, 88))  # LOGPIXELSX
                    if dpi > 0:
                        return dpi
                finally:
                    release_dc(ctypes.c_void_p(0), hdc)
    except (AttributeError, ctypes.ArgumentError, OSError):
        LOGGER.debug("LOGPIXELSX fallback unavailable", exc_info=True)
    return None


def sync_tk_scaling(root: Any, dpi: int | None = None) -> TkDpiInfo:
    """Align Tk scaling with the observed monitor DPI when it is available."""
    before = inspect_tk_scaling(root)
    actual_dpi = dpi if dpi is not None else get_window_dpi(root)
    target = None
    changed = False
    source = "unavailable"
    if actual_dpi is not None and actual_dpi > 0:
        target = dpi_to_tk_scaling(actual_dpi)
        source = "explicit" if dpi is not None else "window"
        if before is None or abs(before - target) > 0.005:
            try:
                root.tk.call("tk", "scaling", target)
                changed = True
            except Exception:
                LOGGER.debug("Unable to set Tk scaling to %.4f", target, exc_info=True)
    after = inspect_tk_scaling(root)
    return TkDpiInfo(actual_dpi, before, target, after, changed, source)


def install_tk_scaling_monitor(root: Any) -> None:
    """Recheck monitor DPI after Tk configure events, including monitor moves."""
    last_dpi = get_window_dpi(root)
    pending = False

    def schedule(_event: Any = None) -> None:
        nonlocal pending
        if pending:
            return
        pending = True
        try:
            root.after_idle(resync)
        except Exception:
            pending = False

    def resync() -> None:
        nonlocal last_dpi, pending
        pending = False
        try:
            dpi = get_window_dpi(root)
            if dpi is not None and dpi != last_dpi:
                sync_tk_scaling(root, dpi)
                last_dpi = dpi
        except Exception:
            LOGGER.debug("Unable to resync Tk scaling after configure", exc_info=True)

    try:
        root.bind("<Configure>", schedule, add="+")
    except Exception:
        LOGGER.debug("Unable to install Tk DPI monitor", exc_info=True)
