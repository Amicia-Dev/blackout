from __future__ import annotations

import ctypes
from dataclasses import dataclass

# Edge shortfall (physical px) still counted as "covers the monitor".
TOL = 4
# Fraction of a monitor's work area a maximized window must cover.
MAXIMIZED_COVERAGE = 0.99


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True)
class Monitor:
    rect: Rect
    work_area: Rect


@dataclass(frozen=True)
class WindowInfo:
    rect: Rect
    maximized: bool


def area(r: Rect) -> int:
    """Rect area in px, clamped to >= 0 per dimension."""
    w = max(0, r.right - r.left)
    h = max(0, r.bottom - r.top)
    return w * h


def covers_fullscreen(win: WindowInfo, mon: Monitor) -> bool:
    """True if win.rect covers mon.rect, allowing TOL px shortfall per edge."""
    return (
        win.rect.left <= mon.rect.left + TOL
        and win.rect.top <= mon.rect.top + TOL
        and win.rect.right >= mon.rect.right - TOL
        and win.rect.bottom >= mon.rect.bottom - TOL
    )


def covers_maximized(win: WindowInfo, mon: Monitor) -> bool:
    """True if win is maximized and covers >= MAXIMIZED_COVERAGE of mon.work_area."""
    if not win.maximized:
        return False
    inter = Rect(
        max(win.rect.left, mon.work_area.left),
        max(win.rect.top, mon.work_area.top),
        min(win.rect.right, mon.work_area.right),
        min(win.rect.bottom, mon.work_area.bottom),
    )
    return area(inter) >= MAXIMIZED_COVERAGE * area(mon.work_area)


def monitor_in_use(mon: Monitor, windows: list[WindowInfo]) -> bool:
    """True if any window is fullscreen or maximized on this monitor."""
    return any(
        covers_fullscreen(w, mon) or covers_maximized(w, mon) for w in windows
    )


def find_free_monitors(
    monitors: list[Monitor], windows: list[WindowInfo]
) -> list[Monitor]:
    """Monitors not in use, in input order — these get blacked out."""
    return [m for m in monitors if not monitor_in_use(m, windows)]


# ---------------------------------------------------------------------------
# Win32 layer (stdlib ctypes only). Everything below is Windows-only.
# ---------------------------------------------------------------------------
import sys

if sys.platform != "win32":
    raise SystemExit("Blackout only runs on Windows.")

from ctypes import wintypes  # noqa: E402
from ctypes.wintypes import RECT, WPARAM, LPARAM  # noqa: E402

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi
kernel32 = ctypes.windll.kernel32

# Constants
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_MAXIMIZE = 0x01000000
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
VK_ESCAPE = 0x1B
WH_KEYBOARD_LL = 13
ERROR_ALREADY_EXISTS = 183
DWMWA_CLOAKED = 14
BLACK_BRUSH = 4  # stock brush IDs: 0=WHITE_BRUSH ... 4=BLACK_BRUSH
CLASS_NAME = "BlackoutOverlayWindow"
MUTEX_NAME = "Local\\BlackoutOverlayMutex"


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, WPARAM, LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HANDLE, wintypes.HANDLE,
                                     ctypes.POINTER(RECT), ctypes.py_object)
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, ctypes.py_object)

# --- ctypes signatures: without these, 64-bit handles (HINSTANCE, HWND,
# HMODULE) truncate to 32-bit c_int and calls silently misbehave. ---
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.PostQuitMessage.argtypes = [wintypes.UINT]
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, ctypes.c_int]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD]
gdi32.GetStockObject.restype = wintypes.HBRUSH
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassW.restype = wintypes.UINT
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, wintypes.DWORD, wintypes.DWORD,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                     wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _monitor_enum_callback(hMon, hdc, lprcMonitor, lParam) -> int:
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    user32.GetMonitorInfoW(hMon, ctypes.byref(info))
    monitors_list = lParam
    monitors_list.append(
        Monitor(
            rect=Rect(info.rcMonitor.left, info.rcMonitor.top,
                      info.rcMonitor.right, info.rcMonitor.bottom),
            work_area=Rect(info.rcWork.left, info.rcWork.top,
                           info.rcWork.right, info.rcWork.bottom),
        )
    )
    return 1


def get_monitors() -> list[Monitor]:
    """All attached monitors (physical pixels after the DPI-awareness call)."""
    monitors_list: list[Monitor] = []
    # Keep a local reference: ctypes needs the callback object alive during the call.
    cb = MONITORENUMPROC(_monitor_enum_callback)
    user32.EnumDisplayMonitors(None, None, cb, ctypes.py_object(monitors_list))
    return monitors_list


def _window_enum_callback(hwnd, lParam) -> int:
    if not user32.IsWindowVisible(hwnd):
        return 1
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW:
        return 1
    # Cloaked check (UWP apps can be cloaked).
    # DwmGetWindowAttribute returns S_OK (0) on success, so test for 0.
    try:
        cloaked = wintypes.DWORD(0)
        hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
        if hr == 0 and cloaked.value:
            return 1
    except Exception:
        pass
    # Skip our own overlay windows
    class_name = user32.GetClassNameW(hwnd, None, 0)
    if class_name:
        buf = ctypes.create_unicode_buffer(class_name + 1)
        user32.GetClassNameW(hwnd, buf, class_name + 1)
        if buf.value == CLASS_NAME:
            return 1
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    maximized = bool(style & WS_MAXIMIZE)
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    wins = lParam
    wins.append(WindowInfo(
        rect=Rect(r.left, r.top, r.right, r.bottom),
        maximized=maximized,
    ))
    return 1


def get_windows() -> list[WindowInfo]:
    """Visible, non-tool, non-cloaked top-level windows (excluding our own overlays)."""
    wins: list[WindowInfo] = []
    cb = WNDENUMPROC(_window_enum_callback)
    user32.EnumWindows(cb, ctypes.py_object(wins))
    return wins


# --- Black window + hook state ---
_hwnds: list[wintypes.HWND] = []
_hook = None
_mutex_handle = None
_hinstance = None
_first_hwnd = None


def _wnd_proc(hwnd, msg, wparam, lparam) -> int:
    # Click-through: the window must never receive mouse input. A Python
    # WNDPROC is too slow for high-polling mouse-move floods, and a window
    # thread that is constantly busy makes Windows show the wait (loading)
    # cursor over it. Passing hits through also lets the user keep using
    # what's underneath; Esc (global keyboard hook) still releases it.
    if msg == WM_NCHITTEST:
        return HTTRANSPARENT
    if msg == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


# Module-level reference: Windows holds the raw pointer, Python must keep the
# ctypes callback object alive for the whole run.
_wnd_proc_c = WNDPROC(_wnd_proc)


def _hook_proc(nCode, wParam, lParam) -> int:
    if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
        kb = KBDLLHOOKSTRUCT.from_address(lParam)
        if kb.vkCode == VK_ESCAPE and _first_hwnd:
            user32.PostMessageW(_first_hwnd, WM_CLOSE, 0, 0)
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


_hook_proc_c = HOOKPROC(_hook_proc)


def create_blackout_windows(monitors: list[Monitor]) -> list[int]:
    global _hinstance, _first_hwnd
    # This Windows/user32 build validates RegisterClassW's hInstance as a
    # 32-bit value: NULL and full 64-bit handles are rejected (err 87), while
    # the low 32 bits of the real module base are accepted. We use no icons or
    # resources from the module, so the truncated value is functionally inert.
    _hinstance = int(kernel32.GetModuleHandleW(None)) & 0xFFFFFFFF or 1

    # Register class once
    hbr = gdi32.GetStockObject(BLACK_BRUSH)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.style = 0
    wc.lpfnWndProc = ctypes.cast(_wnd_proc_c, ctypes.c_void_p)
    wc.cbClsExtra = 0
    wc.cbWndExtra = 0
    wc.hInstance = _hinstance
    wc.hIcon = None
    wc.hCursor = None
    wc.hbrBackground = hbr
    wc.lpszMenuName = None
    wc.lpszClassName = CLASS_NAME
    wc.hIconSm = None
    user32.RegisterClassW(ctypes.byref(wc))

    for mon in monitors:
        w = mon.rect.right - mon.rect.left
        h = mon.rect.bottom - mon.rect.top
        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            CLASS_NAME,
            "Blackout",
            WS_POPUP | WS_VISIBLE,
            mon.rect.left, mon.rect.top, w, h,
            None, None, _hinstance, None,
        )
        _hwnds.append(hwnd)
        if _first_hwnd is None:
            _first_hwnd = hwnd
    return [int(h) for h in _hwnds]


def main() -> int:
    global _hook, _mutex_handle
    # DPI awareness first
    user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)

    # Single-instance toggle
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        hwnd = user32.FindWindowW(CLASS_NAME, None)
        if hwnd:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        kernel32.CloseHandle(_mutex_handle)
        print("Already running \u2014 released.")
        return 0

    free = find_free_monitors(get_monitors(), get_windows())
    if not free:
        print("All monitors already fullscreen \u2014 nothing to black out.")
        return 0

    create_blackout_windows(free)
    print(f"Blacked out {len(free)} monitor(s). Press Esc (or run again) to release.")

    _hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook_proc_c, 0, 0)
    msg = wintypes.MSG()
    while True:
        rc = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if rc in (0, -1):
            break
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    if _hook:
        user32.UnhookWindowsHookEx(_hook)
    for h in list(_hwnds):
        user32.DestroyWindow(h)
    if _mutex_handle:
        kernel32.CloseHandle(_mutex_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
