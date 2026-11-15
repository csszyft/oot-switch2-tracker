"""Portable configuration loader for tracker_config.json."""
import json
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
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
