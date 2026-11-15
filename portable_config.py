"""Portable configuration loader for tracker_config.json."""
import json
from pathlib import Path
import sys
from typing import Any

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = APP_DIR
CONFIG_PATH = APP_DIR / "tracker_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "save_dir": "",
    "amiibo_dir": "",
    "slot": "auto",
    "fs_mode": "distributed",
    "sound_enabled": True,
    "auto_update": True,
    "github_repo": "csszyft/oot-switch2-tracker",
    "gitee_repo": "csszyf/oot-switch2-tracker",
    "update_branch": "main",
    "update_timeout_sec": 3.0,
    "font_scale": 1.0,
    "manual_fullscreen_hud": False,
    "hud_clickthrough": True,
    "window_rect": None,
    "hud_layout": {},
}


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    p = config_path or CONFIG_PATH
    cfg = dict(DEFAULT_CONFIG)
    cfg["hud_layout"] = {}
    if not p.is_file():
        return cfg
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            for k in DEFAULT_CONFIG:
                if k in raw:
                    if k == "hud_layout" and isinstance(raw[k], dict):
                        cfg[k] = {str(mk): list(mv) for mk, mv in raw[k].items() if isinstance(mv, list)}
                    else:
                        cfg[k] = raw[k]
    except Exception:
        pass
    try:
        cfg["font_scale"] = round(max(0.8, min(1.6, float(cfg.get("font_scale", 1.0)))), 2)
    except Exception:
        cfg["font_scale"] = 1.0
    return cfg


def save_config(cfg: dict[str, Any], config_path: Path | None = None) -> bool:
    p = config_path or CONFIG_PATH
    try:
        existing: dict[str, Any] = {}
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    existing = raw
            except Exception:
                existing = {}
        out: dict[str, Any] = {}
        for k in DEFAULT_CONFIG:
            if k in cfg:
                out[k] = cfg[k]
            elif k in existing:
                out[k] = existing[k]
            else:
                out[k] = DEFAULT_CONFIG[k]
        for k, v in existing.items():
            if k not in out:
                out[k] = v
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return True
    except Exception:
        return False
