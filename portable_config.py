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
}


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if not CONFIG_PATH.is_file():
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            for k in DEFAULT_CONFIG:
                if k in raw:
                    cfg[k] = raw[k]
    except Exception:
        pass
    return cfg
