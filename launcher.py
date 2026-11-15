"""Frontend launcher: instant HUD startup with Win32 DPI/AppID init and safe crash reporting."""
from __future__ import annotations

import ctypes
import importlib
from pathlib import Path
import sys
import traceback

_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


def _init_win_identity():
    try:
        ctypes.WinDLL("user32", use_last_error=True).SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    try:
        ctypes.WinDLL("shell32", use_last_error=True).SetCurrentProcessExplicitAppUserModelID("CSSZYF.OoTSwitch2Tracker.1")
    except Exception:
        pass


def main(argv: list[str] | None = None):
    _init_win_identity()
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        overlay_hud = importlib.import_module("overlay_hud")
        if hasattr(overlay_hud, "main"):
            overlay_hud.main(args)
        else:
            hud = overlay_hud.OoTOverlayHUD()
            if "--minimized" in args:
                hud.root.after(60, hud._minimize_window)
            hud.run()
    except Exception:
        tb = traceback.format_exc()
        try:
            (_APP_DIR / "crash.log").write_text(tb, encoding="utf-8")
        except Exception:
            pass
        try:
            ctypes.WinDLL("user32").MessageBoxW(
                None,
                f"启动失败，详细信息已写入 crash.log：\n\n{tb[-600:]}",
                "时之笛进度助手",
                0x10,
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
