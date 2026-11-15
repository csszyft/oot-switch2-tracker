"""Always-on-top Floating HUD for OoT (NX2navi / Fritchii / Hookshot) progress & missables."""
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import winsound

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amiibo_helper import get_nfc_state, load_amiibo_in_emulator, load_daily_used, mark_daily_used, scan_amiibo_cards
from gamepad_ctrl import GamepadSnapshot, UniversalGamepadPoller
from portable_config import APP_DIR, BUNDLE_DIR, load_config
from save_reader import UnifiedStateReader
from tracker_engine import TrackerAlert, TrackerEngine
from win_proc import get_process_name

try:
    from auto_updater import check_and_apply_updates, load_local_manifest
except Exception:
    check_and_apply_updates = None
    load_local_manifest = None
try:
    from triforce_icon import apply_win32_triforce_icon, render_triforce_bgra
except Exception:
    apply_win32_triforce_icon = None
    render_triforce_bgra = None

_ext_db = APP_DIR / "oot_world_db.json"
DB_PATH = _ext_db if _ext_db.is_file() else (BUNDLE_DIR / "oot_world_db.json")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
except Exception:
    _dwmapi = None
try:
    # Ensure physical pixel parity across Windows DPI scaling (125%/150%) regardless of launcher manifest
    _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
_GA_ROOT = 2
_MONITOR_DEFAULTTONEAREST = 2
_GWLP_WNDPROC = -4
_GWL_STYLE = -16
_GWL_EXSTYLE = -20
_WS_MINIMIZEBOX = 0x00020000
_WS_THICKFRAME = 0x00040000
_WS_SYSMENU = 0x00080000
_WS_CAPTION = 0x00C00000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TOPMOST = 0x00000008
_WS_EX_APPWINDOW = 0x00040000
_WS_EX_LAYERED = 0x00080000
_WS_EX_NOACTIVATE = 0x08000000
_WM_MOUSEACTIVATE = 0x0021
_WM_NCCALCSIZE = 0x0083
_MA_NOACTIVATE = 3
_GW_HWNDPREV = 3
_RDW_INVALIDATE = 0x0001
_RDW_ALLCHILDREN = 0x0080
_RDW_UPDATENOW = 0x0100
_HWND_TOPMOST = ctypes.c_void_p(-1)
_HWND_NOTOPMOST = ctypes.c_void_p(-2)
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_SWP_SHOWWINDOW = 0x0040
_SW_HIDE = 0
_SW_SHOWNOACTIVATE = 4
_SW_MINIMIZE = 6
_SW_RESTORE = 9
_DWMWA_CLOAKED = 14
_SELF_PID = os.getpid()
_IGNORE_FS_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "XamlExplorerHostIslandWindow"}
_MAGPIE_FS_CLASSES = {
    "Window_Magpie_967EB565-6F73-4E94-AE53-00CC42592A22",
    "Magpie_967EB565-6F73-4E94-AE53-00CC42592A22",
}
_GAME_FS_CLASSES = {
    "NX2naviRecompWindow",
    "Qt662QWindowIcon",
    "Qt672QWindowIcon",
    "Qt682QWindowIcon",
    *_MAGPIE_FS_CLASSES,
}
_GAME_PROC_NAMES = {
    "ocarina.exe",
    "lichii.exe",
    "hookshot.exe",
    "yuzu.exe",
    "eden.exe",
    "citron.exe",
    "ryujinx.exe",
    "suyu.exe",
    "magpie.exe",
}


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsZoomed.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
_user32.SetWindowLongPtrW.restype = ctypes.c_void_p
_user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallWindowProcW.restype = ctypes.c_ssize_t
_WNDPROC_TYPE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
_user32.RedrawWindow.restype = wintypes.BOOL
_user32.DestroyIcon.argtypes = [wintypes.HICON]
_user32.DestroyIcon.restype = wintypes.BOOL
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL


def _get_top_hwnd(widget: tk.Misc | None) -> int:
    if widget is None:
        return 0
    try:
        hwnd = int(widget.winfo_id())
        top = _user32.GetAncestor(hwnd, _GA_ROOT)
        return int(top or hwnd)
    except Exception:
        return 0


def _is_win_visible(widget: tk.Misc | None) -> bool:
    hwnd = _get_top_hwnd(widget)
    return bool(hwnd and _user32.IsWindowVisible(hwnd) and not _user32.IsIconic(hwnd))


def _hide_win_noactivate(widget: tk.Misc | None):
    """Hide window at Win32 level (SW_HIDE) while keeping Tk wm state 'normal' so child widgets stay mapped."""
    hwnd = _get_top_hwnd(widget)
    if hwnd and _user32.IsWindowVisible(hwnd):
        try:
            _user32.ShowWindow(hwnd, _SW_HIDE)
        except Exception:
            pass


def _make_noactivate_root(win: tk.Misc):
    """Configure borderless HUD root with real taskbar icon (WS_EX_APPWINDOW without WS_EX_NOACTIVATE) + minimize box."""
    try:
        win.update_idletasks()
        hwnd = _get_top_hwnd(win)
        if hwnd:
            st = _user32.GetWindowLongW(hwnd, _GWL_STYLE)
            _user32.SetWindowLongW(
                hwnd,
                _GWL_STYLE,
                (st & ~_WS_CAPTION & ~_WS_THICKFRAME) | _WS_MINIMIZEBOX | _WS_SYSMENU,
            )
            ex = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            _user32.SetWindowLongW(
                hwnd,
                _GWL_EXSTYLE,
                ((ex & ~_WS_EX_TOOLWINDOW & ~_WS_EX_NOACTIVATE & ~_WS_EX_TRANSPARENT) | _WS_EX_LAYERED | _WS_EX_APPWINDOW),
            )
            _user32.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
            )
    except Exception:
        pass


def _make_triforce_icon(win: tk.Tk, size: int = 32) -> tk.PhotoImage:
    """Create a procedural golden Triforce PhotoImage (zero external .ico dependency)."""
    img = tk.PhotoImage(master=win, width=size, height=size)
    if render_triforce_bgra is not None:
        bgra = render_triforce_bgra(size)
        stride = size * 4
        rows = []
        for y in range(size):
            row = bgra[y * stride : (y + 1) * stride]
            cols = []
            for x in range(0, stride, 4):
                a = row[x + 3] / 255.0
                r = int(round(row[x + 2] * a + 13 * (1.0 - a)))
                g = int(round(row[x + 1] * a + 18 * (1.0 - a)))
                b = int(round(row[x] * a + 24 * (1.0 - a)))
                cols.append(f"#{r:02x}{g:02x}{b:02x}")
            rows.append("{" + " ".join(cols) + "}")
        img.put(" ".join(rows))
        return img
    img.put("#0E131D", to=(0, 0, size, size))
    return img


def _set_win_rect(win: tk.Misc, x: int | None = None, y: int | None = None,
                  w: int | None = None, h: int | None = None,
                  topmost: bool | None = None, show: bool = False):
    try:
        hwnd = _get_top_hwnd(win)
        if not hwnd:
            return
        flags = _SWP_NOACTIVATE
        if x is None or y is None:
            flags |= _SWP_NOMOVE
        if w is None or h is None:
            flags |= _SWP_NOSIZE
        if topmost is None:
            flags |= _SWP_NOZORDER
            z = None
        else:
            z = _HWND_TOPMOST if topmost else _HWND_NOTOPMOST
        if show:
            flags |= _SWP_SHOWWINDOW
        _user32.SetWindowPos(hwnd, z, int(x or 0), int(y or 0), int(w or 0), int(h or 0), flags)
    except Exception:
        pass


def _install_borderless_taskbar(win: tk.Tk) -> tuple[int, int | None, object]:
    """Keep borderless dark HUD in Windows Taskbar while returning MA_NOACTIVATE on mouse clicks."""
    _make_noactivate_root(win)
    hwnd = _get_top_hwnd(win)
    if not hwnd:
        return 0, None, None
    old_holder: list[int | None] = [None]

    def _wndproc(h, msg, wp, lp):
        if msg == _WM_MOUSEACTIVATE:
            return _MA_NOACTIVATE
        if msg == _WM_NCCALCSIZE:
            return 0
        old_p = old_holder[0]
        if old_p:
            return _user32.CallWindowProcW(old_p, h, msg, wp, lp)
        return 0

    cb = _WNDPROC_TYPE(_wndproc)
    old_ptr = _user32.SetWindowLongPtrW(hwnd, _GWLP_WNDPROC, cb)
    old_holder[0] = old_ptr
    _user32.SetWindowPos(
        hwnd, None, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
    )
    return hwnd, old_ptr, cb


def _make_clickthrough_noactivate(win: tk.Misc):
    try:
        win.update_idletasks()
        hwnd = _get_top_hwnd(win)
        if hwnd:
            ex = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            _user32.SetWindowLongW(
                hwnd,
                _GWL_EXSTYLE,
                ex | _WS_EX_LAYERED | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW | _WS_EX_TRANSPARENT,
            )
    except Exception:
        pass


def _is_window_cloaked(hwnd: int) -> bool:
    if not _dwmapi:
        return False
    try:
        cloaked = ctypes.c_int(0)
        hr = _dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return hr == 0 and cloaked.value != 0
    except Exception:
        return False


def _is_game_hwnd(hwnd: int, cls_name: str, pid_val: int) -> bool:
    if cls_name in _GAME_FS_CLASSES:
        return True
    if not pid_val:
        return False
    try:
        return get_process_name(pid_val) in _GAME_PROC_NAMES
    except Exception:
        return False


def _flush_paint(win: tk.Misc | None):
    """Synchronously flush Tk geometry & Win32 WM_PAINT for an offscreen/back-buffer window before swapping."""
    if win is None:
        return
    try:
        win.update_idletasks()
        hwnd = _get_top_hwnd(win)
        if hwnd:
            _user32.RedrawWindow(hwnd, None, None, _RDW_INVALIDATE | _RDW_ALLCHILDREN | _RDW_UPDATENOW)
    except Exception:
        pass


def _has_game_window_above(hwnd: int) -> bool:
    """Return True if any large, overlapping game/fullscreen window sits above hwnd in Z-order."""
    try:
        r_self = wintypes.RECT()
        has_self_rect = bool(_user32.GetWindowRect(hwnd, ctypes.byref(r_self)))
        cur = _user32.GetWindow(hwnd, _GW_HWNDPREV)
        cls_b = ctypes.create_unicode_buffer(128)
        wpid = wintypes.DWORD(0)
        r_cur = wintypes.RECT()
        steps = 0
        while cur and steps < 64:
            steps += 1
            c_int = int(cur)
            if _user32.IsWindowVisible(c_int) and not _user32.IsIconic(c_int) and not _is_window_cloaked(c_int):
                _user32.GetWindowThreadProcessId(c_int, ctypes.byref(wpid))
                if wpid.value != _SELF_PID:
                    _user32.GetClassNameW(c_int, cls_b, 128)
                    if _is_game_hwnd(c_int, cls_b.value, wpid.value) and _user32.GetWindowRect(c_int, ctypes.byref(r_cur)):
                        cw = r_cur.right - r_cur.left
                        ch = r_cur.bottom - r_cur.top
                        if cw >= 600 and ch >= 400:
                            if not has_self_rect or (
                                r_cur.left < r_self.right
                                and r_cur.right > r_self.left
                                and r_cur.top < r_self.bottom
                                and r_cur.bottom > r_self.top
                            ):
                                return True
            cur = _user32.GetWindow(cur, _GW_HWNDPREV)
    except Exception:
        pass
    return False


def _show_noactivate(
    win: tk.Misc, x: int, y: int, w: int, h: int, clickthrough: bool = True, insert_after: int | object = _HWND_TOPMOST
):
    """Position and show a pre-mapped Tk window at insert_after with SWP_NOACTIVATE (zero focus steal, instant paint)."""
    try:
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.update_idletasks()
        hwnd = _get_top_hwnd(win)
        if hwnd:
            ex = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            target_ex = ex | _WS_EX_LAYERED | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW
            if clickthrough:
                target_ex |= _WS_EX_TRANSPARENT
            else:
                target_ex &= ~_WS_EX_TRANSPARENT
            if target_ex != ex:
                _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, target_ex)
            z_after = ctypes.c_void_p(insert_after) if isinstance(insert_after, int) and insert_after > 0 else _HWND_TOPMOST
            _user32.SetWindowPos(
                hwnd, z_after, x, y, w, h, _SWP_NOACTIVATE | _SWP_SHOWWINDOW
            )
    except Exception:
        pass


def _ensure_topmost_noactivate(win: tk.Misc | None, clickthrough: bool = True, tool_window: bool = True):
    if win is None:
        return
    try:
        hwnd = _get_top_hwnd(win)
        if hwnd and _user32.IsWindowVisible(hwnd) and not _user32.IsIconic(hwnd):
            ex = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            target_ex = ex | _WS_EX_LAYERED
            if tool_window:
                target_ex = (target_ex | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE) & ~_WS_EX_APPWINDOW
            else:
                target_ex = (target_ex | _WS_EX_APPWINDOW) & ~_WS_EX_TOOLWINDOW & ~_WS_EX_NOACTIVATE
            if clickthrough:
                target_ex |= _WS_EX_TRANSPARENT
            else:
                target_ex &= ~_WS_EX_TRANSPARENT
            if target_ex != ex:
                _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, target_ex)
            if not (ex & _WS_EX_TOPMOST) or _has_game_window_above(hwnd):
                _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)
    except Exception:
        pass


def _check_hwnd_fullscreen(hwnd: int) -> tuple[bool, tuple[int, int, int, int] | None]:
    if not hwnd or not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd) or _is_window_cloaked(hwnd):
        return False, None
    cls_buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, cls_buf, 256)
    if cls_buf.value in _IGNORE_FS_CLASSES:
        return False, None
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False, None
    if (rect.right - rect.left) < 640 or (rect.bottom - rect.top) < 480:
        return False, None
    mon = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    if not mon:
        return False, None
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if not _user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return False, None
    m = mi.rcMonitor
    is_mon_fs = (
        rect.left <= m.left + 2
        and rect.top <= m.top + 2
        and rect.right >= m.right - 2
        and rect.bottom >= m.bottom - 2
    )
    if is_mon_fs:
        return True, (m.left, m.top, m.right, m.bottom)

    # Also treat maximized / borderless-workarea game windows (e.g. NX2navi 1920x991 maximized) as fullscreen-HUD mode
    wpid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
    if _is_game_hwnd(hwnd, cls_buf.value, wpid.value):
        w = mi.rcWork
        is_zoomed = bool(_user32.IsZoomed(hwnd))
        covers_work = (
            rect.left <= w.left + 8
            and rect.top <= w.top + 8
            and rect.right >= w.right - 8
            and rect.bottom >= w.bottom - 8
        )
        if is_zoomed or covers_work:
            return True, (w.left, w.top, w.right, w.bottom)
    return False, None


def detect_fullscreen_monitor(ignore_hwnds: set[int] | None = None) -> tuple[bool, tuple[int, int, int, int] | None]:
    """Return (is_fullscreen, (left, top, right, bottom)) if Magpie scaling or the active game/app is fullscreen."""
    try:
        # 1. Check Magpie fullscreen scaling window first (Magpie uses WS_EX_NOACTIVATE, so GetForegroundWindow()
        #    remains the windowed source game even while Magpie's fullscreen scaling window covers the screen).
        for magpie_cls in _MAGPIE_FS_CLASSES:
            m_hwnd = int(_user32.FindWindowW(magpie_cls, None) or 0)
            if m_hwnd and (not ignore_hwnds or m_hwnd not in ignore_hwnds):
                is_m_fs, m_rect = _check_hwnd_fullscreen(m_hwnd)
                if is_m_fs:
                    return True, m_rect

        # 2. Check foreground window directly if it is not our own HUD window
        fg = _user32.GetForegroundWindow()
        is_our_own = False
        if fg:
            root_hwnd = int(_user32.GetAncestor(fg, _GA_ROOT) or fg)
            wpid = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(wpid))
            is_our_own = (wpid.value == _SELF_PID) or bool(ignore_hwnds and root_hwnd in ignore_hwnds)
            if not is_our_own:
                is_fg_fs, fg_rect = _check_hwnd_fullscreen(root_hwnd)
                if is_fg_fs:
                    return True, fg_rect

        # 3. Foreground is our own HUD/Toplevel, transiently null (F11 transition), or a floating overlay/FPS bar:
        #    scan top-to-bottom ignoring small/transparent/noactivate overlays until hitting fullscreen game or real desktop window.
        fs_result: tuple[bool, tuple[int, int, int, int] | None] = (False, None)

        @_WNDENUMPROC
        def _enum_cb(hwnd, _lp):
            nonlocal fs_result
            h_int = int(hwnd)
            if ignore_hwnds and h_int in ignore_hwnds:
                return True
            if not _user32.IsWindowVisible(h_int) or _user32.IsIconic(h_int) or _is_window_cloaked(h_int):
                return True
            pid_c = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(h_int, ctypes.byref(pid_c))
            if pid_c.value == _SELF_PID:
                return True
            cls_b = ctypes.create_unicode_buffer(128)
            _user32.GetClassNameW(h_int, cls_b, 128)
            if cls_b.value in _IGNORE_FS_CLASSES or cls_b.value in ("IME", "MSCTFIME UI", "tooltips_class32", "SysShadow"):
                return True
            r = wintypes.RECT()
            if not _user32.GetWindowRect(h_int, ctypes.byref(r)):
                return True
            rw = r.right - r.left
            rh = r.bottom - r.top
            if rw < 200 or rh < 150:
                return True
            is_fs_w, m_rect_w = _check_hwnd_fullscreen(h_int)
            if is_fs_w:
                fs_result = (True, m_rect_w)
                return False
            ex = _user32.GetWindowLongW(h_int, _GWL_EXSTYLE)
            if (ex & (_WS_EX_TOOLWINDOW | _WS_EX_TRANSPARENT | _WS_EX_NOACTIVATE)) or rw < 600 or rh < 400:
                return True
            # Real large desktop application sitting above any fullscreen window
            if not _is_game_hwnd(h_int, cls_b.value, pid_c.value):
                return False
            return True

        _user32.EnumWindows(_enum_cb, 0)
        return fs_result
    except Exception:
        return False, None

# Switch 2 OoT Remake Native HUD Palette (Hylian Obsidian + Antique Gold + Navi Cyan)
BG = "#0D1218"
BG_CARD = "#151C25"
BG_HEADER = "#111720"
BG_ROW = "#1B2330"
BG_BOSS = "#26161B"
BG_FINAL = "#160F29"
BG_FINAL_HDR = "#2C184D"
BG_FINAL_GANON = "#220E2D"
BG_FINAL_GANON_HDR = "#3B1344"
BG_VICTORY = "#12242C"
BG_VICTORY_HDR = "#1B3B48"
BORDER = "#7E6536"
BORDER_GOLD = "#D8B467"
BORDER_FINAL_GOLD = "#FFD86B"
FG = "#F4EFE4"
FG_DIM = "#9AA5B4"
ACCENT_BLUE = "#5CC8FF"     # 娜薇提示青
NAVI_CYAN = "#66E8FF"       # 娜薇妖精光青
ACCENT_GREEN = "#4ED88A"    # 科奇里翡翠绿
ACCENT_AMBER = "#F2C968"    # 三角神力金
ACCENT_RED = "#EB4756"      # 红心 / 强敌绯红
ACCENT_PURPLE = "#B48EFF"   # 希卡紫


class OoTOverlayHUD:
    def __init__(self, save_dir: Path | str | None = None, slot: int | str | None = None, auto_update: bool = True):
        self._cfg = load_config()
        eff_save_dir = save_dir if save_dir is not None else (self._cfg.get("save_dir") or None)
        eff_slot = slot if slot is not None else self._cfg.get("slot", "auto")
        self.db = json.loads(DB_PATH.read_text(encoding="utf-8"))
        self.reader = UnifiedStateReader(self.db, save_dir=eff_save_dir, slot=eff_slot)
        self.engine = TrackerEngine(self.db)
        self.gamepad = UniversalGamepadPoller()

        try:
            ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID("CSSZYF.OoTSwitch2Tracker.1")
        except Exception:
            pass
        self._app_version = (
            str(load_local_manifest(APP_DIR).get("version") or "1.2.0")
            if load_local_manifest is not None
            else "1.2.0"
        )
        self._update_busy = False
        self._auto_update_enabled = bool(auto_update)
        self.root = tk.Tk()
        self.root.title(f"塞尔达传说 时之笛 · 全程查漏与攻略助手 v{self._app_version}")
        self.root.configure(bg=BG)
        self.root.withdraw()
        self._icon_img = None
        self._hicons: list[int] = []
        self._wndproc_hwnd = 0
        self._wndproc_old = None
        self._wndproc_cb = None
        self.topmost = True
        self.alphas = [0.96, 0.86, 1.0]
        self.alpha_idx = 0
        self.root.attributes("-alpha", self.alphas[self.alpha_idx])

        self.compact = False
        self._expanded_height = 640
        self._user_minimized = False
        self.sound_enabled = tk.BooleanVar(value=bool(self._cfg.get("sound_enabled", True)))
        # fs_mode: "distributed" (全屏分布式UI) | "toast_only" (全屏仅拿取弹窗) | "off" (关闭全屏隐藏)
        init_fs = str(self._cfg.get("fs_mode", "distributed") or "distributed")
        if init_fs not in ("distributed", "toast_only", "off"):
            init_fs = "distributed"
        self.fs_mode = tk.StringVar(value=init_fs)
        self.fs_hidden = False
        self.fs_manual_peek = False
        self.dist_rail_mode = "auto"  # "auto" | "story" | "boss" | "amiibo"
        self.amiibo_cards = scan_amiibo_cards()
        self.amiibo_used_today = load_daily_used()
        self.amiibo_idx = self._find_next_unused_amiibo(0)
        self._last_amiibo_scan = time.monotonic()
        self.amiibo_scanning = False
        self._tab_before_amiibo = "region"
        self._amiibo_busy = False
        self._prev_boss_id: str | None = None
        self._prev_boss_name: str | None = None
        self._prev_final_stage: str | None = None
        self._saved_geometry: str | None = None
        self._fs_monitor_rect: tuple[int, int, int, int] | None = None
        self._dist_pill_win: tk.Toplevel | None = None
        self._dist_pill_inner: tk.Frame | None = None
        self._dist_pill_main_lbl: tk.Label | None = None
        self._dist_pill_status_lbl: tk.Label | None = None
        self._dist_pill_red_lbl: tk.Label | None = None
        self._dist_rail_win: tk.Toplevel | None = None
        self._dist_rail_body: tk.Frame | None = None
        self._dist_rail_back_win: tk.Toplevel | None = None
        self._dist_rail_back_body: tk.Frame | None = None
        self._dist_right_win: tk.Toplevel | None = None
        self._dist_right_body: tk.Frame | None = None
        self._dist_right_back_win: tk.Toplevel | None = None
        self._dist_right_back_body: tk.Frame | None = None
        self._dist_last_key = None
        self._dist_last_dist_key = None
        self._pill_last_key = None
        self._pill_last_rect: tuple[int, int, int, int] | None = None
        self._rail_last_rect: tuple[int, int, int, int] | None = None
        self._right_last_key = None
        self._right_last_rect: tuple[int, int, int, int] | None = None
        self._rail_nearby_slots: list[tuple[tk.Label, tk.Label | None, str]] = []
        self._fs_miss_streak: int = 0
        self._banner_hold_until: float = 0.0
        self._toast_win: tk.Toplevel | None = None
        self._toast_card: tk.Frame | None = None
        self._toast_head_lbl: tk.Label | None = None
        self._toast_sub_lbl: tk.Label | None = None
        self._toast_after_id: str | None = None
        self.selected_loc_var = tk.StringVar(value="AUTO")
        self.active_tab = "region"  # region | quests | boss
        self.alert_history: list[tuple[str, TrackerAlert]] = []
        self.last_eval = None
        self.last_render_key = None
        self._show_completed_quests: bool = False
        self._show_defeated_bosses: bool = False

        self._drag_x = 0
        self._drag_y = 0
        # 120Hz zero-overshoot smooth-scroll & flick state
        self._wheel_rem_px: float = 0.0   # Exact target-offset remainder for mousewheel/keyboard (never overshoots!)
        self._scroll_vel: float = 0.0     # Intentional fast-flick momentum (cut cleanly at 2.5px/frame, zero tail creep)
        self._scroll_rem: float = 0.0
        self._touch_was_scrolling: bool = False
        self._view_dragging: bool = False
        self._view_drag_last_y: int = 0
        self._view_drag_last_ts: float = 0.0
        self._view_drag_vy: float = 0.0
        self._dpad_hold_frames: int = 0
        self._last_pad_label_state: tuple[bool, str] | None = None
        self._last_banner_key: tuple | None = None
        self._last_desktop_theme_key: tuple | None = None
        self._last_desktop_hdr_key: tuple | None = None

        # Dedicated background game-state & NFC worker so UI thread NEVER blocks on disk/RAM I/O
        self._bg_stop: bool = False
        self._bg_lock = threading.Lock()
        self._bg_pending: tuple[dict | None, int | None] | None = None
        self._bg_ever_received: bool = False

        fg_before_init = int(_user32.GetForegroundWindow() or 0)
        self._build_ui()
        self._init_overlay_windows()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.update_idletasks()
        self._wndproc_hwnd, self._wndproc_old, self._wndproc_cb = _install_borderless_taskbar(self.root)
        if apply_win32_triforce_icon is not None:
            self._hicons = apply_win32_triforce_icon(self._wndproc_hwnd)
        if not self._hicons:
            try:
                self._icon_img = _make_triforce_icon(self.root)
                self.root.iconphoto(True, self._icon_img)
            except Exception:
                self._icon_img = None
        self.root.deiconify()
        self.root.update()
        _set_win_rect(self.root, 30, 40, 468, 640, topmost=self.topmost, show=True)
        self.root.attributes("-topmost", True)
        self.root.update()
        self._saved_rect = (30, 40, 468, 640)
        for ov_win in (
            self._dist_pill_win,
            self._dist_rail_win,
            self._dist_rail_back_win,
            self._dist_right_win,
            self._dist_right_back_win,
            self._toast_win,
        ):
            if ov_win is not None:
                _make_clickthrough_noactivate(ov_win)
                _hide_win_noactivate(ov_win)
        if fg_before_init and _user32.IsWindowVisible(fg_before_init):
            try:
                _user32.SetForegroundWindow(fg_before_init)
            except Exception:
                pass
        self._saved_geometry = "468x640+30+40"
        # Prime initial state synchronously once at startup so window opens immediately populated
        try:
            init_st = self.reader.read()
            init_nfc = get_nfc_state()
            init_ev = self.engine.evaluate(init_st) if init_st else None
            with self._bg_lock:
                self._bg_pending = (init_ev, init_nfc)
            if not init_ev:
                self._render_waiting_guide()
        except Exception:
            pass
        self._bg_thread = threading.Thread(target=self._bg_state_loop, daemon=True)
        self._bg_thread.start()
        self._poll()
        self._poll_gamepad()
        if self._auto_update_enabled and bool(self._cfg.get("auto_update", True)) and check_and_apply_updates is not None:
            self.root.after(450, lambda: self._check_updates_async(silent=True))

    def _bg_state_loop(self):
        """Background worker: reads save/RAM + NFC + evaluates 175 items off the UI thread."""
        while not self._bg_stop:
            t0 = time.monotonic()
            try:
                st = self.reader.read()
                nfc_st = get_nfc_state()
                ev = self.engine.evaluate(st) if st else None
                with self._bg_lock:
                    self._bg_pending = (ev, nfc_st)
            except Exception:
                pass
            elapsed = time.monotonic() - t0
            time.sleep(max(0.08, 0.30 - elapsed))

    def _on_close(self):
        self._bg_stop = True
        try:
            self._hide_fs_toast()
            self._destroy_distributed_hud()
            self.reader.mem_reader.close()
            self.gamepad.close()
            if self._wndproc_hwnd and self._wndproc_old:
                _user32.SetWindowLongPtrW(self._wndproc_hwnd, _GWLP_WNDPROC, self._wndproc_old)
                self._wndproc_old = None
            for hi in getattr(self, "_hicons", ()):
                if hi:
                    _user32.DestroyIcon(hi)
            self._hicons = []
        except Exception:
            pass
        self.root.destroy()

    def _init_overlay_windows(self):
        """Pre-create fullscreen distributed HUD & toast Toplevels once at startup.
        Keeping Tk wm state 'normal' and toggling visibility via Win32 ShowWindow(SW_HIDE)/SetWindowPos(SWP_NOACTIVATE)
        guarantees 100% mapped child widgets and zero focus steal from ocarina.exe or Magpie fullscreen scaling.
        """
        pw = tk.Toplevel(self.root)
        pw.geometry("1x1+-10000+-10000")
        pw.overrideredirect(True)
        pw.configure(bg=BORDER)
        pw.attributes("-topmost", True)
        pw.attributes("-alpha", 0.86)
        inner = tk.Frame(pw, bg=BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        m_lbl = tk.Label(inner, text="", bg=BG, fg=FG, font=("Microsoft YaHei UI", 8, "bold"), padx=0, pady=4)
        m_lbl.pack(side=tk.LEFT, padx=(8, 0))
        s_lbl = tk.Label(inner, text="", bg=BG, fg=ACCENT_GREEN, font=("Microsoft YaHei UI", 8, "bold"), padx=0, pady=4)
        s_lbl.pack(side=tk.LEFT, padx=(0, 8))
        r_lbl = tk.Label(inner, text="", bg=BG, fg=ACCENT_RED, font=("Microsoft YaHei UI", 8, "bold"), padx=0, pady=4)
        self._dist_pill_win = pw
        self._dist_pill_inner = inner
        self._dist_pill_main_lbl = m_lbl
        self._dist_pill_status_lbl = s_lbl
        self._dist_pill_red_lbl = r_lbl

        def _make_rail_win(border_col: str, alpha: float) -> tuple[tk.Toplevel, tk.Frame]:
            w = tk.Toplevel(self.root)
            w.geometry("1x1+-10000+-10000")
            w.overrideredirect(True)
            w.configure(bg=border_col)
            w.attributes("-topmost", True)
            w.attributes("-alpha", alpha)
            body = tk.Frame(w, bg=BG)
            body.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
            return w, body

        self._dist_rail_win, self._dist_rail_body = _make_rail_win(BORDER_GOLD, 0.78)
        self._dist_rail_back_win, self._dist_rail_back_body = _make_rail_win(BORDER_GOLD, 0.78)
        self._dist_right_win, self._dist_right_body = _make_rail_win(BORDER, 0.78)
        self._dist_right_back_win, self._dist_right_back_body = _make_rail_win(BORDER, 0.78)

        tw = tk.Toplevel(self.root)
        tw.geometry("1x1+-10000+-10000")
        tw.overrideredirect(True)
        tw.configure(bg=BG)
        tw.attributes("-topmost", True)
        tw.attributes("-alpha", 0.90)
        tcard = tk.Frame(tw, bg=BG_CARD, highlightbackground=ACCENT_GREEN, highlightthickness=1)
        tcard.pack(fill=tk.BOTH, expand=True)
        thead = tk.Label(
            tcard, text="", bg=BG_CARD, fg=ACCENT_GREEN,
            font=("Microsoft YaHei UI", 9, "bold"), anchor="w", justify=tk.LEFT, wraplength=400
        )
        thead.pack(fill=tk.X, padx=10, pady=(6, 2))
        tsub = tk.Label(
            tcard, text="", bg=BG_CARD, fg=FG,
            font=("Microsoft YaHei UI", 8), anchor="w", justify=tk.LEFT, wraplength=400
        )
        tsub.pack(fill=tk.X, padx=10, pady=(0, 7))
        self._toast_win = tw
        self._toast_card = tcard
        self._toast_head_lbl = thead
        self._toast_sub_lbl = tsub

    def _capture_win_rect(self) -> tuple[int, int, int, int] | None:
        hwnd = _get_top_hwnd(self.root)
        if not hwnd or not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
            return None
        r = wintypes.RECT()
        if _user32.GetWindowRect(hwnd, ctypes.byref(r)):
            w, h = r.right - r.left, r.bottom - r.top
            if w >= 200 and h >= 80:
                return (r.left, r.top, w, h)
        return None

    def _show_root_noactivate(self):
        """Restore self.root cleanly on taskbar + desktop without stealing game focus."""
        try:
            hwnd = _get_top_hwnd(self.root)
            if hwnd and _user32.IsIconic(hwnd):
                _user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)
            if self.root.state() == "withdrawn":
                self.root.deiconify()
            self.root.update_idletasks()
            _make_noactivate_root(self.root)
            rect = getattr(self, "_saved_rect", None)
            if rect:
                _set_win_rect(self.root, rect[0], rect[1], rect[2], rect[3], topmost=self.topmost, show=True)
            else:
                _set_win_rect(self.root, topmost=self.topmost, show=True)
        except Exception:
            pass

    def _minimize_window(self):
        cur = self._capture_win_rect()
        if cur:
            self._saved_rect = cur
        self._user_minimized = True
        self.root.iconify()

    def _restore_window(self):
        self._user_minimized = False
        self._show_root_noactivate()

    def _open_app_folder(self):
        try:
            subprocess.Popen(["explorer.exe", str(APP_DIR)])
        except Exception:
            pass

    def _restart_after_update(self):
        try:
            extra = ["--no-update"]
            if self._user_minimized:
                extra.append("--minimized")
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, *extra]
            else:
                entry = APP_DIR / "launcher.py"
                cmd = [sys.executable, str(entry if entry.is_file() else Path(__file__).resolve()), *extra]
            clean_env = os.environ.copy()
            for k in list(clean_env.keys()):
                if k.startswith(("_MEI", "_PYI", "PYI_")):
                    clean_env.pop(k, None)
            bundle_s = str(BUNDLE_DIR).lower()
            for tk_var in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH"):
                val = clean_env.get(tk_var, "")
                if val and (bundle_s in val.lower() or "_mei" in val.lower()):
                    clean_env.pop(tk_var, None)
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            subprocess.Popen(
                cmd,
                cwd=str(APP_DIR),
                env=clean_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=True,
            )
        except Exception:
            return
        self._on_close()

    def _check_updates_async(self, silent: bool = False):
        if check_and_apply_updates is None or self._update_busy:
            return
        self._update_busy = True
        if not silent:
            self._show_banner(
                TrackerAlert("info", "🔄 正在检测 GitHub / Gitee 代码更新…", f"当前版本 v{self._app_version}"),
                hold_sec=4.0,
            )

        def _worker():
            res = check_and_apply_updates(APP_DIR, self._cfg, force=False, apply_updates=True)
            try:
                self.root.after(0, lambda: self._on_update_checked(res, silent=silent))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_update_checked(self, res, silent: bool = False):
        self._update_busy = False
        if res.status == "updated":
            src_zh = "Gitee" if res.source == "gitee" else "GitHub"
            kb = max(1, res.total_bytes // 1024)
            notes = f"\n更新内容：{res.notes}" if res.notes else ""
            al = TrackerAlert(
                "good",
                f"✔ 后台已热更新至 v{res.remote_version}（{src_zh} · {len(res.updated_files)} 文件 / {kb} KB）",
                f"即将自动重启加载新版代码…{notes}",
            )
            self._show_banner(al, hold_sec=6.0)
            if self.fs_hidden and self.last_eval:
                self._show_fs_toast([al], self._fs_monitor_rect, self.last_eval)
            self.root.after(1400, self._restart_after_update)
        elif not silent and res.status == "up_to_date":
            src_zh = "Gitee" if res.source == "gitee" else "GitHub"
            self._show_banner(
                TrackerAlert(
                    "good",
                    f"✔ 当前已是最新版本 v{res.local_version}",
                    f"已核对 {src_zh}（{int(res.latency_ms)}ms）｜{' · '.join(res.probe_summary)}",
                ),
                hold_sec=4.5,
            )
        elif not silent and res.status not in ("disabled", "cancelled"):
            self._show_banner(
                TrackerAlert(
                    "warn",
                    f"⚠ 暂未连上 GitHub / Gitee（当前 v{self._app_version}）",
                    " · ".join(res.probe_summary) or res.error or "请检查网络或代理设置",
                ),
                hold_sec=4.5,
            )

    def _build_ui(self):
        # Outer border frame
        self.frame = tk.Frame(self.root, bg=BG, highlightbackground=BORDER, highlightthickness=1)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # 1. Draggable Title Bar
        hdr = tk.Frame(self.frame, bg=BG_HEADER, height=34, cursor="fleur")
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        hdr.bind("<ButtonPress-1>", self._start_drag)
        hdr.bind("<B1-Motion>", self._on_drag)

        btn_cfg = dict(bg=BG_HEADER, fg=FG_DIM, bd=0, relief=tk.FLAT,
                       activebackground=BG_CARD, activeforeground=FG,
                       font=("Microsoft YaHei UI", 9), cursor="hand2", padx=5)
        tk.Button(hdr, text="✕", command=self._on_close, **btn_cfg).pack(side=tk.RIGHT, padx=(0, 4))
        self.btn_min = tk.Button(hdr, text="—", command=self._minimize_window, **btn_cfg)
        self.btn_min.pack(side=tk.RIGHT)
        self.btn_compact = tk.Button(hdr, text="▾", command=self._toggle_compact, **btn_cfg)
        self.btn_compact.pack(side=tk.RIGHT)
        self.btn_alpha = tk.Button(hdr, text="◐", command=self._cycle_alpha, **btn_cfg)
        self.btn_alpha.pack(side=tk.RIGHT)
        self.btn_folder = tk.Button(hdr, text="📁", command=self._open_app_folder, **btn_cfg)
        self.btn_folder.pack(side=tk.RIGHT)
        if check_and_apply_updates is not None:
            self.btn_update = tk.Button(hdr, text="🔄", command=self._check_updates_async, **btn_cfg)
            self.btn_update.pack(side=tk.RIGHT)
        self.btn_pin = tk.Button(hdr, text="📌", command=self._toggle_topmost, **btn_cfg)
        self.btn_pin.config(fg=ACCENT_BLUE if self.topmost else FG_DIM)
        self.btn_pin.pack(side=tk.RIGHT)

        self.lbl_title = tk.Label(
            hdr, text=f"🧭 时之笛进度助手 v{self._app_version}", bg=BG_HEADER, fg=FG,
            font=("Microsoft YaHei UI", 10, "bold"), anchor="w"
        )
        self.lbl_title.pack(side=tk.LEFT, padx=(10, 4))
        self.lbl_title.bind("<ButtonPress-1>", self._start_drag)
        self.lbl_title.bind("<B1-Motion>", self._on_drag)

        self.lbl_source = tk.Label(
            hdr, text="● 连接中", bg=BG_HEADER, fg=FG_DIM,
            font=("Microsoft YaHei UI", 8)
        )
        self.lbl_source.pack(side=tk.LEFT, padx=2)

        # 2. Live Banner (always visible even in compact mode!)
        self.banner = tk.Frame(self.frame, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        self.banner.pack(fill=tk.X, padx=8, pady=(6, 4))
        self.lbl_banner_title = tk.Label(
            self.banner, text="正在扫描存档与游戏状态...", bg=BG_CARD, fg=ACCENT_BLUE,
            font=("Microsoft YaHei UI", 9, "bold"), anchor="w", justify=tk.LEFT, wraplength=430
        )
        self.lbl_banner_title.pack(fill=tk.X, padx=8, pady=(5, 1))
        self.lbl_banner_detail = tk.Label(
            self.banner, text="进入新区域、收集黄金蜘蛛/心之碎片、或离开漏掉可拿物品时自动提示",
            bg=BG_CARD, fg=FG_DIM, font=("Microsoft YaHei UI", 8), anchor="w", justify=tk.LEFT, wraplength=430
        )
        self.lbl_banner_detail.pack(fill=tk.X, padx=8, pady=(0, 6))

        # 3. Global Summary Strip (always visible even in compact mode!)
        self.summary_bar = tk.Frame(self.frame, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        self.summary_bar.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.lbl_global = tk.Label(
            self.summary_bar, text="🕷 --/100   ❤ --/36   🎵 --/12   🧪 --/4",
            bg=BG_CARD, fg=FG, font=("Microsoft YaHei UI", 8, "bold"), pady=5
        )
        self.lbl_global.pack(fill=tk.X, padx=6)

        # 4. Collapsible Body
        self.body = tk.Frame(self.frame, bg=BG)
        self.body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Controls row: Region dropdown + Sound toggle + Tabs
        ctrl = tk.Frame(self.body, bg=BG)
        ctrl.pack(fill=tk.X, pady=(0, 6))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=BG_CARD, background=BG_HEADER, foreground=FG,
            arrowcolor=FG, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", BG_CARD), ("disabled", BG_CARD)],
            foreground=[("readonly", FG), ("disabled", FG_DIM)],
            selectbackground=[("readonly", BG_CARD)],
            selectforeground=[("readonly", FG)],
        )
        self.root.option_add("*TCombobox*Listbox.background", BG_CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#26324B")
        self.root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_BLUE)

        loc_options = ["自动跟随当前位置"] + [f"{self.db['locations'][k]} ({k})" for k in self.db["location_order"] if k not in ("DreamWorld", "IngoRanch")]
        self.cmb_loc = ttk.Combobox(ctrl, values=loc_options, state="readonly", width=16, style="Dark.TCombobox")
        self.cmb_loc.current(0)
        self.cmb_loc.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cmb_loc.bind("<<ComboboxSelected>>", lambda _e: self._refresh_display(force=True))

        fs_options = ["全屏分布式", "全屏仅提示", "全屏不隐藏"]
        self.cmb_fs = ttk.Combobox(ctrl, values=fs_options, state="readonly", width=10, style="Dark.TCombobox")
        fs_idx = {"distributed": 0, "toast_only": 1, "off": 2}.get(self.fs_mode.get(), 0)
        self.cmb_fs.current(fs_idx)
        self.cmb_fs.pack(side=tk.RIGHT, padx=(4, 0))
        self.cmb_fs.bind("<<ComboboxSelected>>", lambda _e: self._on_fs_mode_changed())

        chk = tk.Checkbutton(
            ctrl, text="🔔", variable=self.sound_enabled,
            bg=BG, fg=FG_DIM, selectcolor=BG_CARD, activebackground=BG, activeforeground=FG,
            font=("Microsoft YaHei UI", 8), bd=0
        )
        chk.pack(side=tk.RIGHT, padx=(4, 0))

        # Tab buttons (Amiibo tab stays hidden during normal play; auto-appears ONLY when calling Amiibo in-game!)
        self.tabs_frame = tk.Frame(self.body, bg=BG)
        self.tabs_frame.pack(fill=tk.X, pady=(0, 6))
        self.tab_buttons = {}
        for tid, label in [("region", "本区查漏"), ("quests", "支线/攻略"), ("boss", "Boss/记录"), ("amiibo", "🎁Amiibo")]:
            b = tk.Button(
                self.tabs_frame, text=label, command=lambda t=tid: self._switch_tab(t),
                bg=BG_CARD, fg=FG, bd=0, relief=tk.FLAT,
                font=("Microsoft YaHei UI", 9), pady=4, cursor="hand2"
            )
            if tid != "amiibo":
                b.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.tab_buttons[tid] = b
        self._update_tab_styles()

        # Quick Amiibo Action Bar (shown when on Amiibo tab)
        self.amiibo_bar = tk.Frame(self.body, bg=BG)
        self.btn_load_amiibo = tk.Button(
            self.amiibo_bar, text="🎁 一键载入当前 Amiibo（手柄 L3+○）",
            command=self._trigger_load_amiibo,
            bg="#262015", fg=ACCENT_AMBER, bd=0, relief=tk.FLAT,
            activebackground="#352C1D", activeforeground=FG,
            font=("Microsoft YaHei UI", 8, "bold"), pady=4, cursor="hand2"
        )
        self.btn_load_amiibo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tk.Button(
            self.amiibo_bar, text="▲", command=lambda: self._step_amiibo(-1),
            bg=BG_CARD, fg=FG, bd=0, relief=tk.FLAT, font=("Microsoft YaHei UI", 8), padx=7, pady=4, cursor="hand2"
        ).pack(side=tk.LEFT, padx=1)
        tk.Button(
            self.amiibo_bar, text="▼", command=lambda: self._step_amiibo(1),
            bg=BG_CARD, fg=FG, bd=0, relief=tk.FLAT, font=("Microsoft YaHei UI", 8), padx=7, pady=4, cursor="hand2"
        ).pack(side=tk.LEFT, padx=1)
        tk.Button(
            self.amiibo_bar, text="⏭未刷", command=self._jump_next_unused_amiibo,
            bg=BG_CARD, fg=ACCENT_GREEN, bd=0, relief=tk.FLAT, font=("Microsoft YaHei UI", 8), padx=6, pady=4, cursor="hand2"
        ).pack(side=tk.LEFT, padx=(2, 0))

        # High-speed Rich Text Scrollable View (zero widget lag, instant tab switching)
        scroll_wrap = tk.Frame(self.body, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        scroll_wrap.pack(fill=tk.BOTH, expand=True)

        self.view = tk.Text(
            scroll_wrap, bg=BG_CARD, fg=FG, bd=0, highlightthickness=0,
            wrap=tk.WORD, padx=10, pady=8, spacing1=2, spacing2=1, spacing3=2,
            font=("Microsoft YaHei UI", 9), cursor="arrow",
            state=tk.DISABLED, exportselection=False, takefocus=0,
        )
        self.scrollbar = ttk.Scrollbar(scroll_wrap, orient=tk.VERTICAL, command=self.view.yview)
        self.view.configure(yscrollcommand=self.scrollbar.set)
        self.view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._configure_text_tags()
        self.view.bind("<MouseWheel>", self._on_mousewheel)
        self.view.bind("<ButtonPress-1>", self._on_view_press)
        self.view.bind("<B1-Motion>", self._on_view_drag)
        self.view.bind("<ButtonRelease-1>", self._on_view_release)
        # Instant keyboard shortcuts when HUD window is focused
        self.root.bind("<Up>", lambda _e: self._queue_exact_scroll(-48.0))
        self.root.bind("<Down>", lambda _e: self._queue_exact_scroll(48.0))
        self.root.bind("<Prior>", lambda _e: self._queue_exact_scroll(-260.0))
        self.root.bind("<Next>", lambda _e: self._queue_exact_scroll(260.0))
        self.root.bind("<Home>", lambda _e: self.view.yview_moveto(0.0))
        self.root.bind("<End>", lambda _e: self.view.yview_moveto(1.0))
        self.root.bind("<Left>", lambda _e: self._step_tab_keyboard(-1))
        self.root.bind("<Right>", lambda _e: self._step_tab_keyboard(1))

        # Bottom Gamepad Control Status Strip (PS5 DualSense + Universal)
        self.lbl_gamepad = tk.Label(
            self.body,
            text="🎮 手柄待机（PS5 触控板 / 通用 L3+R3 呼出 · R3+←→切页 · 呼唤Amiibo自动弹出）",
            bg=BG_HEADER, fg=FG_DIM, font=("Microsoft YaHei UI", 7),
            anchor="w", padx=6, pady=3
        )
        self.lbl_gamepad.pack(fill=tk.X, pady=(4, 0))

        # Resize grip in bottom-right
        self.grip = tk.Label(self.frame, text="◢", bg=BG, fg=BORDER_GOLD, font=("Arial", 8), cursor="size_nw_se")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<ButtonPress-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)

    def _configure_text_tags(self):
        v = self.view
        v.tag_configure("hdr_blue", foreground=ACCENT_BLUE, font=("Microsoft YaHei UI", 9, "bold"), spacing1=8, spacing3=3)
        v.tag_configure("hdr_amber", foreground=ACCENT_AMBER, font=("Microsoft YaHei UI", 9, "bold"), spacing1=8, spacing3=3)
        v.tag_configure("hdr_red", foreground=ACCENT_RED, font=("Microsoft YaHei UI", 9, "bold"), spacing1=8, spacing3=3)
        v.tag_configure("hdr_green", foreground=ACCENT_GREEN, font=("Microsoft YaHei UI", 9, "bold"), spacing1=8, spacing3=3)
        v.tag_configure("hdr_purple", foreground=ACCENT_PURPLE, font=("Microsoft YaHei UI", 9, "bold"), spacing1=8, spacing3=3)
        v.tag_configure(
            "hdr_green_toggle",
            foreground=ACCENT_GREEN,
            background="#14261D",
            font=("Microsoft YaHei UI", 9, "bold"),
            lmargin1=6,
            lmargin2=6,
            rmargin=6,
            spacing1=8,
            spacing3=4,
        )

        v.tag_configure("card_bg", background=BG_ROW, lmargin1=6, lmargin2=24, rmargin=6)
        v.tag_configure("story_stage", foreground=ACCENT_AMBER, background="#192330", font=("Microsoft YaHei UI", 8, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=4)
        v.tag_configure("story_title", foreground=FG, background="#192330", font=("Microsoft YaHei UI", 9, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2)
        v.tag_configure("story_route", foreground="#DCE7F5", background="#192330", font=("Microsoft YaHei UI", 8), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2, spacing3=5)

        v.tag_configure("boss_hdr", foreground=ACCENT_RED, background=BG_BOSS, font=("Microsoft YaHei UI", 9, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=4)
        v.tag_configure("boss_item", foreground=ACCENT_AMBER, background=BG_BOSS, font=("Microsoft YaHei UI", 8, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2)
        v.tag_configure("boss_body", foreground=FG, background=BG_BOSS, font=("Microsoft YaHei UI", 8), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2, spacing3=5)

        v.tag_configure("final_hdr", foreground=BORDER_FINAL_GOLD, background=BG_FINAL_HDR, font=("Microsoft YaHei UI", 10, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=5, spacing3=2)
        v.tag_configure("final_navi", foreground=NAVI_CYAN, background=BG_FINAL, font=("Microsoft YaHei UI", 8, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=3, spacing3=2)
        v.tag_configure("final_item", foreground=BORDER_FINAL_GOLD, background=BG_FINAL, font=("Microsoft YaHei UI", 8, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2)
        v.tag_configure("final_body", foreground=FG, background=BG_FINAL, font=("Microsoft YaHei UI", 8), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2, spacing3=5)

        v.tag_configure("victory_hdr", foreground=BORDER_FINAL_GOLD, background=BG_VICTORY_HDR, font=("Microsoft YaHei UI", 10, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=5, spacing3=2)
        v.tag_configure("victory_navi", foreground=NAVI_CYAN, background=BG_VICTORY, font=("Microsoft YaHei UI", 8, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=3, spacing3=2)
        v.tag_configure("victory_body", foreground=FG, background=BG_VICTORY, font=("Microsoft YaHei UI", 8), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2, spacing3=5)

        v.tag_configure("boss_unlock_hdr", foreground=ACCENT_PURPLE, background="#1D1729", font=("Microsoft YaHei UI", 9, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=4)
        v.tag_configure("boss_unlock_item", foreground=ACCENT_AMBER, background="#1D1729", font=("Microsoft YaHei UI", 8, "bold"), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2)
        v.tag_configure("boss_unlock_body", foreground=FG, background="#1D1729", font=("Microsoft YaHei UI", 8), lmargin1=8, lmargin2=14, rmargin=8, spacing1=2, spacing3=5)

        v.tag_configure("badge_red", foreground=ACCENT_RED, background=BG_ROW, font=("Microsoft YaHei UI", 10, "bold"), lmargin1=6, lmargin2=24)
        v.tag_configure("badge_amber", foreground=ACCENT_AMBER, background=BG_ROW, font=("Microsoft YaHei UI", 9, "bold"), lmargin1=6, lmargin2=24)
        v.tag_configure("badge_green", foreground=ACCENT_GREEN, background=BG_ROW, font=("Microsoft YaHei UI", 9, "bold"), lmargin1=6, lmargin2=24)
        v.tag_configure("badge_purple", foreground=ACCENT_PURPLE, background=BG_ROW, font=("Microsoft YaHei UI", 9, "bold"), lmargin1=6, lmargin2=24)
        v.tag_configure("badge_blue", foreground=ACCENT_BLUE, background=BG_ROW, font=("Microsoft YaHei UI", 9, "bold"), lmargin1=6, lmargin2=24)

        v.tag_configure("item_fg", foreground=FG, background=BG_ROW, font=("Microsoft YaHei UI", 9), rmargin=6)
        v.tag_configure("item_dim", foreground=FG_DIM, background=BG_ROW, font=("Microsoft YaHei UI", 9), rmargin=6)
        v.tag_configure("sub_amber", foreground=ACCENT_AMBER, background=BG_ROW, font=("Microsoft YaHei UI", 8, "bold"), lmargin1=24, lmargin2=24, rmargin=6)
        v.tag_configure("sub_red", foreground=ACCENT_RED, background=BG_ROW, font=("Microsoft YaHei UI", 8, "bold"), lmargin1=24, lmargin2=24, rmargin=6)
        v.tag_configure("sub_dim", foreground=FG_DIM, background=BG_ROW, font=("Microsoft YaHei UI", 8), lmargin1=24, lmargin2=24, rmargin=6)
        v.tag_configure("sub_guide", foreground="#C7D7EA", background=BG_ROW, font=("Microsoft YaHei UI", 8), lmargin1=24, lmargin2=24, rmargin=6)
        v.tag_configure("sep", font=("Microsoft YaHei UI", 3))

    def _start_drag(self, e):
        cur = self._capture_win_rect()
        x = cur[0] if cur else self.root.winfo_x()
        y = cur[1] if cur else self.root.winfo_y()
        self._drag_x = e.x_root - x
        self._drag_y = e.y_root - y

    def _on_drag(self, e):
        nx = e.x_root - self._drag_x
        ny = e.y_root - self._drag_y
        _set_win_rect(self.root, x=nx, y=ny)
        cur = self._capture_win_rect()
        if cur:
            self._saved_rect = cur

    def _start_resize(self, e):
        cur = self._capture_win_rect()
        self._rs_w = cur[2] if cur else self.root.winfo_width()
        self._rs_h = cur[3] if cur else self.root.winfo_height()
        self._rs_x = e.x_root
        self._rs_y = e.y_root

    def _on_resize(self, e):
        nw = max(360, self._rs_w + (e.x_root - self._rs_x))
        nh = max(260, self._rs_h + (e.y_root - self._rs_y))
        _set_win_rect(self.root, w=nw, h=nh)
        cur = self._capture_win_rect()
        if cur:
            self._saved_rect = cur
        wrap_w = max(260, nw - 38)
        self.lbl_banner_title.config(wraplength=wrap_w)
        self.lbl_banner_detail.config(wraplength=wrap_w)

    def _scroll_by_pixels(self, dy_px: float):
        """Scroll self.view by sub-pixel accumulated 1-pixel increments (silky 120Hz smooth scroll)."""
        total = dy_px + self._scroll_rem
        step = int(total)
        if step == 0:
            self._scroll_rem = total
            return
        self._scroll_rem = total - step
        try:
            y0, y1 = self.view.yview()
            if (step < 0 and y0 <= 0.0) or (step > 0 and y1 >= 1.0):
                self._scroll_vel = 0.0
                self._wheel_rem_px = 0.0
                self._scroll_rem = 0.0
                return
            self.view.tk.call(self.view._w, "yview", "scroll", step, "pixels")
        except Exception:
            self.view.yview_scroll(1 if step > 0 else -1, "units")

    def _queue_exact_scroll(self, delta_px: float):
        """Add exact target pixel offset (eases out in ~55ms and stops dead on target — zero tail overshoot!)."""
        self._scroll_vel = 0.0
        if (delta_px > 0 and self._wheel_rem_px < 0) or (delta_px < 0 and self._wheel_rem_px > 0):
            self._wheel_rem_px = delta_px
        else:
            self._wheel_rem_px = max(-640.0, min(640.0, self._wheel_rem_px + delta_px))
        return "break"

    def _step_tab_keyboard(self, step: int):
        tab_order = ["region", "quests", "boss"]
        cur = self.active_tab if self.active_tab in tab_order else "region"
        idx = (tab_order.index(cur) + step) % len(tab_order)
        self._switch_tab(tab_order[idx])
        return "break"

    def _on_mousewheel(self, e):
        # Exact target-offset smooth glide (62px per wheel notch, zero extra roll after stopping!)
        notches = -float(e.delta) / 120.0
        return self._queue_exact_scroll(notches * 62.0)

    def _on_view_press(self, e):
        # Touch / mouse drag directly inside self.view (instantly catches coasting inertia)
        self._view_dragging = True
        self._view_press_y = e.y_root
        self._view_drag_last_y = e.y_root
        self._view_drag_last_ts = time.monotonic()
        self._view_drag_vy = 0.0
        self._scroll_vel = 0.0
        self._wheel_rem_px = 0.0
        self._scroll_rem = 0.0

    def _on_view_drag(self, e):
        if not self._view_dragging:
            return
        now = time.monotonic()
        dy = float(self._view_drag_last_y - e.y_root)
        dt = max(0.004, now - self._view_drag_last_ts)
        self._view_drag_last_y = e.y_root
        self._view_drag_last_ts = now
        if abs(dy) > 0.0:
            self._scroll_by_pixels(dy)
            self._view_drag_vy = 0.5 * self._view_drag_vy + 0.5 * (dy / dt)

    def _on_view_release(self, _e):
        if self._view_dragging:
            # Only flick if released while still moving fast (<35ms since last drag motion & speed >= 750 px/s)
            if (time.monotonic() - self._view_drag_last_ts) <= 0.035 and abs(self._view_drag_vy) >= 750.0:
                self._scroll_vel = max(-38.0, min(38.0, self._view_drag_vy * 0.010))
            else:
                self._scroll_vel = 0.0
        self._view_dragging = False

    def _fit_compact_height(self):
        if not self.compact:
            return
        try:
            self.root.update_idletasks()
            cur = self._capture_win_rect()
            cur_w = max(360, cur[2] if cur else (self.root.winfo_width() or 468))
            wrap_w = max(260, cur_w - 38)
            self.lbl_banner_title.config(wraplength=wrap_w)
            self.lbl_banner_detail.config(wraplength=wrap_w)
            self.root.update_idletasks()
            req_h = max(112, self.frame.winfo_reqheight() + 2)
            _set_win_rect(self.root, w=cur_w, h=req_h)
            cur_after = self._capture_win_rect()
            if cur_after:
                self._saved_rect = cur_after
        except Exception:
            pass

    def _toggle_compact(self):
        if not self.compact:
            try:
                cur = self._capture_win_rect()
                cur_h = cur[3] if cur else self.root.winfo_height()
                if cur_h >= 260:
                    self._expanded_height = cur_h
            except Exception:
                pass
            self.compact = True
            self.body.pack_forget()
            if hasattr(self, "grip"):
                self.grip.place_forget()
            self.btn_compact.config(text="▸")
            self._last_banner_key = None
            if self.last_eval and time.monotonic() >= self._banner_hold_until:
                self._show_idle_region_banner(self.last_eval)
            self._fit_compact_height()
        else:
            self.compact = False
            self.body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
            if hasattr(self, "grip"):
                self.grip.place(relx=1.0, rely=1.0, anchor="se")
            self.btn_compact.config(text="▾")
            self._last_banner_key = None
            if self.last_eval and time.monotonic() >= self._banner_hold_until:
                self._show_idle_region_banner(self.last_eval)
            cur = self._capture_win_rect()
            cur_w = max(360, cur[2] if cur else (self.root.winfo_width() or 468))
            exp_h = max(460, getattr(self, "_expanded_height", 640))
            wrap_w = max(260, cur_w - 38)
            self.lbl_banner_title.config(wraplength=wrap_w)
            self.lbl_banner_detail.config(wraplength=wrap_w)
            _set_win_rect(self.root, w=cur_w, h=exp_h)
            cur_after = self._capture_win_rect()
            if cur_after:
                self._saved_rect = cur_after

    def _cycle_alpha(self):
        self.alpha_idx = (self.alpha_idx + 1) % len(self.alphas)
        self.root.attributes("-alpha", self.alphas[self.alpha_idx])

    def _toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)
        _set_win_rect(self.root, topmost=self.topmost)
        self.btn_pin.config(fg=ACCENT_BLUE if self.topmost else FG_DIM)

    def _switch_tab(self, tab_id: str):
        self.active_tab = tab_id
        self._scroll_vel = 0.0
        self._wheel_rem_px = 0.0
        self._scroll_rem = 0.0
        self._update_tab_styles()
        if hasattr(self, "amiibo_bar"):
            if tab_id == "amiibo":
                self.amiibo_bar.pack(fill=tk.X, pady=(0, 5), before=self.view.master)
            else:
                self.amiibo_bar.pack_forget()
        self._refresh_display(force=True)
        self.view.yview_moveto(0.0)

    def _find_next_unused_amiibo(self, start: int = 0) -> int:
        if not self.amiibo_cards:
            return 0
        n = len(self.amiibo_cards)
        for off in range(n):
            idx = (start + off) % n
            c = self.amiibo_cards[idx]
            if not c.get("skip_auto") and c["daily_limit"] and c["key"] not in self.amiibo_used_today:
                return idx
        for off in range(n):
            idx = (start + off) % n
            if not self.amiibo_cards[idx].get("skip_auto"):
                return idx
        return start % n

    def _step_amiibo(self, delta: int):
        if not self.amiibo_cards:
            self.amiibo_cards = scan_amiibo_cards()
        if not self.amiibo_cards:
            return
        self.amiibo_idx = (self.amiibo_idx + delta) % len(self.amiibo_cards)
        self._refresh_display(force=True)
        if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)

    def _jump_next_unused_amiibo(self):
        if not self.amiibo_cards:
            self.amiibo_cards = scan_amiibo_cards()
        if not self.amiibo_cards:
            return
        self.amiibo_idx = self._find_next_unused_amiibo((self.amiibo_idx + 1) % len(self.amiibo_cards))
        self._refresh_display(force=True)
        if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)

    def _toggle_amiibo_mask(self, step: int = 1):
        if not self.amiibo_cards:
            self.amiibo_cards = scan_amiibo_cards()
        mask_indices = [i for i, c in enumerate(self.amiibo_cards) if c["category"] == "mask"]
        if not mask_indices:
            return
        if self.amiibo_idx in mask_indices:
            pos = mask_indices.index(self.amiibo_idx)
            self.amiibo_idx = mask_indices[(pos + step) % len(mask_indices)]
        else:
            self.amiibo_idx = mask_indices[0 if step >= 0 else -1]
        self._refresh_display(force=True)
        if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)

    def _trigger_load_amiibo(self, from_gamepad: bool = False):
        if self._amiibo_busy:
            return
        if from_gamepad and not (
            self.amiibo_scanning
            or self.dist_rail_mode == "amiibo"
            or self.active_tab == "amiibo"
            or get_nfc_state() in (2, 3)
        ):
            return
        if not self.amiibo_cards:
            self.amiibo_cards = scan_amiibo_cards()
        if not self.amiibo_cards:
            al = TrackerAlert("warn", "未找到 Amiibo 文件", "请检查 NX2navi/amiibo 或 Fritchii/user/amiibo 目录下的 .bin 文件")
            self._show_banner(al)
            return

        card = self.amiibo_cards[self.amiibo_idx % len(self.amiibo_cards)]
        self._amiibo_busy = True
        loading_al = TrackerAlert("info", f"🎁 正在载入 Amiibo：{card['name']}", card["reward_short"])
        self._show_banner(loading_al)
        if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
            self._show_fs_toast([loading_al], self._fs_monitor_rect, self.last_eval)

        def _worker():
            ok, msg = load_amiibo_in_emulator(card["path"])
            self.root.after(0, lambda: self._on_amiibo_loaded(card, ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_amiibo_loaded(self, card: dict, ok: bool, msg: str):
        self._amiibo_busy = False
        ts = datetime.now().strftime("%H:%M:%S")
        if ok:
            if card["daily_limit"]:
                self.amiibo_used_today = mark_daily_used(card["key"])
                self.amiibo_idx = self._find_next_unused_amiibo((self.amiibo_idx + 1) % len(self.amiibo_cards))
            al = TrackerAlert("good", f"🎁 已载入：{card['name']}", f"掉落奖励：{card['reward_short']}")
        else:
            al = TrackerAlert("warn", f"⚠ Amiibo 载入未完成：{card['name']}", msg)
        self.alert_history.insert(0, (ts, al))
        self.alert_history = self.alert_history[:60]
        self._show_banner(al)
        if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
            self._show_fs_toast([al], self._fs_monitor_rect, self.last_eval)
            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)
        else:
            self._refresh_display(force=True)
        if self.sound_enabled.get():
            winsound.MessageBeep(winsound.MB_OK if ok else winsound.MB_ICONEXCLAMATION)

    def _update_tab_styles(self):
        for tid, b in self.tab_buttons.items():
            if tid == self.active_tab:
                b.config(bg="#262015", fg=ACCENT_AMBER, font=("Microsoft YaHei UI", 9, "bold"))
            else:
                b.config(bg=BG_CARD, fg=FG_DIM, font=("Microsoft YaHei UI", 9))

    def _east_btn_name(self, kind: str | None = None) -> str:
        k = kind if kind is not None else getattr(getattr(self, "gamepad", None), "last_snap", None)
        if not isinstance(k, str):
            k = getattr(k, "kind", "none")
        if k == "switch":
            return "A"
        if k in ("xbox", "generic"):
            return "B"
        if k in ("ps5", "ps4"):
            return "○"
        return "○/B"

    def handle_gamepad_actions(self, snap: GamepadSnapshot, actions: list[str]):
        """Execute semantic controller actions + 1px smooth touchpad/stick scrolling."""
        if hasattr(self, "lbl_gamepad"):
            pad_state = (snap.connected, snap.kind)
            if pad_state != self._last_pad_label_state:
                self._last_pad_label_state = pad_state
                east = self._east_btn_name(snap.kind if snap.connected else "none")
                if snap.connected:
                    if snap.kind == "ps5":
                        txt = f"🎮 {snap.label}｜触控板←→切页/↑↓丝滑滚屏 · 呼唤Amiibo自动弹出(L3+○载入)"
                    elif snap.kind == "ps4":
                        txt = f"🎮 {snap.label}｜触控板/L3+R3:呼出  R3+←→:切页  R3+↑↓/右摇杆:滚屏  L3+○:载入"
                    else:
                        txt = f"🎮 {snap.label}｜L3+R3:呼出  R3+←→:切页  R3+↑↓/右摇杆:滚屏  L3+{east}:载入"
                    self.lbl_gamepad.config(text=txt, fg=ACCENT_GREEN)
                else:
                    self.lbl_gamepad.config(
                        text="🎮 手柄待机（PS5 触控板 / 通用 L3+R3 呼出 · R3+←→切页 · 呼唤Amiibo自动弹出）",
                        fg=FG_DIM,
                    )
                if hasattr(self, "btn_load_amiibo"):
                    self.btn_load_amiibo.config(text=f"🎁 一键载入当前 Amiibo（手柄 L3+{east}）")

        panel_visible = (not self.fs_hidden or self.fs_manual_peek)
        amiibo_discrete = (
            self.amiibo_scanning
            or (self.fs_hidden and not self.fs_manual_peek and self.dist_rail_mode == "amiibo" and snap.btn_r3)
            or (panel_visible and self.active_tab == "amiibo" and snap.btn_r3)
        )

        # 1. Pure 1:1 PS5 Touchpad finger tracking (zero lag while dragging, zero unwanted roll when stopping!)
        if panel_visible and not amiibo_discrete and snap.touch_active and not snap.touchpad:
            if not self._touch_was_scrolling:
                self._touch_was_scrolling = True
                self._scroll_vel = 0.0
                self._wheel_rem_px = 0.0
                self._scroll_rem = 0.0
            if snap.touch_dy != 0.0:
                self._scroll_by_pixels(snap.touch_dy * 0.68)
        else:
            if self._touch_was_scrolling and snap.touch_lifted and panel_visible and not amiibo_discrete:
                # Only engage flick momentum if thumb lifted while actively flicking fast (>= 1150 units/s);
                # if thumb slowed/stopped on pad before lift, touch_vy is 0 -> ZERO extra roll!
                if abs(snap.touch_vy) >= 1150.0:
                    self._scroll_vel = max(-38.0, min(38.0, snap.touch_vy * 0.0085))
                else:
                    self._scroll_vel = 0.0
            self._touch_was_scrolling = False

        # 2. Continuous 120Hz R3 + Right Stick OR held R3 + D-Pad Up/Down smooth scrolling
        if panel_visible and not amiibo_discrete and snap.btn_r3 and not snap.btn_l3 and not snap.touchpad:
            if abs(snap.ry_norm) >= 0.26:
                self._scroll_by_pixels(-snap.ry_norm * 10.5)
                self._scroll_vel = 0.0
                self._wheel_rem_px = 0.0
            if snap.dpad_up or snap.dpad_down:
                self._dpad_hold_frames += 1
                # After brief 110ms initial tap delay, glide continuously at 120Hz while held!
                if self._dpad_hold_frames >= 14:
                    self._wheel_rem_px = 0.0
                    self._scroll_by_pixels(-9.5 if snap.dpad_up else 9.5)
            else:
                self._dpad_hold_frames = 0
        else:
            self._dpad_hold_frames = 0

        if not actions:
            return

        tab_order = ["region", "quests", "boss"]
        rail_order = ["auto", "story", "boss"]
        for act in actions:
            if act == "toggle_panel":
                if self.fs_hidden:
                    self.fs_manual_peek = not self.fs_manual_peek
                    if self.fs_manual_peek:
                        self._destroy_distributed_hud()
                        self._show_root_noactivate()
                        self._refresh_display(force=True)
                    else:
                        _hide_win_noactivate(self.root)
                        if self._get_fs_mode() == "distributed" and self.last_eval:
                            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)
                else:
                    hwnd = _get_top_hwnd(self.root)
                    if hwnd and _user32.IsIconic(hwnd):
                        self._restore_window()
                    else:
                        self._toggle_compact()
            elif act == "open_amiibo":
                pass  # Amiibo UI now appears automatically and exclusively during in-game '呼唤 amiibo'
            elif act in ("prev_view", "next_view"):
                step = -1 if act == "prev_view" else 1
                if self.amiibo_scanning:
                    self._toggle_amiibo_mask(step)
                elif self.fs_hidden and not self.fs_manual_peek:
                    cur_r = self.dist_rail_mode if self.dist_rail_mode in rail_order else "auto"
                    idx = (rail_order.index(cur_r) + step) % len(rail_order)
                    self.dist_rail_mode = rail_order[idx]
                    if self.last_eval:
                        self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)
                else:
                    cur_t = self.active_tab if self.active_tab in tab_order else "region"
                    idx = (tab_order.index(cur_t) + step) % len(tab_order)
                    self._switch_tab(tab_order[idx])
            elif act in ("scroll_up", "scroll_down"):
                delta = -1 if act == "scroll_up" else 1
                if amiibo_discrete:
                    self._step_amiibo(delta)
                elif panel_visible and not snap.touch_active:
                    # Single R3 + D-Pad tap -> exact 48px smooth glide (zero tail overshoot)
                    self._queue_exact_scroll(delta * 48.0)
            elif act in ("stick_up", "stick_down"):
                pass  # Handled continuously above at 120Hz via snap.ry_norm
            elif act == "load_amiibo":
                self._trigger_load_amiibo(from_gamepad=True)
            elif act in ("prev_region", "next_region"):
                vals = list(self.cmb_loc.cget("values"))
                if vals:
                    cur = self.cmb_loc.current()
                    nxt = (cur + (-1 if act == "prev_region" else 1)) % len(vals)
                    self.cmb_loc.current(nxt)
                    self._refresh_display(force=True)
                    if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
                        self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)
            elif act == "snap_live_region":
                self.cmb_loc.current(0)
                self._refresh_display(force=True)
                if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
                    self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)

    def _poll_gamepad(self):
        active_motion = False
        try:
            snap, actions = self.gamepad.poll_actions()
            self.handle_gamepad_actions(snap, actions)

            # A) Exact target-offset glide (mousewheel / keyboard / D-pad tap): zero overshoot, zero <2px tail stutter!
            if abs(self._wheel_rem_px) > 0.5:
                if abs(self._wheel_rem_px) <= 3.0:
                    step_px = self._wheel_rem_px
                    self._wheel_rem_px = 0.0
                else:
                    step_px = self._wheel_rem_px * 0.36
                    if 0.0 < step_px < 2.8:
                        step_px = 2.8
                    elif -2.8 < step_px < 0.0:
                        step_px = -2.8
                    self._wheel_rem_px -= step_px
                self._scroll_by_pixels(step_px)
                active_motion = abs(self._wheel_rem_px) > 0.5

            # B) Intentional fast-flick momentum (touchpad / direct drag): cuts cleanly at 2.5px/frame (never creeps!)
            if not self._touch_was_scrolling and not self._view_dragging and abs(self._scroll_vel) >= 2.5:
                self._scroll_by_pixels(self._scroll_vel)
                self._scroll_vel *= 0.84
                if abs(self._scroll_vel) < 2.5:
                    self._scroll_vel = 0.0
                    self._scroll_rem = 0.0
                else:
                    active_motion = True
            elif not self._touch_was_scrolling and not self._view_dragging:
                self._scroll_vel = 0.0

            if snap.touch_active or snap.btn_r3 or self._view_dragging:
                active_motion = True
        except Exception:
            pass
        # 8ms (~120 FPS) during touch/wheel/drag for instant zero-lag feel, 16ms (~60 FPS) when idle
        self.root.after(8 if active_motion else 16, self._poll_gamepad)

    def _get_selected_location(self, fallback_loc: str) -> str:
        sel = self.cmb_loc.get()
        if not sel or sel.startswith("自动跟随"):
            return fallback_loc
        if "(" in sel and sel.endswith(")"):
            return sel.rsplit("(", 1)[-1][:-1]
        return fallback_loc

    def _get_fs_mode(self) -> str:
        sel = self.cmb_fs.get() if hasattr(self, "cmb_fs") else "全屏分布式"
        if sel == "全屏仅提示":
            return "toast_only"
        if sel == "全屏不隐藏":
            return "off"
        return "distributed"

    def _on_fs_mode_changed(self):
        mode = self._get_fs_mode()
        self.fs_mode.set(mode)
        if mode == "off" and self.fs_hidden:
            self._exit_fullscreen_mode()
        elif self.fs_hidden and mode == "toast_only":
            self._destroy_distributed_hud()
        elif self.fs_hidden and mode == "distributed" and self.last_eval:
            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)

    def _enter_fullscreen_mode(self, monitor_rect: tuple[int, int, int, int] | None = None):
        self._fs_monitor_rect = monitor_rect
        if self.fs_hidden:
            return
        cur = self._capture_win_rect()
        if cur:
            self._saved_rect = cur
        self.fs_hidden = True
        _hide_win_noactivate(self.root)
        if self._get_fs_mode() == "distributed" and self.last_eval:
            self._render_distributed_hud(self.last_eval, monitor_rect, force=True)

    def _exit_fullscreen_mode(self):
        self._hide_fs_toast()
        self._destroy_distributed_hud()
        self._fs_monitor_rect = None
        self._fs_miss_streak = 0
        self.fs_manual_peek = False
        if not self.fs_hidden:
            return
        self.fs_hidden = False
        if self._user_minimized:
            self._show_root_noactivate()
            self._minimize_window()
        else:
            self._show_root_noactivate()
            self._refresh_display(force=True)

    def _destroy_distributed_hud(self):
        self._dist_last_key = None
        self._dist_last_dist_key = None
        self._pill_last_key = None
        self._pill_last_rect = None
        self._rail_last_rect = None
        self._right_last_key = None
        self._right_last_rect = None
        self._rail_nearby_slots = []
        for attr in (
            "_dist_pill_win",
            "_dist_rail_win",
            "_dist_rail_back_win",
            "_dist_right_win",
            "_dist_right_back_win",
        ):
            w = getattr(self, attr, None)
            if w is not None:
                _hide_win_noactivate(w)

    def _render_distributed_hud(self, ev: dict, monitor_rect: tuple[int, int, int, int] | None, force: bool = False):
        """Render distributed mini-HUD modules strictly in Switch 2 OoT safe zones:
        - Top-Center Pill: between Top-Left Hearts/Magic and Top-Right Item buttons
        - Left-Mid Rail: below Hearts/Magic (22% H) and above bottom-left Rupees (68% H)
          * Automatically switches to Boss Strategy Card during any Boss/Mini-Boss battle,
            and automatically restores to region collectibles once battle ends!
        """
        if monitor_rect:
            ml, mt, mr, mb = monitor_rect
        else:
            ml, mt = 0, 0
            mr = self.root.winfo_screenwidth()
            mb = self.root.winfo_screenheight()
        mw = max(800, mr - ml)
        mh = max(600, mb - mt)

        caps = ev["caps"]
        loc = self._get_selected_location(ev["location"])
        reg = ev["regions"].get(loc)
        era_str = "幼年" if caps["is_child"] else "成年"
        rem_sk = max(0, 100 - ev["total_skulls_got"])
        rem_hp = max(0, 36 - ev["total_hp_got"])
        boss = ev.get("active_boss")
        final_stage = ev.get("final_battle_stage")
        is_final = bool(ev.get("is_final_battle"))

        # 1. Top-Center Safe Strip (avoids Top-Left Hearts/Magic and Top-Right Item slots)
        reach_cnt = reg.reachable_missing_count if reg else 0
        unreach_cnt = reg.unreachable_count if reg else 0
        sk_part = f"🕷{reg.skull_got}/{reg.skull_total}" if reg else ""
        hp_part = f"❤{reg.hp_got}/{reg.hp_total}" if reg else ""
        mode_tag = (
            " [主线]" if self.dist_rail_mode == "story"
            else (" [Boss]" if self.dist_rail_mode == "boss"
                  else (" [Amiibo]" if self.dist_rail_mode == "amiibo" else ""))
        )
        if final_stage == "victory":
            main_txt = f"✨ 终局胜利 · 漫长冒险画上句号 | 🕷{ev['total_skulls_got']}/100 ❤{ev['total_hp_got']}/36 | "
            status_txt = "🧚 娜薇：林克，回去吧…"
            status_col = NAVI_CYAN
            pill_bg = BG_VICTORY
            pill_border = BORDER_FINAL_GOLD
            red_txt = ""
        elif final_stage == "escape" and boss is None:
            main_txt = f"🔥 最终决战 · 城堡崩塌逃离 | 🕷{ev['total_skulls_got']}/100 ❤{ev['total_hp_got']}/36 | "
            status_txt = "⚡ 快跟紧塞尔达冲出去！"
            status_col = BORDER_FINAL_GOLD
            pill_bg = BG_BOSS
            pill_border = ACCENT_RED
            red_txt = ""
        elif boss is not None and is_final:
            phase_short = (
                "魔兽加侬·夺回大师之剑！" if final_stage == "ganon_p2"
                else ("魔兽加侬（失去大师之剑）" if final_stage == "ganon_p1" else "魔王加侬多夫")
            )
            main_txt = f"🔱 最终战·{ev['location_zh']}{mode_tag} | 🕷{ev['total_skulls_got']}/100 ❤{ev['total_hp_got']}/36 | "
            status_txt = f"⚔ 最终决战：{phase_short}"
            status_col = NAVI_CYAN if final_stage == "ganon_p2" else BORDER_FINAL_GOLD
            pill_bg = BG_FINAL_GANON if final_stage in ("ganon_p1", "ganon_p2") else BG_FINAL
            pill_border = BORDER_FINAL_GOLD
            red_txt = ""
        else:
            main_txt = (
                f"📍{ev['location_zh']}·{era_str}{mode_tag} | "
                f"{sk_part}({ev['total_skulls_got']}/100 缺{rem_sk}) "
                f"{hp_part}({ev['total_hp_got']}/36 缺{rem_hp}) | "
            )
            if boss is not None:
                status_txt = f"⚔ 激战：{boss['name_zh']}"
                status_col = ACCENT_RED
                pill_border = ACCENT_RED
            elif reach_cnt > 0:
                status_txt = f"可补 {reach_cnt}"
                status_col = ACCENT_AMBER
                pill_border = BORDER_GOLD
            else:
                status_txt = "✔ 本区已清"
                status_col = ACCENT_GREEN
                pill_border = BORDER_GOLD
            pill_bg = BG
            red_txt = f"● 缺前置/成年 {unreach_cnt}" if (unreach_cnt > 0 and boss is None) else ""

        pill_fg_main = BORDER_FINAL_GOLD if (is_final or final_stage == "victory") else FG
        pill_key = (main_txt, status_txt, status_col, red_txt, pill_bg, pill_border, pill_fg_main, monitor_rect)
        if force or pill_key != self._pill_last_key or not _is_win_visible(self._dist_pill_win):
            self._pill_last_key = pill_key
            self._dist_pill_win.configure(bg=pill_border)
            self._dist_pill_inner.configure(bg=pill_bg)
            self._dist_pill_main_lbl.config(text=main_txt, bg=pill_bg, fg=pill_fg_main)
            self._dist_pill_status_lbl.config(text=status_txt, fg=status_col, bg=pill_bg)
            self._dist_pill_red_lbl.config(text=red_txt, bg=pill_bg)
            if red_txt:
                self._dist_pill_status_lbl.pack_configure(padx=(0, 0))
                if not self._dist_pill_red_lbl.winfo_manager():
                    self._dist_pill_red_lbl.pack(side=tk.LEFT, padx=(6, 8))
            else:
                if self._dist_pill_red_lbl.winfo_manager():
                    self._dist_pill_red_lbl.pack_forget()
                self._dist_pill_status_lbl.pack_configure(padx=(0, 8))

            self._dist_pill_win.update_idletasks()
            w_pill = min(int(mw * 0.50), max(340, self._dist_pill_inner.winfo_reqwidth() + 2))
            h_pill = max(28, self._dist_pill_inner.winfo_reqheight() + 2)
            x_pill = ml + (mw - w_pill) // 2
            y_pill = mt + 8
            pill_rect = (x_pill, y_pill, w_pill, h_pill)
            if force or pill_rect != self._pill_last_rect or not _is_win_visible(self._dist_pill_win):
                self._pill_last_rect = pill_rect
                _show_noactivate(self._dist_pill_win, x_pill, y_pill, w_pill, h_pill)
                _flush_paint(self._dist_pill_win)

        # 2. Left-Mid Safe Rail (strictly below Top-Left Hearts/Magic/Mask >= 29% H, above Rupees <= 68% H)
        #    & Right-Mid Safe Rail (adjacent cross-region items, strictly between Top-Right buttons & Minimap)
        reach_miss = (reg.skull_reachable_missing + reg.hp_reachable_missing + reg.quest_reachable_missing) if reg else []
        unreach_list = (reg.skull_unreachable + reg.hp_unreachable + reg.quest_unreachable) if reg else []
        adj_miss = ev["get_adjacent"](loc) if "get_adjacent" in ev else ev.get("adjacent_miss", [])
        active_chains = ev.get("active_chains", [])
        nearby_hints = ev.get("nearby_hints", [])
        story = ev["story"]
        boss_tips = ev["all_boss_tips"].get(loc, [])
        rail_content_kind = (
            "final_victory" if (boss is None and final_stage == "victory")
            else ("final_escape" if (boss is None and final_stage == "escape")
                  else ("boss_fight" if boss is not None
                        else ("amiibo" if self.amiibo_scanning else self.dist_rail_mode)))
        )
        should_show_rail = (
            boss is not None
            or final_stage in ("escape", "victory")
            or rail_content_kind in ("story", "boss", "amiibo")
            or bool(reach_miss)
            or bool(active_chains)
            or bool(nearby_hints)
            or unreach_cnt > 0
        )
        rail_struct_key = (
            should_show_rail,
            rail_content_kind,
            boss["id"] if boss else None,
            final_stage,
            (boss or {}).get("final_phase"),
            loc,
            monitor_rect,
            tuple((x.id, x.name) for x in reach_miss[:5]),
            len(reach_miss),
            tuple((x.id, tuple(x.missing_reqs[:2])) for x in unreach_list[:2]),
            len(unreach_list),
            tuple((c["id"], c["step_key"], c["in_target"]) for c in active_chains[:2]),
            tuple(
                (n["key"], n["reachable"], bool(n.get("radar")), bool(n.get("need_plant")), n.get("tier", ""), n.get("guide", ""))
                for n in nearby_hints[:2]
            ),
            unreach_cnt,
            story["stage"] if rail_content_kind == "story" else "",
            story["title"] if rail_content_kind == "story" else "",
            self.gamepad.last_snap.connected,
            self.gamepad.last_snap.kind,
            self.amiibo_idx if rail_content_kind == "amiibo" else -1,
            len(self.amiibo_used_today) if rail_content_kind == "amiibo" else -1,
        )
        rail_dist_key = tuple(
            (n["key"], n.get("dist"), n.get("radar", ""))
            for n in nearby_hints[:2]
        )

        if not should_show_rail:
            self._dist_last_key = rail_struct_key
            self._dist_last_dist_key = rail_dist_key
            self._rail_last_rect = None
            self._rail_nearby_slots = []
            _hide_win_noactivate(self._dist_rail_win)
            _hide_win_noactivate(self._dist_rail_back_win)
        elif (
            not force
            and rail_struct_key == self._dist_last_key
            and _is_win_visible(self._dist_rail_win)
        ):
            if (
                rail_dist_key != self._dist_last_dist_key
                and self._rail_nearby_slots
                and len(self._rail_nearby_slots) == len(nearby_hints[:2])
            ):
                for (st_lbl, rd_lbl, st_prefix), nh in zip(self._rail_nearby_slots, nearby_hints[:2]):
                    st_lbl.config(text=f"{st_prefix} · 水平{nh['dist']}m")
                    if rd_lbl is not None and nh.get("radar"):
                        rd_lbl.config(text=f"🧭 {nh['radar']}")
                self._dist_last_dist_key = rail_dist_key
                if self._rail_last_rect is not None:
                    rx, ry, rw, rh = self._rail_last_rect
                    self._dist_rail_win.update_idletasks()
                    new_h = min(int(mh * 0.395), max(48, self._dist_rail_body.winfo_reqheight() + 2))
                    if abs(new_h - rh) > 2:
                        self._rail_last_rect = (rx, ry, rw, new_h)
                        _show_noactivate(self._dist_rail_win, rx, ry, rw, new_h)
            _ensure_topmost_noactivate(self._dist_rail_win)
        else:
            self._dist_last_key = rail_struct_key
            self._dist_last_dist_key = rail_dist_key
            self._render_left_rail_contents(
                boss, rail_content_kind, reg, loc, reach_miss, unreach_list, active_chains, nearby_hints, unreach_cnt, story, boss_tips, ml, mt, mw, mh, final_stage=final_stage
            )

        # 3. Right-Mid Safe Rail: Other-region reachable items (never overlapped with Left current-region rail)
        should_show_right = (boss is None and not is_final and final_stage not in ("escape", "victory") and rail_content_kind == "auto" and bool(adj_miss))
        right_key = (
            should_show_right,
            tuple(x.id for _, x in adj_miss[:5]) if should_show_right else (),
            len(adj_miss) if should_show_right else 0,
            monitor_rect,
        )
        if not should_show_right:
            self._right_last_key = right_key
            self._right_last_rect = None
            _hide_win_noactivate(self._dist_right_win)
            _hide_win_noactivate(self._dist_right_back_win)
        elif force or right_key != self._right_last_key or not _is_win_visible(self._dist_right_win):
            self._right_last_key = right_key
            self._render_right_rail_contents(ev, adj_miss, mt, mr, mw, mh)
        else:
            _ensure_topmost_noactivate(self._dist_right_win)

    def _render_left_rail_contents(
        self, boss, rail_content_kind, reg, loc, reach_miss, unreach_list, active_chains, nearby_hints, unreach_cnt, story, boss_tips, ml, mt, mw, mh, final_stage=None
    ):
        is_final_boss = bool(boss and boss.get("is_final"))
        is_ganon = (final_stage in ("ganon_p1", "ganon_p2"))
        if is_final_boss:
            rail_border = BORDER_FINAL_GOLD
            rail_alpha = 0.88
            rail_bg = BG_FINAL_GANON if is_ganon else BG_FINAL
            hdr_bg = BG_FINAL_GANON_HDR if is_ganon else BG_FINAL_HDR
            w_rail = min(295, max(225, int(mw * 0.16)))
        elif final_stage == "victory" and boss is None:
            rail_border = BORDER_FINAL_GOLD
            rail_alpha = 0.88
            rail_bg = BG_VICTORY
            hdr_bg = BG_VICTORY_HDR
            w_rail = min(295, max(225, int(mw * 0.16)))
        elif final_stage == "escape" and boss is None:
            rail_border = ACCENT_RED
            rail_alpha = 0.86
            rail_bg = BG_BOSS
            hdr_bg = "#3A151B"
            w_rail = min(285, max(215, int(mw * 0.155)))
        else:
            rail_border = ACCENT_RED if boss else BORDER_GOLD
            rail_alpha = 0.84 if boss else 0.78
            rail_bg = BG_BOSS if boss else BG
            hdr_bg = "#3A151B"
            w_rail = min(285 if boss else 265, max(215, int(mw * (0.155 if boss else 0.145))))

        old_win = self._dist_rail_win
        old_body = self._dist_rail_body
        win = self._dist_rail_back_win or old_win
        body = self._dist_rail_back_body or old_body
        nearby_slots: list[tuple[tk.Label, tk.Label | None, str]] = []

        win.configure(bg=rail_border)
        win.attributes("-alpha", rail_alpha)
        body.configure(bg=rail_bg)
        for ch in body.winfo_children():
            ch.destroy()

        if boss is not None and is_final_boss:
            phase = boss.get("final_phase") or final_stage or "ganondorf"
            if phase == "ganon_p2":
                hdr_t = "✨ 最终决战 · 魔兽加侬（终结！）"
                navi_q = "🧚 娜薇：「拿回大师之剑了！用它给加侬致命一击，为漫长的战斗画上句号吧！」"
            elif phase == "ganon_p1":
                hdr_t = "🔥 最终决战 · 魔兽加侬（前半战）"
                navi_q = "🧚 娜薇：「这次一定要一起战斗！就算没有大师之剑，林克也能凭手上道具对抗他！」"
            else:
                hdr_t = "🔱 最终决战 · 魔王加侬多夫"
                navi_q = "🧚 娜薇：「林克，终于到这一刻了！无论多危险，我都会陪你一起面对加侬多夫！」"
            tk.Label(
                body, text=hdr_t,
                bg=hdr_bg, fg=BORDER_FINAL_GOLD,
                font=("Microsoft YaHei UI", 9, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=4
            ).pack(fill=tk.X)
            tk.Label(
                body, text=navi_q,
                bg=rail_bg, fg=NAVI_CYAN,
                font=("Microsoft YaHei UI", 7, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
            tk.Label(
                body, text=f"✦ 有利的道具：{boss['valid_items']}",
                bg=rail_bg, fg=BORDER_FINAL_GOLD,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
            for step in boss["tactics"]:
                is_hi = (phase == "ganon_p2" and "第二阶段" in step) or (phase == "ganon_p1" and "第一阶段" in step)
                tk.Label(
                    body, text=step,
                    bg=rail_bg, fg=BORDER_FINAL_GOLD if is_hi else FG,
                    font=("Microsoft YaHei UI", 7, "bold" if is_hi else "normal"),
                    anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=1
                ).pack(fill=tk.X)
        elif boss is None and final_stage == "escape":
            tk.Label(
                body, text="🔥 最终战中场 · 城堡崩塌逃离",
                bg=hdr_bg, fg=BORDER_FINAL_GOLD,
                font=("Microsoft YaHei UI", 9, "bold"), anchor="w", padx=7, pady=4
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text="🧚 娜薇：「城堡快塌了，林克！快跟紧塞尔达公主冲出去，决战还没有结束！！」",
                bg=rail_bg, fg=NAVI_CYAN,
                font=("Microsoft YaHei UI", 7, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text="• 跟着塞尔达下楼躲避落石；途经阻路的铁甲武士需击败后再继续逃脱。",
                bg=rail_bg, fg=FG,
                font=("Microsoft YaHei UI", 8), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
        elif boss is None and final_stage == "victory":
            tk.Label(
                body, text="✨ 终局胜利 · 漫长的冒险结束了",
                bg=hdr_bg, fg=BORDER_FINAL_GOLD,
                font=("Microsoft YaHei UI", 9, "bold"), anchor="w", padx=7, pady=4
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text="🧚 娜薇：「一切……都结束了呢……\n海拉鲁重回和平的这一天……也是我们分别的时刻呢。」",
                bg=rail_bg, fg=NAVI_CYAN,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=3
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text="「好了，回去吧，林克！去取回原本属于你的时光吧！」",
                bg=rail_bg, fg=BORDER_FINAL_GOLD,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
        elif boss is not None:
            # BOSS BATTLE OVERRIDE: Replace collectibles with instant Boss Combat Strategy!
            tk.Label(
                body,
                text=f"⚔ 激战 · {boss['name_zh']}",
                bg="#3A151B", fg=ACCENT_RED,
                font=("Microsoft YaHei UI", 9, "bold"), anchor="w", padx=7, pady=4
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text=f"✦ 有利的道具：{boss['valid_items']}",
                bg=rail_bg, fg=ACCENT_AMBER,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text=f"✦ 娜薇提示：{boss['navi_hint']}",
                bg=rail_bg, fg=ACCENT_BLUE,
                font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=1
            ).pack(fill=tk.X)
            for step in boss["tactics"]:
                tk.Label(
                    body,
                    text=step,
                    bg=rail_bg, fg=FG,
                    font=("Microsoft YaHei UI", 8), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=1
                ).pack(fill=tk.X)
        elif rail_content_kind == "story":
            tk.Label(
                body,
                text=f"🎯 {story['stage']}",
                bg=BG_HEADER, fg=ACCENT_AMBER,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", padx=7, pady=3
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text=story["title"],
                bg=rail_bg, fg=FG,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
            tk.Label(
                body,
                text=f"📍 {story['target_zh']}\n↳ {story['how_to']}",
                bg=rail_bg, fg="#DCE7F5",
                font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
            ).pack(fill=tk.X)
        elif rail_content_kind == "boss":
            tk.Label(
                body,
                text=f"⚔ {reg.name_zh if reg else loc} · 机关/Boss",
                bg=BG_HEADER, fg=ACCENT_PURPLE,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", padx=7, pady=3
            ).pack(fill=tk.X)
            if boss_tips:
                for bt, bd in boss_tips[:3]:
                    tk.Label(
                        body,
                        text=f"• {bt}：{bd}",
                        bg=rail_bg, fg=FG,
                        font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
                    ).pack(fill=tk.X)
            else:
                tk.Label(
                    body,
                    text="本区域无迷宫Boss，滑触控板←或按 R3+← 切回查漏。",
                    bg=rail_bg, fg=FG_DIM,
                    font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=4
                ).pack(fill=tk.X)
        elif rail_content_kind == "amiibo":
            cards = self.amiibo_cards
            used = self.amiibo_used_today
            supply_left = sum(1 for x in cards if x["daily_limit"] and x["key"] not in used)
            tk.Label(
                body,
                text=f"🎁 Amiibo 选卡（{self.amiibo_idx + 1 if cards else 0}/{len(cards)} · 余{supply_left}）",
                bg=BG_HEADER, fg=ACCENT_AMBER,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", padx=7, pady=3
            ).pack(fill=tk.X)
            if cards:
                n = len(cards)
                cur_idx = self.amiibo_idx % n
                win_sz = min(6, n)
                start_i = max(0, min(cur_idx - win_sz // 2, n - win_sz))
                for i in range(start_i, start_i + win_sz):
                    item = cards[i]
                    is_sel = (i == cur_idx)
                    is_used = item["key"] in used
                    if not item["daily_limit"]:
                        tag_txt, tag_col = "[面具切换]", ACCENT_PURPLE
                    elif is_used:
                        tag_txt, tag_col = "[已刷过]", ACCENT_GREEN if is_sel else FG_DIM
                    else:
                        tag_txt, tag_col = "[可刷]", ACCENT_GREEN
                    prefix = "▶ " if is_sel else ("✔ " if is_used else ("🎭 " if not item["daily_limit"] else "● "))
                    row_bg = "#262015" if is_sel else rail_bg
                    row_fg = FG if is_sel else (FG_DIM if is_used else FG)
                    row = tk.Frame(body, bg=row_bg)
                    row.pack(fill=tk.X, padx=4, pady=1)
                    lbl_nm = f"{prefix}{item['name']}"
                    if len(lbl_nm) > 13:
                        lbl_nm = lbl_nm[:12] + "…"
                    tk.Label(
                        row, text=lbl_nm, bg=row_bg, fg=row_fg,
                        font=("Microsoft YaHei UI", 8, "bold" if is_sel else "normal"), anchor="w"
                    ).pack(side=tk.LEFT, fill=tk.X, expand=True)
                    tk.Label(
                        row, text=tag_txt, bg=row_bg, fg=tag_col,
                        font=("Microsoft YaHei UI", 7, "bold" if is_sel else "normal"), anchor="e"
                    ).pack(side=tk.RIGHT)
                c = cards[cur_idx]
                tk.Label(
                    body, text=f"掉落：{c['reward_short']}",
                    bg=rail_bg, fg=ACCENT_AMBER, font=("Microsoft YaHei UI", 7),
                    anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
                ).pack(fill=tk.X)
                east = self._east_btn_name()
                pad_kind = getattr(self.gamepad.last_snap, "kind", "none")
                am_hint = f"触控板←→换面具 · ↑↓选卡 · L3+{east}载入" if pad_kind == "ps5" else f"R3+←→换面具 · R3+↑↓选卡 · L3+{east}载入"
                tk.Label(
                    body, text=am_hint,
                    bg=BG_HEADER, fg=ACCENT_BLUE, font=("Microsoft YaHei UI", 7, "bold"),
                    anchor="w", padx=7, pady=2
                ).pack(fill=tk.X)
            else:
                tk.Label(
                    body, text="未检测到 Amiibo .bin 文件",
                    bg=rail_bg, fg=FG_DIM, font=("Microsoft YaHei UI", 7), anchor="w", padx=7, pady=4
                ).pack(fill=tk.X)
        else:
            def _draw_chain_boxes():
                for ch in active_chains[:2]:
                    ch_bg = "#351616" if ch["timed"] else ("#1C2B1D" if ch["in_target"] else "#1E222A")
                    ch_fg = ACCENT_RED if ch["timed"] else (ACCENT_GREEN if ch["in_target"] else ACCENT_AMBER)
                    ch_box = tk.Frame(body, bg=ch_bg)
                    ch_box.pack(fill=tk.X, padx=4, pady=(2, 2))
                    loc_tag = "✅就在本区" if ch["in_target"] else f"📍立刻去{ch['target_zh']}" if ch["timed"] else f"📍下一步去{ch['target_zh']}"
                    tk.Label(
                        ch_box, text=f"{ch['badge']} {ch['header']}（{loc_tag}）",
                        bg=ch_bg, fg=ch_fg, font=("Microsoft YaHei UI", 7, "bold"),
                        anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                    ).pack(fill=tk.X)
                    tk.Label(
                        ch_box, text=ch["title"],
                        bg=ch_bg, fg=FG, font=("Microsoft YaHei UI", 7, "bold" if ch["timed"] else "normal"),
                        anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                    ).pack(fill=tk.X)
                    if ch["timed"] or ch["in_target"]:
                        tk.Label(
                            ch_box, text=f"↳ {ch['detail']}",
                            bg=ch_bg, fg=FG_DIM, font=("Microsoft YaHei UI", 7),
                            anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                        ).pack(fill=tk.X, pady=(0, 2))

            urgent_chains = [c for c in active_chains if c["timed"] or c["in_target"]]
            if urgent_chains:
                _draw_chain_boxes()

            hdr_txt = (
                f"🟠 本区可补（{len(reach_miss)} 项）"
                if reach_miss
                else f"✔ {reg.name_zh if reg else loc} · 本区可补已清"
            )
            tk.Label(
                body,
                text=hdr_txt,
                bg=BG_HEADER, fg=ACCENT_AMBER if reach_miss else ACCENT_GREEN,
                font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=3
            ).pack(fill=tk.X)
            max_show = 5
            max_nm_chars = 115 if len(reach_miss) <= 2 else (64 if len(reach_miss) <= 4 else 44)
            for it in reach_miss[:max_show]:
                badge = "🕷" if it.kind == "skulltula" else ("❤" if it.kind == "heart_piece" else "⭐")
                col = ACCENT_AMBER if it.kind == "skulltula" else (ACCENT_RED if it.kind == "heart_piece" else ACCENT_PURPLE)
                fl_prefix = f"[{it.floor}]" if getattr(it, "floor", "") else ""
                full_nm = f"{fl_prefix}{it.name}"
                short_name = full_nm if len(full_nm) <= max_nm_chars else full_nm[:max_nm_chars - 1] + "…"
                if it.night_only:
                    short_name = "🌙" + short_name
                row = tk.Frame(body, bg=rail_bg)
                row.pack(fill=tk.X, padx=5, pady=1)
                tk.Label(row, text=badge, bg=rail_bg, fg=col, font=("Microsoft YaHei UI", 8), width=2).pack(side=tk.LEFT, anchor="n")
                tk.Label(
                    row, text=short_name, bg=rail_bg, fg=FG,
                    font=("Microsoft YaHei UI", 8), anchor="w", justify=tk.LEFT, wraplength=w_rail - 34
                ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            if len(reach_miss) > max_show:
                tk.Label(
                    body, text=f"… 另有 {len(reach_miss) - max_show} 项",
                    bg=rail_bg, fg=FG_DIM, font=("Microsoft YaHei UI", 7), anchor="w", padx=7, pady=1
                ).pack(fill=tk.X)

            if unreach_cnt > 0:
                tk.Label(
                    body, text=f"● 本区另有 {unreach_cnt} 项缺前置/成年",
                    bg=rail_bg, fg=ACCENT_RED, font=("Microsoft YaHei UI", 7, "bold"),
                    anchor="w", justify=tk.LEFT, wraplength=w_rail - 14, padx=7, pady=2
                ).pack(fill=tk.X)
                for uit in unreach_list[:2]:
                    fl_u = f"[{uit.floor}]" if getattr(uit, "floor", "") else ""
                    u_full = f"{fl_u}{uit.name}"
                    uname = u_full if len(u_full) <= 36 else u_full[:35] + "…"
                    ureq = "、".join(uit.missing_reqs[:2])
                    tk.Label(
                        body, text=f"🔒 {uname}（缺:{ureq}）",
                        bg=rail_bg, fg="#E08F8F", font=("Microsoft YaHei UI", 7),
                        anchor="w", justify=tk.LEFT, wraplength=w_rail - 16, padx=7, pady=1
                    ).pack(fill=tk.X)

            for nh in nearby_hints[:2]:
                is_soil = (nh["kind"] == "bean_soil")
                nbg = "#2C1818" if not nh["reachable"] else ("#1C2B1D" if is_soil else "#18242C")
                nfg = ACCENT_RED if not nh["reachable"] else (ACCENT_AMBER if (is_soil and nh.get("need_plant")) else (ACCENT_GREEN if nh["kind"] != "grotto" else ACCENT_BLUE))
                nbox = tk.Frame(body, bg=nbg)
                nbox.pack(fill=tk.X, padx=4, pady=(2, 1))
                fl_n = f"[{nh['floor']}] " if nh.get("floor") else ""
                status_s = (
                    "🌱 软土坑提示" if is_soil
                    else (f"🔒 {fl_n}暂不可拿(缺:{'、'.join(nh['missing_reqs'][:2])})" if not nh["reachable"] else (f"🔔 {fl_n}可拿!" if nh["kind"] != "grotto" else "🔔 隐藏洞"))
                )
                st_lbl = tk.Label(
                    nbox, text=f"{status_s} · 水平{nh['dist']}m",
                    bg=nbg, fg=nfg, font=("Microsoft YaHei UI", 7, "bold"),
                    anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                )
                st_lbl.pack(fill=tk.X)
                rd_lbl = None
                if nh.get("radar"):
                    rd_lbl = tk.Label(
                        nbox, text=f"🧭 {nh['radar']}",
                        bg=nbg, fg=ACCENT_AMBER, font=("Microsoft YaHei UI", 7, "bold"),
                        anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                    )
                    rd_lbl.pack(fill=tk.X)
                nearby_slots.append((st_lbl, rd_lbl, status_s))
                tk.Label(
                    nbox, text=nh["name"],
                    bg=nbg, fg=FG, font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                ).pack(fill=tk.X)
                if nh.get("guide"):
                    g_short = nh["guide"] if len(nh["guide"]) <= 68 else nh["guide"][:67] + "…"
                    tk.Label(
                        nbox, text=f"↳ {g_short}",
                        bg=nbg, fg=FG_DIM, font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_rail - 20, padx=5, pady=1
                    ).pack(fill=tk.X)

            if not urgent_chains and active_chains:
                # Non-urgent chains belong in the Quests tab; only show a 1-line compact reminder if region has room
                pass

        if self.gamepad.last_snap.connected:
            pad_hint = "触控板滑动切/按呼全窗" if self.gamepad.last_snap.kind == "ps5" else "L3+R3全窗 · R3+←→切"
            tk.Label(
                body, text=f"🎮 {pad_hint}",
                bg=BG_HEADER, fg=FG_DIM, font=("Microsoft YaHei UI", 7), anchor="w", padx=7, pady=1
            ).pack(fill=tk.X)

        self._rail_nearby_slots = nearby_slots
        win.update_idletasks()
        h_rail = min(int(mh * 0.395), max(48, body.winfo_reqheight() + 2))
        x_rail = ml + 14
        y_rail = mt + int(mh * 0.455)
        self._rail_last_rect = (x_rail, y_rail, w_rail, h_rail)
        insert_after = _get_top_hwnd(old_win) if (win is not old_win and _is_win_visible(old_win)) else _HWND_TOPMOST
        _show_noactivate(win, x_rail, y_rail, w_rail, h_rail, insert_after=insert_after)
        _flush_paint(win)
        if win is not old_win:
            _hide_win_noactivate(old_win)
            _ensure_topmost_noactivate(win)
            self._dist_rail_win, self._dist_rail_back_win = win, old_win
            self._dist_rail_body, self._dist_rail_back_body = body, old_body

    def _render_right_rail_contents(self, ev: dict, adj_miss: list, mt: int, mr: int, mw: int, mh: int):
        old_win = self._dist_right_win
        old_body = self._dist_right_body
        win = self._dist_right_back_win or old_win
        body = self._dist_right_back_body or old_body

        for ch in body.winfo_children():
            ch.destroy()

        w_right = min(280, max(220, int(mw * 0.15)))
        tk.Label(
            body,
            text=f"🔗 相连其他区域可拿（{len(adj_miss)} 项）",
            bg=BG_HEADER, fg=ACCENT_BLUE,
            font=("Microsoft YaHei UI", 8, "bold"), anchor="w", justify=tk.LEFT, wraplength=w_right - 14, padx=7, pady=3
        ).pack(fill=tk.X)

        max_show = 5
        for hint, it in adj_miss[:max_show]:
            loc_zh = ev["regions"][it.location].name_zh if it.location in ev["regions"] else it.location
            ktag = "🕷" if it.kind == "skulltula" else ("❤" if it.kind == "heart_piece" else "⭐")
            short_it = it.name if len(it.name) <= 22 else it.name[:21] + "…"
            if it.night_only:
                short_it = "🌙" + short_it
            short_hint = hint.split("（", 1)[0]
            if len(short_hint) > 20:
                short_hint = short_hint[:19] + "…"
            row = tk.Frame(body, bg=BG)
            row.pack(fill=tk.X, padx=5, pady=1)
            tk.Label(row, text=ktag, bg=BG, fg=ACCENT_BLUE, font=("Microsoft YaHei UI", 8), width=2).pack(side=tk.LEFT, anchor="n")
            txt_col = tk.Frame(row, bg=BG)
            txt_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                txt_col, text=f"[{loc_zh}] {short_it}", bg=BG, fg=FG,
                font=("Microsoft YaHei UI", 8), anchor="w", justify=tk.LEFT, wraplength=w_right - 36
            ).pack(fill=tk.X)
            tk.Label(
                txt_col, text=f"↳ {short_hint}", bg=BG, fg=FG_DIM,
                font=("Microsoft YaHei UI", 7), anchor="w", justify=tk.LEFT, wraplength=w_right - 36
            ).pack(fill=tk.X)

        if len(adj_miss) > max_show:
            tk.Label(
                body, text=f"… 另有 {len(adj_miss) - max_show} 项",
                bg=BG, fg=FG_DIM, font=("Microsoft YaHei UI", 7), anchor="w", padx=7, pady=1
            ).pack(fill=tk.X)

        win.update_idletasks()
        h_right = min(int(mh * 0.33), max(48, body.winfo_reqheight() + 2))
        x_right = mr - w_right - 14
        y_right = mt + int(mh * 0.32)
        self._right_last_rect = (x_right, y_right, w_right, h_right)
        insert_after = _get_top_hwnd(old_win) if (win is not old_win and _is_win_visible(old_win)) else _HWND_TOPMOST
        _show_noactivate(win, x_right, y_right, w_right, h_right, insert_after=insert_after)
        _flush_paint(win)
        if win is not old_win:
            _hide_win_noactivate(old_win)
            _ensure_topmost_noactivate(win)
            self._dist_right_win, self._dist_right_back_win = win, old_win
            self._dist_right_body, self._dist_right_back_body = body, old_body

    def _hide_fs_toast(self):
        if self._toast_after_id:
            try:
                self.root.after_cancel(self._toast_after_id)
            except Exception:
                pass
            self._toast_after_id = None
        _hide_win_noactivate(self._toast_win)

    def _show_fs_toast(self, alerts: list[TrackerAlert], monitor_rect: tuple[int, int, int, int] | None, ev: dict):
        if not alerts:
            return
        if self._toast_after_id:
            try:
                self.root.after_cancel(self._toast_after_id)
            except Exception:
                pass
            self._toast_after_id = None

        first = alerts[0]
        is_warn = (first.level == "warn")
        is_final_victory = first.title.startswith("✨ 终局胜利")
        is_final_phase = first.title.startswith(("🔱 最终决战", "🔥 最终决战", "🔥 加侬多夫倒下", "✨ 夺回大师之剑"))
        is_chain = ("【完整多轮路线】" in first.detail) or first.title.startswith("⏳") or first.title.startswith("🗡") or first.title.startswith("🎭")
        is_prox = first.title.startswith(("🔔", "🔒", "🌱"))

        toast_bg = BG_CARD
        sub_fg = FG
        accent = ACCENT_RED if is_warn else (ACCENT_BLUE if first.title.startswith("🔔") else ACCENT_GREEN)

        if is_final_victory:
            head_txt = first.title
            sub_txt = first.detail
            toast_bg = BG_VICTORY
            accent = BORDER_FINAL_GOLD
            sub_fg = NAVI_CYAN
        elif is_final_phase:
            head_txt = first.title
            sub_txt = first.detail
            toast_bg = BG_FINAL_GANON if any(k in first.title for k in ("魔兽", "倒下", "大师之剑")) else BG_FINAL
            accent = BORDER_FINAL_GOLD
            sub_fg = NAVI_CYAN
        elif is_warn or is_chain or is_prox:
            head_txt = first.title
            sub_txt = first.detail
        elif first.title.startswith("⚔ "):
            head_txt = first.title
            sub_txt = first.detail
            accent = ACCENT_RED
        elif first.title.startswith("✔ 战斗结束"):
            head_txt = first.title
            sub_txt = first.detail
        elif len(alerts) == 1:
            head_txt = f"✔ 拿取成功 · {first.title}"
            sub_txt = first.detail
        else:
            head_txt = f"✔ 拿取成功（+{len(alerts)} 项）"
            rem_sk = max(0, 100 - ev["total_skulls_got"])
            rem_hp = max(0, 36 - ev["total_hp_got"])
            sub_txt = f"{first.title}\n全图蜘蛛 {ev['total_skulls_got']}/100（还剩 {rem_sk}）｜心片 {ev['total_hp_got']}/36（还剩 {rem_hp}）"

        wrap_px = 500 if (is_final_victory or is_final_phase) else (470 if is_chain else 400)
        self._toast_card.configure(bg=toast_bg, highlightbackground=accent)
        self._toast_head_lbl.configure(text=head_txt, bg=toast_bg, fg=accent, wraplength=wrap_px)
        self._toast_sub_lbl.configure(text=sub_txt, bg=toast_bg, fg=sub_fg, wraplength=wrap_px)

        self._toast_win.update_idletasks()
        max_w = 540 if (is_final_victory or is_final_phase) else (510 if is_chain else 440)
        w = min(max_w, max(300, self._toast_card.winfo_reqwidth()))
        h = max(44, self._toast_card.winfo_reqheight())
        if monitor_rect:
            ml, mt, mr, _mb = monitor_rect
            mw = mr - ml
        else:
            ml, mt = 0, 0
            mw = self.root.winfo_screenwidth()
        # Top-Center below safe pill (completely avoids Top-Left Hearts, Top-Right Buttons, Bottom Dialogue/Minimap)
        x = ml + (mw - w) // 2
        y_offset = 46 if _is_win_visible(self._dist_pill_win) else 12
        y = mt + y_offset
        _show_noactivate(self._toast_win, x, y, w, h)
        _flush_paint(self._toast_win)

        hold_ms = (
            14000 if is_final_victory
            else (10500 if is_final_phase else (9500 if is_chain else (6500 if is_prox else 4200)))
        )
        self._toast_after_id = self.root.after(hold_ms, self._hide_fs_toast)

    def _poll(self):
        mon_rect = None
        fs_mode = self._get_fs_mode()
        if fs_mode != "off":
            ignore = {
                h for h in (
                    _get_top_hwnd(self.root),
                    _get_top_hwnd(self._toast_win) if self._toast_win else 0,
                    _get_top_hwnd(self._dist_pill_win) if self._dist_pill_win else 0,
                    _get_top_hwnd(self._dist_rail_win) if self._dist_rail_win else 0,
                    _get_top_hwnd(self._dist_rail_back_win) if self._dist_rail_back_win else 0,
                    _get_top_hwnd(self._dist_right_win) if self._dist_right_win else 0,
                    _get_top_hwnd(self._dist_right_back_win) if self._dist_right_back_win else 0,
                ) if h
            }
            is_fs, mon_rect = detect_fullscreen_monitor(ignore)
            if is_fs:
                self._fs_miss_streak = 0
                prev_rect = self._fs_monitor_rect
                self._fs_monitor_rect = mon_rect
                if not self.fs_hidden:
                    self._enter_fullscreen_mode(mon_rect)
                elif not self.fs_manual_peek and fs_mode == "distributed":
                    if mon_rect != prev_rect and self.last_eval:
                        self._render_distributed_hud(self.last_eval, mon_rect, force=True)
                    else:
                        _ensure_topmost_noactivate(self._dist_pill_win)
                        _ensure_topmost_noactivate(self._dist_rail_win)
                        _ensure_topmost_noactivate(self._dist_right_win)
                        _ensure_topmost_noactivate(self._toast_win)
                elif self.fs_manual_peek:
                    _ensure_topmost_noactivate(self.root, clickthrough=False, tool_window=False)
            elif self.fs_hidden:
                self._fs_miss_streak += 1
                if self._fs_miss_streak >= 3:
                    self._exit_fullscreen_mode()
            else:
                self._fs_miss_streak = 0
                if self._user_minimized and _is_win_visible(self.root):
                    self._user_minimized = False
        elif self.fs_hidden:
            self._exit_fullscreen_mode()
        elif self._user_minimized and _is_win_visible(self.root):
            self._user_minimized = False

        with self._bg_lock:
            pkt = self._bg_pending
            self._bg_pending = None

        if pkt is None:
            self.root.after(180, self._poll)
            return

        self._bg_ever_received = True
        ev, nfc_st = pkt
        now_scanning = (nfc_st == 2)
        if not self.amiibo_cards and (now_scanning or (time.monotonic() - self._last_amiibo_scan >= 4.0)):
            self._last_amiibo_scan = time.monotonic()
            found_cards = scan_amiibo_cards()
            if found_cards:
                self.amiibo_cards = found_cards
                self.amiibo_idx = self._find_next_unused_amiibo(0)
        if now_scanning != self.amiibo_scanning:
            self.amiibo_scanning = now_scanning
            am_btn = self.tab_buttons.get("amiibo")
            if now_scanning:
                if self.active_tab != "amiibo":
                    self._tab_before_amiibo = self.active_tab
                if am_btn and not am_btn.winfo_manager():
                    am_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
                self._switch_tab("amiibo")
                if self.amiibo_cards:
                    c = self.amiibo_cards[self.amiibo_idx % len(self.amiibo_cards)]
                    east = self._east_btn_name()
                    nav_hint = "触控板↑↓选卡 / ←→换面具" if getattr(self.gamepad.last_snap, "kind", "none") == "ps5" else "R3+↑↓选卡 / R3+←→换面具"
                    scan_al = TrackerAlert(
                        "info",
                        f"🎁 检测到「呼唤 amiibo」｜待刷：{c['name']}",
                        f"奖励：{c['reward_short']}｜按 L3+{east} 直接载入（{nav_hint}）",
                    )
                    self._show_banner(scan_al)
                    if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
                        self._show_fs_toast([scan_al], mon_rect or self._fs_monitor_rect, self.last_eval)
            else:
                if am_btn and am_btn.winfo_manager():
                    am_btn.pack_forget()
                if self.dist_rail_mode == "amiibo":
                    self.dist_rail_mode = "auto"
                if self.active_tab == "amiibo":
                    self._switch_tab(self._tab_before_amiibo or "region")
            if self.fs_hidden and not self.fs_manual_peek and self.last_eval and fs_mode == "distributed":
                self._render_distributed_hud(self.last_eval, mon_rect or self._fs_monitor_rect, force=True)

        if ev is not None:
            self.last_eval = ev
            is_reload_sync = any("已同步读档进度" in a.title for a in ev["alerts"])
            boss = ev.get("active_boss")
            cur_boss_id = boss["id"] if boss else None
            final_stage = ev.get("final_battle_stage")
            boss_alerts: list[TrackerAlert] = []
            if is_reload_sync:
                self._prev_boss_id = cur_boss_id
                self._prev_boss_name = boss["name_zh"] if boss else None
                self._prev_final_stage = final_stage
            else:
                if final_stage != self._prev_final_stage:
                    if final_stage == "ganondorf":
                        boss_alerts.append(
                            TrackerAlert(
                                "warn",
                                "🔱 最终决战开幕 · 娜薇：「林克，终于走到这里了！」",
                                "「无论前面有多危险，我都会陪你一起面对大魔王加侬多夫！把大妖精和精灵的力量握在手里，上吧！」\n⚔ 有利道具：大师之剑、光之箭、空白瓶子",
                            )
                        )
                    elif final_stage == "escape":
                        boss_alerts.append(
                            TrackerAlert(
                                "warn",
                                "🔥 加侬多夫倒下 · 娜薇：「林克！城堡要塌了，快跟上塞尔达！」",
                                "「快跟紧塞尔达公主冲出去！别让漫长的旅途停在这里——真正的最终决战还在等着我们！！」",
                            )
                        )
                    elif final_stage == "ganon_p1":
                        boss_alerts.append(
                            TrackerAlert(
                                "warn",
                                "🔥 最终决战第二幕 · 娜薇：「这次一定要一起战斗！！」",
                                "「这次光环挡不住我了！因为我……是林克的搭档！！就算没有大师之剑，只凭手上的道具，林克一定也能和他对抗的！」",
                            )
                        )
                    elif final_stage == "ganon_p2":
                        boss_alerts.append(
                            TrackerAlert(
                                "info",
                                "✨ 夺回大师之剑！· 娜薇：「林克！用大师之剑给他致命一击吧！」",
                                "「为漫长的战斗画上句号吧！用光之箭定身或钻过胯下，举起大师之剑终结魔兽加侬！！」",
                            )
                        )
                    elif final_stage == "victory":
                        boss_alerts.append(
                            TrackerAlert(
                                "good",
                                "✨ 终局胜利 · 娜薇：「一切……都结束了呢……」",
                                "「这次的冒险真的非常漫长。海拉鲁重回和平的这一天……也是我们分别的时刻呢。\n好了，回去吧，林克！去取回原本属于你的时光吧！」\n🧚 —— 时之妖精 娜薇 · 感谢你一路走到最后",
                            )
                        )
                    elif self._prev_boss_id and self._prev_boss_name and cur_boss_id is None and self._prev_final_stage not in ("escape", "victory"):
                        boss_alerts.append(
                            TrackerAlert(
                                "good",
                                f"✔ 战斗结束：{self._prev_boss_name}",
                                "🧚 娜薇：「干得漂亮，林克！这场战斗总算赢下来了～」\n左侧悬浮窗已自动还原为本区查漏补缺指引",
                            )
                        )
                elif cur_boss_id != self._prev_boss_id:
                    if cur_boss_id and boss:
                        tactic_1 = f"\n{boss['tactics'][0]}" if boss.get("tactics") else ""
                        boss_alerts.append(
                            TrackerAlert(
                                "warn",
                                f"⚔ 遭遇强敌：{boss['name_zh']}",
                                f"有利的道具：{boss['valid_items']}｜娜薇：{boss['navi_hint']}{tactic_1}",
                            )
                        )
                    elif self._prev_boss_id and self._prev_boss_name:
                        boss_alerts.append(
                            TrackerAlert(
                                "good",
                                f"✔ 战斗结束：{self._prev_boss_name}",
                                "🧚 娜薇：「干得漂亮，林克！这场战斗总算赢下来了～」\n左侧悬浮窗已自动还原为本区查漏补缺指引",
                            )
                        )
                self._prev_boss_id = cur_boss_id
                self._prev_boss_name = boss["name_zh"] if boss else None
                self._prev_final_stage = final_stage

            if ev["alerts"] or boss_alerts:
                ts = datetime.now().strftime("%H:%M:%S")
                for al in ev["alerts"] + boss_alerts:
                    self.alert_history.insert(0, (ts, al))
                self.alert_history = self.alert_history[:60]
                top_alert = (boss_alerts + ev["alerts"])[0]
                has_prio = bool(boss_alerts) or is_reload_sync
                if not has_prio:
                    for al in ev["alerts"]:
                        if al.level in ("warn", "good") or al.title.startswith(("🔔", "🔒")):
                            top_alert = al
                            has_prio = True
                            break
                if has_prio:
                    if top_alert.title.startswith("✨ 终局胜利"):
                        hold_s = 14.0
                    elif top_alert.title.startswith(("🔱 最终决战", "🔥 最终决战", "🔥 加侬多夫倒下", "✨ 夺回大师之剑")):
                        hold_s = 10.5
                    else:
                        hold_s = 9.0 if ("【完整多轮路线】" in top_alert.detail or top_alert.title.startswith("⏳")) else (6.5 if top_alert.title.startswith(("🔔", "🔒")) else 5.5)
                    self._show_banner(top_alert, hold_sec=hold_s)
                elif boss:
                    self._show_banner(
                        TrackerAlert(
                            "warn",
                            f"⚔ 正在交战：{boss['name_zh']}",
                            f"有利的道具：{boss['valid_items']}",
                        ),
                        hold_sec=3.0,
                    )
                else:
                    self._show_idle_region_banner(ev)
                good_alerts = [a for a in ev["alerts"] if a.level == "good"]
                warn_alerts = [a for a in ev["alerts"] if a.level == "warn"]
                prox_alerts = [a for a in ev["alerts"] if a.title.startswith(("🔔", "🔒"))]
                timed_alerts = [a for a in warn_alerts if a.title.startswith(("⏳", "🔒"))]
                if self.fs_hidden and not self.fs_manual_peek:
                    if boss_alerts:
                        self._show_fs_toast(boss_alerts, mon_rect or self._fs_monitor_rect, ev)
                    elif timed_alerts:
                        self._show_fs_toast(timed_alerts, mon_rect or self._fs_monitor_rect, ev)
                    elif good_alerts:
                        self._show_fs_toast(good_alerts, mon_rect or self._fs_monitor_rect, ev)
                    elif prox_alerts:
                        self._show_fs_toast(prox_alerts, mon_rect or self._fs_monitor_rect, ev)
                    elif warn_alerts and fs_mode == "distributed":
                        self._show_fs_toast(warn_alerts, mon_rect or self._fs_monitor_rect, ev)
                if self.sound_enabled.get():
                    if warn_alerts and (timed_alerts or not self.fs_hidden or fs_mode == "distributed"):
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    elif good_alerts or any(a.title.startswith("✨ 终局胜利") for a in boss_alerts):
                        winsound.MessageBeep(winsound.MB_OK)
            elif time.monotonic() >= self._banner_hold_until:
                self._show_idle_region_banner(ev)
            if self.fs_hidden and not self.fs_manual_peek:
                if fs_mode == "distributed":
                    self._render_distributed_hud(ev, mon_rect or self._fs_monitor_rect, force=False)
            else:
                self._refresh_display(force=False)
        else:
            if not self.last_eval:
                self.lbl_source.config(text="● 等待游戏/存档", fg=ACCENT_AMBER)

        self.root.after(180, self._poll)

    def _render_waiting_guide(self):
        self.view.configure(state=tk.NORMAL)
        self.view.delete("1.0", tk.END)
        self._add_section_header("⏳ 等待连接游戏或读取存档...", "hdr_amber")
        self._add_row(
            "1",
            "直接启动游戏即可自动连接",
            sub="支持 NX2navi (ocarina.exe)、Fritchii / Lichii (lichii.exe)、Hookshot (hookshot.exe)、Eden / Yuzu / Citron / Suyu / Ryujinx。",
            badge_tag="badge_blue",
            sub_tag="sub_guide",
        )
        self._add_row(
            "2",
            "未开游戏时也可手动放存档查看",
            sub="把游戏存档里的 slot_00 ~ slot_05 文件夹放入本目录 saves/ 文件夹，或在 tracker_config.json 中填写 save_dir。",
            badge_tag="badge_green",
            sub_tag="sub_guide",
        )
        self._add_row(
            "3",
            "全屏与手柄快捷键说明",
            sub="游戏全屏时自动切换为屏幕安全区微浮窗；PS5 触控板或通用手柄 L3+R3 可随时呼出大面板，R3+←→切页，呼唤 amiibo 时按 L3+○/B/A 直接载入。",
            badge_tag="badge_purple",
            sub_tag="sub_guide",
        )
        self.view.configure(state=tk.DISABLED)

    def _set_banner_labels(self, title: str, fg: str, detail: str):
        key = (title, fg, detail, self.compact)
        if key == self._last_banner_key:
            return
        self._last_banner_key = key
        cur_w = max(360, self.root.winfo_width() or 468)
        wrap_w = max(260, cur_w - 38)
        self.lbl_banner_title.config(text=title, fg=fg, wraplength=wrap_w)
        self.lbl_banner_detail.config(text=detail, wraplength=wrap_w)
        if self.compact:
            self._fit_compact_height()

    def _apply_final_desktop_theme(self, final_stage: str | None, active_boss: dict | None):
        is_final_boss = bool(active_boss and active_boss.get("is_final"))
        if final_stage == "victory":
            frame_bg, frame_bd = BG_VICTORY, BORDER_FINAL_GOLD
            ban_bg, ban_bd, det_fg = BG_VICTORY_HDR, BORDER_FINAL_GOLD, NAVI_CYAN
        elif final_stage in ("ganondorf", "ganon_p1", "ganon_p2") or is_final_boss:
            is_ganon = final_stage in ("ganon_p1", "ganon_p2")
            frame_bg = BG_FINAL_GANON if is_ganon else BG_FINAL
            frame_bd = BORDER_FINAL_GOLD
            ban_bg = BG_FINAL_GANON_HDR if is_ganon else BG_FINAL_HDR
            ban_bd = BORDER_FINAL_GOLD
            det_fg = FG
        elif final_stage == "escape":
            frame_bg, frame_bd = BG_FINAL, ACCENT_RED
            ban_bg, ban_bd, det_fg = BG_BOSS, BORDER_FINAL_GOLD, FG
        else:
            frame_bg, frame_bd = BG, BORDER
            ban_bg, ban_bd, det_fg = BG_CARD, BORDER, FG_DIM
        theme_key = (frame_bg, frame_bd, ban_bg, ban_bd, det_fg)
        if theme_key != self._last_desktop_theme_key:
            self._last_desktop_theme_key = theme_key
            self.frame.configure(bg=frame_bg, highlightbackground=frame_bd)
            self.banner.configure(bg=ban_bg, highlightbackground=ban_bd)
            self.lbl_banner_title.configure(bg=ban_bg)
            self.lbl_banner_detail.configure(bg=ban_bg, fg=det_fg)

    def _show_idle_region_banner(self, ev: dict):
        boss = ev.get("active_boss")
        final_stage = ev.get("final_battle_stage")
        if boss and boss.get("is_final"):
            phase = boss.get("final_phase") or final_stage or "ganondorf"
            if phase == "ganon_p2":
                t_txt = "✨ 最终决战 · 夺回大师之剑！"
                d_txt = "🧚 娜薇：「用大师之剑给他致命一击，为漫长的战斗画上句号吧！」"
            elif phase == "ganon_p1":
                t_txt = "🔥 最终决战 · 魔兽加侬（前半战）"
                d_txt = "🧚 娜薇：「这次一定要一起战斗！就算没有大师之剑也能对抗他！」"
            else:
                t_txt = "🔱 最终决战 · 魔王加侬多夫"
                d_txt = "🧚 娜薇：「林克，终于到最后的战斗了！我也会一直陪在你身边的！」"
            self._set_banner_labels(t_txt, BORDER_FINAL_GOLD, d_txt)
            return
        if final_stage == "victory":
            self._set_banner_labels(
                "✨ 终局胜利 · 娜薇：「一切……都结束了呢……」",
                BORDER_FINAL_GOLD,
                "「海拉鲁重回和平的这一天……也是我们分别的时刻呢。好了，回去吧，林克！」",
            )
            return
        if final_stage == "escape":
            self._set_banner_labels(
                "🔥 城堡崩塌逃离 · 娜薇：「快跟紧塞尔达公主！」",
                ACCENT_RED,
                "「城堡快塌了！跟着塞尔达往下冲，途中注意击败铁甲武士打通出口！」",
            )
            return
        if boss:
            self._show_banner(
                TrackerAlert("warn", f"⚔ 正在交战：{boss['name_zh']}", f"有利的道具：{boss['valid_items']}｜{boss['navi_hint']}"),
                hold_sec=0.0,
            )
            return
        for ch in ev.get("active_chains", []):
            if ch.get("timed"):
                self._show_banner(
                    TrackerAlert("warn", f"⏳ {ch['header']}：{ch['title']}", f"立刻前往【{ch['target_zh']}】｜{ch['detail']}"),
                    hold_sec=0.0,
                )
                return
        story = ev.get("story")
        if story:
            how = story.get("how_to", "")
            if self.compact:
                detail = f"📍 目标：{story['target_zh']}"
            else:
                detail = f"📍 目标：{story['target_zh']}\n{how}" if how else f"📍 目标：{story['target_zh']}"
            self._set_banner_labels(
                f"🎯 {story['stage']}｜{story['title']}",
                ACCENT_AMBER,
                detail,
            )
            return

    def _show_banner(self, al: TrackerAlert, hold_sec: float = 4.0):
        color = ACCENT_BLUE
        if al.title.startswith(("✨ 终局胜利", "🔱 最终决战", "🔥 最终决战", "🔥 加侬多夫倒下", "✨ 夺回大师之剑")):
            color = BORDER_FINAL_GOLD
        elif al.level == "good":
            color = ACCENT_GREEN
        elif al.level == "warn":
            color = ACCENT_RED
        self._set_banner_labels(al.title, color, al.detail)
        if hold_sec > 0:
            self._banner_hold_until = time.monotonic() + hold_sec

    def _refresh_display(self, force: bool = False, preserve_scroll: bool = False):
        ev = self.last_eval
        if not ev:
            if self.active_tab == "amiibo":
                self.view.configure(state=tk.NORMAL)
                self.view.delete("1.0", tk.END)
                self._render_amiibo_tab()
                self.view.configure(state=tk.DISABLED)
            else:
                self._render_waiting_guide()
            return
        caps = ev["caps"]
        era_str = "幼年" if caps["is_child"] else "成年"
        src_txt = "● 实时内存" if ev["source"] == "live_memory" else f"● {ev.get('slot_name', 'save')}"
        src_col = ACCENT_GREEN if ev["source"] == "live_memory" else ACCENT_BLUE
        boss = ev.get("active_boss")
        final_stage = ev.get("final_battle_stage")
        self._apply_final_desktop_theme(final_stage, boss)
        if final_stage == "victory":
            title_txt, title_fg = "✨ 终局胜利 · 娜薇的告别", BORDER_FINAL_GOLD
        elif final_stage in ("ganondorf", "ganon_p1", "ganon_p2") or (boss and boss.get("is_final")):
            title_txt, title_fg = f"🔱 最终决战 · {ev['location_zh']} · {era_str}", BORDER_FINAL_GOLD
        elif final_stage == "escape":
            title_txt, title_fg = f"🔥 逃离加侬城堡 · {era_str}", BORDER_FINAL_GOLD
        else:
            title_txt, title_fg = f"🧭 {ev['location_zh']} · {era_str}", FG

        rem_sk = max(0, 100 - ev["total_skulls_got"])
        global_txt = f"🕷 黄金骷髅蜘蛛 {ev['total_skulls_got']}/100(缺{rem_sk})  ❤ 心之碎片 {ev['total_hp_got']}/36  🎵 {caps['_songs_count']}/12  🧪 {caps['_bottles_count']}/4"
        hdr_key = (title_txt, title_fg, src_txt, src_col, global_txt)
        if force or hdr_key != self._last_desktop_hdr_key:
            self._last_desktop_hdr_key = hdr_key
            self.lbl_title.config(text=title_txt, fg=title_fg)
            self.lbl_source.config(text=src_txt, fg=src_col)
            self.lbl_global.config(text=global_txt)

        target_loc = self._get_selected_location(ev["location"])
        bj = ev.get("boss_journal") or {}
        render_key = (
            self.active_tab,
            ev["location"],
            target_loc,
            ev["total_skulls_got"],
            ev["total_hp_got"],
            len(self.alert_history),
            caps["is_child"],
            ev["source"],
            ev.get("slot_name"),
            ev["story"]["stage"],
            ev["story"]["title"],
            tuple((c["id"], c["step_key"], c["in_target"]) for c in ev.get("active_chains", [])),
            tuple((n["key"], n["reachable"], int(n["dist"])) for n in ev.get("nearby_hints", [])[:2]),
            boss["id"] if boss else None,
            final_stage,
            (boss or {}).get("final_phase"),
            tuple(b["id"] for b in bj.get("unlocked_undefeated", [])),
            tuple(b["id"] for b in bj.get("defeated", [])),
            self._show_completed_quests,
            self._show_defeated_bosses,
            self.amiibo_idx if self.active_tab == "amiibo" else -1,
            len(self.amiibo_used_today) if self.active_tab == "amiibo" else -1,
        )
        if not force and render_key == self.last_render_key:
            return
        self.last_render_key = render_key

        frac_before = self.view.yview()[0]
        self.view.configure(state=tk.NORMAL)
        self.view.delete("1.0", tk.END)

        if self.active_tab == "region":
            self._render_region_tab(ev, target_loc)
        elif self.active_tab == "quests":
            self._render_quests_tab(ev)
        elif self.active_tab == "amiibo":
            self._render_amiibo_tab()
        else:
            self._render_boss_and_log_tab(ev)

        self.view.configure(state=tk.DISABLED)
        if not force or preserve_scroll:
            self.view.yview_moveto(frac_before)

    def _toggle_completed_quests(self):
        self._show_completed_quests = not self._show_completed_quests
        self._refresh_display(force=True, preserve_scroll=True)

    def _toggle_defeated_bosses(self):
        self._show_defeated_bosses = not self._show_defeated_bosses
        self._refresh_display(force=True, preserve_scroll=True)

    def _add_collapsible_green_header(self, tag_name: str, text: str, callback):
        self.view.insert(tk.END, f" {text}\n", ("hdr_green_toggle", tag_name))
        self.view.insert(tk.END, "\n", "sep")
        self.view.tag_bind(
            tag_name,
            "<ButtonRelease-1>",
            lambda e: callback() if abs(e.y_root - getattr(self, "_view_press_y", e.y_root)) <= 8 else None,
        )
        self.view.tag_bind(tag_name, "<Enter>", lambda _e: self.view.config(cursor="hand2"))
        self.view.tag_bind(tag_name, "<Leave>", lambda _e: self.view.config(cursor="arrow"))

    def _add_section_header(self, text: str, color_tag: str):
        self.view.insert(tk.END, f"{text}\n", color_tag)

    def _add_story_card(self, story: dict):
        self.view.insert(tk.END, f"🎯 {story['stage']}\n", "story_stage")
        self.view.insert(tk.END, f"下一步：{story['title']}\n", "story_title")
        self.view.insert(tk.END, f"📍 主要出现地：{story['target_zh']}\n↳ 怎么走：{story['how_to']}\n", "story_route")
        self.view.insert(tk.END, "\n", "sep")

    def _add_active_boss_card(self, boss: dict):
        if boss.get("is_final"):
            phase = boss.get("final_phase") or "ganondorf"
            if phase == "ganon_p2":
                hdr_t = f"✨ 最终决战（终结阶段）· {boss['name_zh']}"
                navi_q = "🧚 娜薇：「拿回大师之剑了！用它给加侬致命一击，为漫长的战斗画上句号吧！」"
            elif phase == "ganon_p1":
                hdr_t = f"🔥 最终决战（第二幕·前半）· {boss['name_zh']}"
                navi_q = "🧚 娜薇：「这次一定要一起战斗！！因为我……是林克的搭档！！就算没有大师之剑，只凭手上的道具也能对抗他！」"
            else:
                hdr_t = f"🔱 最终决战（第一幕）· {boss['name_zh']}"
                navi_q = "🧚 娜薇：「林克，这就是最后的战斗了！无论前面有多危险，我都会一直陪在你身边的！」"
            self.view.insert(tk.END, f"{hdr_t}\n", "final_hdr")
            self.view.insert(tk.END, f"{navi_q}\n", "final_navi")
            self.view.insert(tk.END, f"✦ 有利的道具：{boss['valid_items']}\n", "final_item")
            lines = [f"✦ 娜薇提示：{boss['navi_hint']}"] + boss["tactics"]
            self.view.insert(tk.END, "\n".join(lines) + "\n", "final_body")
            self.view.insert(tk.END, "\n", "sep")
            return
        self.view.insert(tk.END, f"⚔ 正在交战 · {boss['name_zh']}\n", "boss_hdr")
        self.view.insert(tk.END, f"✦ 有利的道具：{boss['valid_items']}\n", "boss_item")
        lines = [f"✦ 娜薇的提示：{boss['navi_hint']}"] + boss["tactics"]
        self.view.insert(tk.END, "\n".join(lines) + "\n", "boss_body")
        self.view.insert(tk.END, "\n", "sep")

    def _add_final_stage_card(self, final_stage: str | None):
        if final_stage == "escape":
            self.view.insert(tk.END, "🔥 最终战中场 · 城堡崩塌逃离战\n", "final_hdr")
            self.view.insert(
                tk.END,
                "🧚 娜薇：「城堡要塌了，林克！快跟紧塞尔达公主往下冲，决战还没有结束！！」\n",
                "final_navi",
            )
            self.view.insert(
                tk.END,
                "• 限时逃离塔顶：紧跟塞尔达公主沿楼梯向下，注意击败阻路的铁甲武士。\n• 逃出废墟后将立即迎来最终形态的对决！\n",
                "final_body",
            )
            self.view.insert(tk.END, "\n", "sep")
        elif final_stage == "victory":
            self.view.insert(tk.END, "✨ 终局胜利 · 漫长的冒险画上句号\n", "victory_hdr")
            self.view.insert(
                tk.END,
                "🧚 娜薇：「一切……都结束了呢……\n这次的冒险真的非常漫长。海拉鲁重回和平的这一天……也是我们分别的时刻呢。」\n",
                "victory_navi",
            )
            self.view.insert(
                tk.END,
                "「好了，回去吧，林克！去取回原本属于你的时光吧！」\n—— 感谢你与娜薇一同走完这段《塞尔达传说 时之笛》的旅程 ✨\n",
                "victory_body",
            )
            self.view.insert(tk.END, "\n", "sep")

    def _add_unlocked_boss_card(self, boss: dict, loc_zh: str, tag_suffix: str = ""):
        kind_lbl = "中首领" if boss.get("is_miniboss") else "迷宫首领"
        self.view.insert(tk.END, f"⚔ [{loc_zh} · {kind_lbl}] {boss['name_zh']}{tag_suffix}\n", "boss_unlock_hdr")
        self.view.insert(tk.END, f"✦ 有利的道具：{boss['valid_items']}\n", "boss_unlock_item")
        lines = [f"✦ 娜薇的提示：{boss['navi_hint']}"] + boss["tactics"]
        self.view.insert(tk.END, "\n".join(lines) + "\n", "boss_unlock_body")
        self.view.insert(tk.END, "\n", "sep")

    def _add_row(
        self,
        badge: str,
        text: str,
        sub: str = "",
        badge_tag: str = "badge_blue",
        text_tag: str = "item_fg",
        sub_tag: str = "sub_dim",
        sub2: str = "",
    ):
        self.view.insert(tk.END, f" {badge}  ", badge_tag)
        self.view.insert(tk.END, f"{text}\n", text_tag)
        if sub:
            self.view.insert(tk.END, f"{sub}\n", sub_tag)
        if sub2:
            self.view.insert(tk.END, f"{sub2}\n", "sub_guide")
        self.view.insert(tk.END, "\n", "sep")

    def _render_region_tab(self, ev: dict, loc: str):
        reg = ev["regions"].get(loc)
        if not reg:
            return

        # 0. Active Boss battle card (or Final Escape / Final Victory ceremonial card)
        if ev.get("active_boss"):
            self._add_active_boss_card(ev["active_boss"])
        elif ev.get("final_battle_stage") in ("escape", "victory"):
            self._add_final_stage_card(ev.get("final_battle_stage"))

        # Summary header for selected region right at the top
        auto_tag = "当前位置" if loc == ev["location"] else "手动预览"
        self._add_section_header(
            f"📍 {reg.name_zh}（{auto_tag}）｜蜘蛛 {reg.skull_got}/{reg.skull_total} · 心片 {reg.hp_got}/{reg.hp_total}",
            "hdr_blue",
        )

        # 0.3 Proximity / Stone of Agony nearby hints (for current position)
        if loc == ev["location"] and ev.get("nearby_hints"):
            self._add_section_header("🔔 当前站位附近感应（响音石 / 黄金骷髅蜘蛛 / 心之碎片）", "hdr_blue")
            for nh in ev["nearby_hints"][:3]:
                fl_tag = f"[{nh['floor']}] " if nh.get("floor") else ""
                radar_s = f" · 🧭 {nh['radar']}" if nh.get("radar") else ""
                g_sub2 = f"↳ 怎么拿：{nh['guide']}" if nh.get("guide") else ""
                if not nh["reachable"]:
                    self._add_row(
                        "🔒",
                        f"{fl_tag}{nh['name']}（水平距离 {nh['dist']}m）",
                        sub=f"当前无法获得 · 缺前置：{'、'.join(nh['missing_reqs'])}{radar_s}",
                        badge_tag="badge_red",
                        sub_tag="sub_red",
                        sub2=g_sub2,
                    )
                elif nh["kind"] == "bean_soil":
                    b_tag = "badge_red" if nh.get("tier") == "must" else ("badge_amber" if nh.get("need_plant") else "badge_green")
                    self._add_row(
                        "🌱",
                        f"{nh['name']}（水平距离 {nh['dist']}m）",
                        sub=nh["guide"],
                        badge_tag=b_tag,
                        sub_tag="sub_amber" if nh.get("need_plant") else "sub_dim",
                    )
                else:
                    b = "🕳" if nh["kind"] == "grotto" else ("🕷" if nh["kind"] == "skulltula" else "❤")
                    base_sub = "可立刻获取" if nh["kind"] != "grotto" else "隐藏洞穴"
                    self._add_row(
                        b,
                        f"{fl_tag}{nh['name']}（水平距离 {nh['dist']}m）",
                        sub=f"{base_sub}{radar_s}",
                        badge_tag="badge_green" if nh["kind"] != "grotto" else "badge_blue",
                        sub_tag="sub_amber",
                        sub2=g_sub2,
                    )

        # 0.6 Regional soft-soil Magic Bean guidance (helps decide whether to plant beans in Child form)
        bean_tips = ev["get_bean_tips"](loc) if "get_bean_tips" in ev else []
        if bean_tips:
            self._add_section_header("🌱 本区软土坑 · 是否需要种魔法豆", "hdr_green")
            for bt in bean_tips:
                b_tag = "badge_red" if bt["tier"] == "must" else ("badge_amber" if bt["tier"] == "opt" else "badge_green")
                self._add_row(
                    "🌱",
                    f"{bt['name']}：{bt['badge']}",
                    sub=bt["why"],
                    badge_tag=b_tag,
                    sub_tag="sub_amber" if bt["need_plant"] else "sub_dim",
                )

        # 1. Reachable missing (will trigger warning if left behind!)
        reach_miss = reg.skull_reachable_missing + reg.hp_reachable_missing + reg.quest_reachable_missing
        if reach_miss:
            self._add_section_header(f"🟠 当前可补（{len(reach_miss)} 项 · 离开本区未拿将提醒）", "hdr_amber")
            for it in reach_miss:
                if it.kind == "skulltula":
                    badge, btag = "🕷", "badge_amber"
                elif it.kind == "heart_piece":
                    badge, btag = "❤", "badge_red"
                else:
                    badge, btag = "⭐", "badge_purple"
                sub = "🌙 仅限夜晚出现（可吹太阳之歌或等天黑）" if it.night_only else ""
                sub2 = f"↳ 怎么去：{it.guide}" if it.guide else ""
                fl_p = f"[{it.floor}] " if getattr(it, "floor", "") else ""
                self._add_row(badge, f"{fl_p}{it.name}", sub=sub, badge_tag=btag, sub2=sub2)
        else:
            self._add_section_header("✅ 本区当前可获得项已全部收齐！", "hdr_green")

        # 1.5 Adjacent / Border / Connected-Route Reachable Items
        adj_miss = ev["get_adjacent"](loc) if "get_adjacent" in ev else ev.get("adjacent_miss", [])
        if adj_miss:
            self._add_section_header(f"🔗 门外紧邻 / 相连顺路可拿（{len(adj_miss)} 项）", "hdr_blue")
            for hint, it in adj_miss:
                ktag = "🕷" if it.kind == "skulltula" else ("❤" if it.kind == "heart_piece" else "⭐")
                loc_zh = ev["regions"][it.location].name_zh if it.location in ev["regions"] else it.location
                sub_txt = f"↳ 怎么去（{loc_zh}）：{hint}"
                if it.night_only:
                    sub_txt += " · 🌙需夜晚"
                self._add_row("🔗", f"{ktag} {it.name}", sub=sub_txt, badge_tag="badge_blue", sub_tag="sub_guide")

        # 2. Temporarily unreachable (red dot + highlighted prerequisites + how-to-get)
        unreach = reg.skull_unreachable + reg.hp_unreachable + reg.quest_unreachable
        if unreach:
            self._add_section_header(f"● 暂时无法获得（{len(unreach)} 项 · 离开不提醒）", "hdr_red")
            for it in unreach:
                ktag = "蜘蛛" if it.kind == "skulltula" else ("心片" if it.kind == "heart_piece" else "支线")
                req_txt = "⚠ 缺前置：" + "、".join(it.missing_reqs)
                if it.night_only:
                    req_txt += "（且需夜晚）"
                guide_parts = []
                if it.missing_guides:
                    guide_parts.append("前置获取：" + "；".join(it.missing_guides))
                if it.guide:
                    guide_parts.append("任务路线：" + it.guide)
                sub2 = "↳ " + "｜".join(guide_parts) if guide_parts else ""
                fl_u = f"[{it.floor}] " if getattr(it, "floor", "") else ""
                self._add_row(
                    "●",
                    f"[{ktag}] {fl_u}{it.name}",
                    sub=req_txt,
                    badge_tag="badge_red",
                    text_tag="item_fg",
                    sub_tag="sub_amber",
                    sub2=sub2,
                )

        # 3. Completed
        done = reg.skull_collected + reg.hp_collected + reg.quest_collected
        if done:
            self._add_section_header(f"✔ 本区已收集 / 已完成（{len(done)} 项）", "hdr_green")
            for it in done:
                self._add_row("✔", it.name, badge_tag="badge_green", text_tag="item_dim")

    def _render_quests_tab(self, ev: dict):
        # 0. Active Multi-Step Trading Chains (pinned at top when in progress)
        for ch in ev.get("active_chains", []):
            where = "✅ 已在目标区域" if ch["in_target"] else f"📍 前往：{ch['target_zh']}"
            rm = f"\n↳ 完整路线：{ch['roadmap']}" if ch.get("roadmap") else ""
            self._add_row(
                ch["badge"],
                f"正在推进：{ch['header']}｜{ch['title']}",
                sub=where,
                badge_tag="badge_red" if ch["timed"] else "badge_amber",
                sub_tag="sub_red" if ch["timed"] else "sub_amber",
                sub2=f"↳ 怎么做：{ch['detail']}{rm}",
            )

        # 1. ALL currently reachable uncollected collectibles across ALL of Hyrule — expanded right at the top!
        #    (So the player can clear every reachable Skulltula, Heart Piece, and Side Quest before advancing Main Story without visiting each map first!)
        curr_loc = ev["location"]
        pending_regs = [
            r for r in ev["regions"].values()
            if r.location not in ("DreamWorld", "IngoRanch") and r.reachable_missing_count > 0
        ]
        pending_regs.sort(
            key=lambda r: (
                0 if r.location == curr_loc else 1,
                -r.reachable_missing_count,
            )
        )
        total_reach_all = sum(r.reachable_missing_count for r in pending_regs)
        if pending_regs:
            self._add_section_header(
                f"🟠 全海拉鲁当前可补清单（共 {total_reach_all} 项 · 全部展开 · 无需跑图即可查看拿法）",
                "hdr_amber",
            )
            for r in pending_regs:
                loc_tag = "【当前所在区域】" if r.location == curr_loc else f"（蜘蛛 {r.skull_got}/{r.skull_total} · 心之碎片 {r.hp_got}/{r.hp_total}）"
                self._add_section_header(
                    f"▸ 📍 {r.name_zh} — 当前可补 {r.reachable_missing_count} 项 {loc_tag}",
                    "hdr_blue" if r.location == curr_loc else "hdr_amber",
                )
                reach_items = r.skull_reachable_missing + r.hp_reachable_missing + r.quest_reachable_missing
                for it in reach_items:
                    if it.kind == "skulltula":
                        badge, btag, klabel = "🕷", "badge_amber", "黄金骷髅蜘蛛"
                    elif it.kind == "heart_piece":
                        badge, btag, klabel = "❤", "badge_red", "心之碎片"
                    else:
                        badge, btag, klabel = "⭐", "badge_purple", "支线/道具"
                    fl_p = f"[{it.floor}] " if getattr(it, "floor", "") else ""
                    sub = "🌙 仅限夜晚出现（可吹太阳之歌或等天黑）" if it.night_only else ""
                    sub2 = f"↳ 怎么拿：{it.guide}" if it.guide else ""
                    self._add_row(
                        badge,
                        f"[{r.name_zh} · {klabel}] {fl_p}{it.name}",
                        sub=sub,
                        badge_tag=btag,
                        sub_tag="sub_amber",
                        sub2=sub2,
                    )
        else:
            self._add_section_header(
                "✅ 全海拉鲁当前阶段可收集项已 100% 拿齐！可安心推进主线！",
                "hdr_green",
            )

        # 2. Active Main Story + Milestones
        self._add_story_card(ev["story"])
        self._add_section_header("🏁 主线里程碑进度", "hdr_blue")
        for mname, mdone in ev["story"]["milestones"]:
            self._add_row(
                "✔" if mdone else "○",
                mname,
                badge_tag="badge_green" if mdone else "badge_amber",
                text_tag="item_dim" if mdone else "item_fg",
            )

        # 3. Temporarily Locked Quests (red dot + highlighted prerequisites + how-to-get + route)
        quests = [x for x in ev["all_items"] if x.kind == "quest"]
        locked_q = [x for x in quests if not x.collected and not x.reachable]
        done_q = [x for x in quests if x.collected]

        if locked_q:
            self._add_section_header(f"● 暂缺前置支线 / 成长（{len(locked_q)} 项）", "hdr_red")
            for it in locked_q:
                loc_zh = self.db["locations"].get(it.location, it.location)
                guide_parts = []
                if it.missing_guides:
                    guide_parts.append("前置获取：" + "；".join(it.missing_guides))
                if it.guide:
                    guide_parts.append("后续路线：" + it.guide)
                self._add_row(
                    "●",
                    f"[{loc_zh}] {it.name}",
                    sub="⚠ 缺前置：" + "、".join(it.missing_reqs),
                    badge_tag="badge_red",
                    text_tag="item_fg",
                    sub_tag="sub_amber",
                    sub2="↳ " + "｜".join(guide_parts) if guide_parts else "",
                )

        # 4. Completed Quests — Default-Collapsed Green Toggle Bar at the bottom
        if done_q:
            arrow = "▾" if self._show_completed_quests else "▸"
            act_txt = "点击收起" if self._show_completed_quests else "点击展开查看"
            self._add_collapsible_green_header(
                "toggle_done_quests",
                f"{arrow} ✔ 已完成支线 / 成长归档（{len(done_q)} 项 · {act_txt}）",
                self._toggle_completed_quests,
            )
            if self._show_completed_quests:
                for it in done_q:
                    loc_zh = self.db["locations"].get(it.location, it.location)
                    self._add_row("✔", f"[{loc_zh}] {it.name}", badge_tag="badge_green", text_tag="item_dim")

    def _render_boss_and_log_tab(self, ev: dict):
        active_boss = ev.get("active_boss")
        if active_boss:
            self._add_active_boss_card(active_boss)
        elif ev.get("final_battle_stage") in ("escape", "victory"):
            self._add_final_stage_card(ev.get("final_battle_stage"))
        self._add_story_card(ev["story"])

        bj = ev.get("boss_journal") or {}
        unlocked_undefeated = bj.get("unlocked_undefeated", [])
        defeated_bosses = bj.get("defeated", [])
        locked_count = bj.get("locked_count", 0)
        active_tips = bj.get("active_tips", {})

        # 1. Unlocked & Undefeated Bosses (unlocked ONLY when Main Story triggers their dungeon or player approaches/enters)
        pending_bosses = [b for b in unlocked_undefeated if not (active_boss and active_boss["id"] == b["id"])]
        self._add_section_header(
            f"⚔ 当前已解锁首领与中首领记录（待击败 {len(unlocked_undefeated)} 只 · 防剧透渐进解锁）",
            "hdr_purple",
        )
        if pending_bosses:
            for b in pending_bosses:
                loc_zh = self.db["locations"].get(b["location"], b["location"])
                tag_s = (
                    " 【当前区域】"
                    if b["location"] == ev["location"]
                    else (" 【主线目标】" if b["location"] == ev["story"]["target_loc"] else "")
                )
                self._add_unlocked_boss_card(b, loc_zh, tag_s)
        elif not active_boss:
            self._add_row(
                "✔",
                "当前已解锁的首领均已击败！",
                sub="当主线推进到下一个迷宫或靠近新首领房间时，会自动在此解锁对应首领攻略。",
                badge_tag="badge_green",
                text_tag="item_fg",
            )

        if locked_count > 0:
            self._add_row(
                "🔒",
                f"另有 {locked_count} 只后续迷宫首领 / 中首领记录未解锁（防剧透隐藏）",
                sub="触发对应主线阶段或进入对应迷宫后自动解锁显示",
                badge_tag="badge_blue",
                text_tag="item_dim",
            )

        # 2. Unlocked Active Dungeon Mechanic & Puzzle Tips
        if active_tips:
            self._add_section_header("🧩 当前已解锁迷宫机关与解谜要点", "hdr_amber")
            for loc, tips in active_tips.items():
                loc_zh = self.db["locations"].get(loc, loc)
                tag = "【当前位置】" if loc == ev["location"] else ("【当前主线】" if loc == ev["story"]["target_loc"] else "")
                self._add_section_header(f"▸ {loc_zh} {tag}", "hdr_blue" if tag else "hdr_amber")
                for btitle, bdesc in tips:
                    self._add_row("⚔", btitle, sub=f"↳ {bdesc}", badge_tag="badge_purple", text_tag="item_fg", sub_tag="sub_guide")

        # 3. Defeated Bosses Archive — Default-Collapsed Green Toggle Bar at the bottom (just like green completed quests!)
        if defeated_bosses:
            arrow = "▾" if self._show_defeated_bosses else "▸"
            act_txt = "点击收起" if self._show_defeated_bosses else "点击展开回顾打法"
            self._add_collapsible_green_header(
                "toggle_defeated_bosses",
                f"{arrow} ✔ 已击败首领与中首领归档（{len(defeated_bosses)} 只 · {act_txt}）",
                self._toggle_defeated_bosses,
            )
            if self._show_defeated_bosses:
                for b in defeated_bosses:
                    loc_zh = self.db["locations"].get(b["location"], b["location"])
                    kind_lbl = "中首领" if b.get("is_miniboss") else "迷宫首领"
                    self._add_row(
                        "✔",
                        f"[{loc_zh} · {kind_lbl}] {b['name_zh']}（已击败）",
                        sub=f"有效道具：{b['valid_items']}｜娜薇提示：{b['navi_hint']}",
                        badge_tag="badge_green",
                        text_tag="item_dim",
                        sub_tag="sub_dim",
                        sub2="↳ " + " ".join(b["tactics"]),
                    )

        self._add_section_header("📜 近期动态提醒记录", "hdr_blue")
        if not self.alert_history:
            self._add_row("…", "暂无变化记录", badge_tag="badge_blue", text_tag="item_dim")
            return
        for ts, al in self.alert_history[:20]:
            btag = "badge_green" if al.level == "good" else ("badge_red" if al.level == "warn" else "badge_blue")
            self._add_row(ts[:5], al.title, sub=al.detail, badge_tag=btag)

    def _select_amiibo_idx(self, idx: int):
        if not self.amiibo_cards:
            return
        self.amiibo_idx = idx % len(self.amiibo_cards)
        self._refresh_display(force=True)
        if self.fs_hidden and not self.fs_manual_peek and self.last_eval:
            self._render_distributed_hud(self.last_eval, self._fs_monitor_rect, force=True)

    def _render_amiibo_tab(self):
        cards = self.amiibo_cards
        used = self.amiibo_used_today
        supply_total = sum(1 for c in cards if c["daily_limit"])
        supply_left = sum(1 for c in cards if c["daily_limit"] and c["key"] not in used)
        self._add_section_header(
            f"🎁 Amiibo 刷卡清单（共 {len(cards)} 张 · 今日补给剩余 {supply_left}/{supply_total} 张）",
            "hdr_amber",
        )
        if cards:
            cur = cards[self.amiibo_idx % len(cards)]
            cur_status = (
                "二选一替换面具" if not cur["daily_limit"]
                else ("✔ 今日已刷过" if cur["key"] in used else "● 今日可刷")
            )
            self.view.insert(
                tk.END,
                f"▶ 当前指定（第 {self.amiibo_idx + 1}/{len(cards)} 张 · {cur_status}）：{cur['name']} [{cur['file_name']}]\n",
                "story_stage",
            )
            self.view.insert(tk.END, f"真实掉落：{cur['reward_short']}\n", "story_title")
            east = self._east_btn_name()
            nav_desc = "【触控板←→】" if getattr(self.gamepad.last_snap, "kind", "none") == "ps5" else "【R3+←→】"
            step_desc = "【触控板↑↓】" if getattr(self.gamepad.last_snap, "kind", "none") == "ps5" else "【R3+↑↓】"
            self.view.insert(
                tk.END,
                f"{cur['reward_detail']}\n操作：游戏内打开「呼唤 amiibo」后，按手柄【L3+{east}】立即载入；{nav_desc}快速切换两张面具，{step_desc}或点击卡片指定任意一张。\n",
                "story_route",
            )
            self.view.insert(tk.END, "\n", "sep")
        else:
            self._add_row(
                "ℹ",
                "暂未检测到 Amiibo .bin 文件",
                sub="可将 .bin 放入本目录 amiibo/ 文件夹，或启动游戏后自动读取 NX2navi\\amiibo / Fritchii\\user\\amiibo。",
                badge_tag="badge_amber",
                sub_tag="sub_guide",
            )

        self._add_section_header("🎭 独占面具卡（二选一覆盖替换 · 触控板 / R3+←→ 快切 · 无每日限制）", "hdr_purple")
        for idx, c in enumerate(cards):
            if c["category"] != "mask":
                continue
            is_sel = idx == self.amiibo_idx
            mark = "▶" if is_sel else "🎭"
            btag = "badge_amber" if is_sel else "badge_purple"
            rtag = f"amiibo_pick_{idx}"
            s_idx = self.view.index(tk.END)
            self._add_row(
                mark,
                f"{c['name']}  ({c['file_name']})",
                sub=f"{c['reward_short']} · 点击或触控板←→切换",
                badge_tag=btag,
                text_tag="item_fg",
                sub_tag="sub_amber" if is_sel else "sub_dim",
                sub2=c["reward_detail"],
            )
            e_idx = self.view.index(tk.END)
            self.view.tag_add(rtag, s_idx, e_idx)
            self.view.tag_bind(rtag, "<Button-1>", lambda _e, i=idx: self._select_amiibo_idx(i))

        self._add_section_header("🎒 塞尔达系列每日补给卡（按文件标号排序 · 已刷过有标注）", "hdr_blue")
        for idx, c in enumerate(cards):
            if c["category"] != "supply":
                continue
            is_used = c["key"] in used
            is_sel = idx == self.amiibo_idx
            mark = "▶" if is_sel else ("✔" if is_used else "●")
            btag = "badge_amber" if is_sel else ("badge_green" if is_used else "badge_blue")
            ttag = "item_dim" if (is_used and not is_sel) else "item_fg"
            st = (
                f"✔ 今日已刷过 | 文件：{c['file_name']}"
                if is_used
                else f"● 今日可刷 · {c['reward_short']} | 文件：{c['file_name']}"
            )
            rtag = f"amiibo_pick_{idx}"
            s_idx = self.view.index(tk.END)
            self._add_row(mark, f"{c['name']}  ({c['en_name']})", sub=st, badge_tag=btag, text_tag=ttag)
            e_idx = self.view.index(tk.END)
            self.view.tag_add(rtag, s_idx, e_idx)
            self.view.tag_bind(rtag, "<Button-1>", lambda _e, i=idx: self._select_amiibo_idx(i))

    def run(self):
        self.root.mainloop()


def main(argv: list[str] | None = None, **_kwargs):
    args = list(sys.argv[1:] if argv is None else argv)
    update_notice = _kwargs.get("update_notice")
    skip_upd = ("--no-update" in args) or (update_notice is not None and getattr(update_notice, "status", "") == "updated")
    hud = OoTOverlayHUD(auto_update=not skip_upd)
    if update_notice is not None and getattr(update_notice, "status", "") == "updated":
        src_zh = "Gitee" if getattr(update_notice, "source", "") == "gitee" else "GitHub"
        files = getattr(update_notice, "updated_files", [])
        kb = max(1, int(getattr(update_notice, "total_bytes", 0)) // 1024)
        ver = getattr(update_notice, "remote_version", hud._app_version)
        notes = getattr(update_notice, "notes", "")
        al = TrackerAlert(
            "good",
            f"✔ 已从 {src_zh} 热更新至 v{ver}（{len(files)} 文件 / {kb} KB）",
            notes or "已同步最新代码",
        )
        hud.alert_history.insert(0, (datetime.now().strftime("%H:%M:%S"), al))
        hud._show_banner(al, hold_sec=6.0)
    if "--minimized" in args:
        hud.root.after(60, hud._minimize_window)
    hud.run()


if __name__ == "__main__":
    main(sys.argv[1:])
