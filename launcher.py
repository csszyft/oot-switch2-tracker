"""Thin Frontend Launcher: fast GitHub/Gitee pure-code hot-update before starting OoT Overlay HUD."""
from __future__ import annotations

import ctypes
import importlib
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from auto_updater import UpdateResult, check_and_apply_updates, load_local_manifest
from portable_config import APP_DIR, BUNDLE_DIR, load_config

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_BACKEND_MODULES = (
    "overlay_hud",
    "tracker_engine",
    "save_reader",
    "gamepad_ctrl",
    "amiibo_helper",
    "win_proc",
    "portable_config",
)


def _init_win_identity():
    try:
        _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    try:
        _shell32.SetCurrentProcessExplicitAppUserModelID("CSSZYF.OoTSwitch2Tracker.1")
    except Exception:
        pass


def _find_ico_path() -> Path | None:
    for base in (APP_DIR, _APP_DIR, BUNDLE_DIR):
        p = base / "triforce.ico"
        if p.is_file():
            return p
    return None


def _draw_triforce_canvas(canvas: tk.Canvas, size: int = 44):
    cx = size / 2.0
    cy = size / 2.0 + 2.0
    h = size * 0.70
    hw = h / 1.73205
    top = (cx, cy - h * 0.56)
    bl = (cx - hw, cy + h * 0.44)
    br = (cx + hw, cy + h * 0.44)
    ml = ((top[0] + bl[0]) / 2.0, (top[1] + bl[1]) / 2.0)
    mr = ((top[0] + br[0]) / 2.0, (top[1] + br[1]) / 2.0)
    mb = ((bl[0] + br[0]) / 2.0, (bl[1] + br[1]) / 2.0)
    for tri in ((top, ml, mr), (ml, bl, mb), (mr, mb, br)):
        flat = [coord for pt in tri for coord in pt]
        canvas.create_polygon(flat, fill="#F2C968", outline="#FFE9A3", width=1)


def _run_splash_updater(cfg: dict) -> UpdateResult | None:
    local_m = load_local_manifest(APP_DIR)
    loc_ver = str(local_m.get("version") or "1.2.0")

    root = tk.Tk()
    root.title("时之笛进度助手 · 启动器")
    root.overrideredirect(True)
    root.configure(bg="#D8B467")
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.96)
    except Exception:
        pass

    ico = _find_ico_path()
    if ico is not None:
        try:
            root.iconbitmap(default=str(ico))
        except Exception:
            pass

    w, h = 408, 152
    sw = max(800, root.winfo_screenwidth())
    sh = max(600, root.winfo_screenheight())
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    card = tk.Frame(root, bg="#0D1218")
    card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    top_row = tk.Frame(card, bg="#111720")
    top_row.pack(fill=tk.X)

    cv = tk.Canvas(top_row, width=44, height=44, bg="#111720", highlightthickness=0)
    cv.pack(side=tk.LEFT, padx=(12, 8), pady=8)
    _draw_triforce_canvas(cv, 44)

    title_col = tk.Frame(top_row, bg="#111720")
    title_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=8)
    tk.Label(
        title_col,
        text=f"塞尔达传说：时之笛进度助手  v{loc_ver}",
        bg="#111720",
        fg="#FFD86B",
        font=("Microsoft YaHei UI", 10, "bold"),
        anchor="w",
    ).pack(fill=tk.X)
    tk.Label(
        title_col,
        text="前端启动器 · GitHub / Gitee 双源纯代码热更新",
        bg="#111720",
        fg="#9AA5B4",
        font=("Microsoft YaHei UI", 8),
        anchor="w",
    ).pack(fill=tk.X, pady=(1, 0))

    status_var = tk.StringVar(value="正在并行检测 GitHub / Gitee 上游代码更新…")
    tk.Label(
        card,
        textvariable=status_var,
        bg="#0D1218",
        fg="#F4EFE4",
        font=("Microsoft YaHei UI", 9),
        anchor="w",
        wraplength=380,
        justify=tk.LEFT,
    ).pack(fill=tk.X, padx=14, pady=(10, 6))

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        "Triforce.Horizontal.TProgressbar",
        troughcolor="#151C25",
        background="#F2C968",
        bordercolor="#151C25",
        lightcolor="#FFD86B",
        darkcolor="#D8B467",
        thickness=6,
    )
    pbar = ttk.Progressbar(card, mode="indeterminate", style="Triforce.Horizontal.TProgressbar")
    pbar.pack(fill=tk.X, padx=14, pady=(0, 8))
    pbar.start(14)

    btn_row = tk.Frame(card, bg="#0D1218")
    btn_row.pack(fill=tk.X, padx=14, pady=(0, 8))
    hint_lbl = tk.Label(
        btn_row,
        text="仅检查纯代码与数据库（毫秒级热同步）",
        bg="#0D1218",
        fg="#7F8C9D",
        font=("Microsoft YaHei UI", 8),
        anchor="w",
    )
    hint_lbl.pack(side=tk.LEFT)

    state: dict[str, object] = {
        "done": False,
        "skipped": False,
        "result": None,
        "progress_msg": "正在并行检测 GitHub / Gitee 上游代码更新…",
    }
    lock = threading.Lock()
    cancel_evt = threading.Event()

    def _on_skip():
        cancel_evt.set()
        with lock:
            state["skipped"] = True
        try:
            pbar.stop()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

    tk.Button(
        btn_row,
        text="跳过并启动",
        command=_on_skip,
        bg="#1B2330",
        fg="#DCE7F5",
        activebackground="#26324B",
        activeforeground="#FFD86B",
        bd=0,
        relief=tk.FLAT,
        font=("Microsoft YaHei UI", 8),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side=tk.RIGHT)

    def _on_prog(msg: str):
        with lock:
            state["progress_msg"] = msg

    def _worker():
        res = check_and_apply_updates(APP_DIR, cfg, cancel_event=cancel_evt, on_progress=_on_prog)
        with lock:
            state["result"] = res
            state["done"] = True

    threading.Thread(target=_worker, daemon=True).start()

    finished_at: float | None = None
    close_delay = 0.20

    def _tick():
        nonlocal finished_at, close_delay
        with lock:
            skipped = bool(state["skipped"])
            done = bool(state["done"])
            res: UpdateResult | None = state["result"]  # type: ignore[assignment]
            pmsg = str(state["progress_msg"])
        if skipped:
            return
        if not done:
            status_var.set(pmsg)
            root.after(60, _tick)
            return
        if finished_at is None:
            finished_at = time.monotonic()
            try:
                pbar.stop()
                pbar.configure(mode="determinate", maximum=100, value=100)
            except Exception:
                pass
            if res and res.status == "updated":
                src_zh = "Gitee" if res.source == "gitee" else "GitHub"
                status_var.set(
                    f"✔ 已从 {src_zh} 热更新 {len(res.updated_files)} 个文件至 v{res.remote_version}，正在启动…"
                )
                close_delay = 0.55
            elif res and res.status == "up_to_date":
                src_zh = "Gitee" if res.source == "gitee" else "GitHub"
                status_var.set(f"✔ 已是最新版 v{res.local_version}（{src_zh} {int(res.latency_ms)}ms），正在启动…")
                close_delay = 0.18
            else:
                status_var.set(f"● 使用本地版本 v{loc_ver} 直接启动…")
                close_delay = 0.15
            root.after(60, _tick)
            return
        if time.monotonic() - finished_at >= close_delay:
            try:
                root.destroy()
            except Exception:
                pass
            return
        root.after(60, _tick)

    root.after(60, _tick)
    root.mainloop()
    with lock:
        return state["result"]  # type: ignore[return-value]


def _purge_backend_modules():
    for mod_name in _BACKEND_MODULES:
        sys.modules.pop(mod_name, None)
    importlib.invalidate_caches()


def main(argv: list[str] | None = None):
    _init_win_identity()
    args = list(sys.argv[1:] if argv is None else argv)
    no_update = "--no-update" in args
    no_splash = "--no-splash" in args or "--minimized" in args
    forward_args = [a for a in args if a not in ("--no-update", "--no-splash")]

    cfg = load_config()
    update_res: UpdateResult | None = None
    if not no_update and bool(cfg.get("auto_update", True)):
        if no_splash:
            update_res = check_and_apply_updates(APP_DIR, cfg)
        else:
            update_res = _run_splash_updater(cfg)

    # Clear cached backend modules so any hot-updated .py files on disk are loaded fresh
    _purge_backend_modules()
    overlay_hud = importlib.import_module("overlay_hud")
    if hasattr(overlay_hud, "main"):
        overlay_hud.main(forward_args, update_notice=update_res)
    else:
        hud = overlay_hud.OoTOverlayHUD()
        if "--minimized" in forward_args:
            hud.root.after(60, hud._minimize_window)
        hud.run()


if __name__ == "__main__":
    main()
