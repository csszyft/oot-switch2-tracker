"""Minimal thin PyInstaller frontend bootloader.
Pre-bundles Python stdlib + tkinter, ensures external pure-code files exist in APP_DIR,
and dynamically executes APP_DIR/launcher.py so GitHub/Gitee pure-code updates take effect immediately.
"""
# Explicit stdlib pre-imports so PyInstaller bundles complete stdlib support for hot-updated backend code
import atexit  # noqa: F401
import base64  # noqa: F401
import binascii  # noqa: F401
import collections  # noqa: F401
from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: F401
import copy  # noqa: F401
import ctypes  # noqa: F401
from ctypes import wintypes  # noqa: F401
import dataclasses  # noqa: F401
from datetime import date, datetime  # noqa: F401
import difflib  # noqa: F401
import enum  # noqa: F401
import functools  # noqa: F401
import gzip  # noqa: F401
import hashlib  # noqa: F401
import hmac  # noqa: F401
import importlib  # noqa: F401
import importlib.util  # noqa: F401
import io  # noqa: F401
import itertools  # noqa: F401
import json  # noqa: F401
import math  # noqa: F401
import os  # noqa: F401
from pathlib import Path
import re  # noqa: F401
import shutil
import socket  # noqa: F401
import ssl  # noqa: F401
import struct  # noqa: F401
import subprocess  # noqa: F401
import sys
import tempfile  # noqa: F401
import threading  # noqa: F401
import time  # noqa: F401
import tkinter as tk  # noqa: F401
from tkinter import ttk  # noqa: F401
from typing import Any  # noqa: F401
import urllib.error  # noqa: F401
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401
import uuid  # noqa: F401
import winsound  # noqa: F401
import zipfile  # noqa: F401
import zlib  # noqa: F401


def _seed_missing_files(app_dir: Path, bundle_dir: Path):
    seed_dir = bundle_dir / "_seed"
    if not seed_dir.is_dir():
        return
    for src in seed_dir.iterdir():
        if not src.is_file():
            continue
        dst = app_dir / src.name
        if not dst.exists():
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass


def main():
    try:
        ctypes.WinDLL("user32").SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    try:
        ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID("CSSZYF.OoTSwitch2Tracker.1")
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        bundle_dir = Path(getattr(sys, "_MEIPASS", app_dir))
    else:
        app_dir = Path(__file__).resolve().parent
        bundle_dir = app_dir

    _seed_missing_files(app_dir, bundle_dir)

    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    launcher_path = app_dir / "launcher.py"
    if not launcher_path.is_file():
        launcher_path = bundle_dir / "_seed" / "launcher.py"

    spec = importlib.util.spec_from_file_location("launcher", str(launcher_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load launcher from {launcher_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["launcher"] = mod
    spec.loader.exec_module(mod)
    mod.main(sys.argv[1:])


if __name__ == "__main__":
    main()
