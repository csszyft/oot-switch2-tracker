"""Amiibo catalog, Switch 2 OoT reward database, daily cooldown tracker, and zero-menu NX2navi / Fritchii NFC loaders (Portable)."""
import ctypes
from ctypes import wintypes
from datetime import date
import json
import os
from pathlib import Path
import struct
import time

from portable_config import APP_DIR, load_config
from win_proc import iter_processes, pid_exists

DEFAULT_AMIIBO_DIR = APP_DIR / "amiibo"
DAILY_LOG_PATH = APP_DIR / "amiibo_daily_log.json"

SUPPLY_REWARD_SHORT = "红心·魔力瓶·炸弹/鼠·箭/种子 + 稀有【小贩果坚果】"
SUPPLY_REWARD_DETAIL = (
    "冒险补给池（每日每卡限1次，每次随机3～5个）："
    "红心(8x高概率)、小魔力瓶(4x)、炸弹/炸弹鼠/箭矢/德库种子/木棒/坚果(各2x)、"
    "【小贩果坚果】(1x稀有，装备后空旷处呼唤德库商人购买补给)。"
)

MASK_REWARDS = {
    "1277": (
        "妖精之子面具 (1277)",
        "🎭 必掉【妖精之子面具】（二选一替换 · 覆盖公主面具）",
        "官方说明：使人联想到科奇里森林的神奇面具。注意：两张独占面具不可同时持有，每刷一次会覆盖替换另一张！无每日限制，可随时切换。",
    ),
    "1279": (
        "公主面具 (1279)",
        "👑 必掉【公主面具】（二选一替换 · 覆盖妖精之子面具）",
        "官方说明：使人联想到海拉鲁城堡中庭相遇的神奇面具。注意：两张独占面具不可同时持有，每刷一次会覆盖替换另一张！无每日限制，可随时切换。",
    ),
}

SUPPLY_NAME_MAP = {
    "8-bit link": "8-Bit 像素林克",
    "bokoblin": "波克布林",
    "daruk": "达尔克尔（鼓隆英杰）",
    "ganondorf (smash)": "大乱斗 加农多夫",
    "guardian": "守护者",
    "link (link_s awakening)": "织梦岛林克",
    "link (link's awakening)": "织梦岛林克",
    "link (majora_s mask)": "梅祖拉的假面林克",
    "link (majora's mask)": "梅祖拉的假面林克",
    "link (ocarina of time)": "时之笛林克",
    "link (skyward sword)": "御天之剑林克",
    "link (smash)": "大乱斗 林克",
    "link (twilight princess)": "黄昏公主林克",
    "link (wind waker)": "风之杖林克",
    "link archer (breath of the wild)": "旷野之息 弓箭林克",
    "link rider (breath of the wild)": "旷野之息 骑马林克",
    "mipha": "米法（卓拉英杰）",
    "revali": "力巴尔（利特英杰）",
    "sheik (smash)": "大乱斗 希克",
    "toon link (smash)": "大乱斗 卡通林克",
    "urbosa": "乌尔波扎（格鲁德英杰）",
    "wolf link": "黄昏狼林克",
    "young link (smash)": "大乱斗 少年林克",
    "zelda (breath of the wild)": "旷野之息 塞尔达",
    "zelda (smash)": "大乱斗 塞尔达",
    "zelda (wind waker)": "风之杖塞尔达",
}

_AMIIBO_PROC_HINTS = {"ocarina.exe", "lichii", "hookshot.exe", "eden", "yuzu", "citron", "suyu"}


def _read_nx2navi_amiibo_dir(exe_dir: Path) -> Path | None:
    ini = exe_dir / "nx2navi.ini"
    if ini.is_file():
        try:
            for line in ini.read_text("utf-8", errors="ignore").splitlines():
                s = line.strip()
                if s.lower().startswith("amiibo_dir") and "=" in s:
                    val = s.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        cand = (exe_dir / val) if not Path(val).is_absolute() else Path(val)
                        if cand.is_dir() and any(cand.glob("*.bin")):
                            return cand
        except Exception:
            pass
    local_dir = exe_dir / "amiibo"
    if local_dir.is_dir() and any(local_dir.glob("*.bin")):
        return local_dir
    return None


def find_active_amiibo_dir() -> Path | None:
    """Auto-discover Amiibo .bin folder: config -> foreground/running emulator -> portable ./amiibo -> %APPDATA% -> legacy."""
    cfg_dir = load_config().get("amiibo_dir") or ""
    if cfg_dir:
        cand = Path(str(cfg_dir)).expanduser()
        if not cand.is_absolute():
            cand = APP_DIR / cand
        if cand.is_dir() and any(cand.glob("*.bin")):
            return cand

    fg_pid = _foreground_pid()
    found_dirs: list[tuple[int, Path]] = []
    for pid, nm, exe in iter_processes(_AMIIBO_PROC_HINTS):
        if not exe:
            continue
        exe_dir = Path(exe).resolve().parent
        is_fg = 0 if pid == fg_pid else 1
        if nm == "ocarina.exe":
            cand = _read_nx2navi_amiibo_dir(exe_dir)
            if cand:
                found_dirs.append((is_fg, cand))
        else:
            for sub in (exe_dir.parent / "user" / "amiibo", exe_dir / "user" / "amiibo", exe_dir / "amiibo"):
                if sub.is_dir() and any(sub.glob("*.bin")):
                    found_dirs.append((is_fg, sub))
                    break
    if found_dirs:
        found_dirs.sort(key=lambda x: x[0])
        return found_dirs[0][1]

    local_portable = APP_DIR / "amiibo"
    if local_portable.is_dir() and any(local_portable.glob("*.bin")):
        return local_portable

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        for emu in ("eden", "yuzu", "suyu", "citron"):
            cand = Path(appdata) / emu / "amiibo"
            if cand.is_dir() and any(cand.glob("*.bin")):
                return cand
        ryu_cand = Path(appdata) / "Ryujinx" / "system" / "amiibo"
        if ryu_cand.is_dir() and any(ryu_cand.glob("*.bin")):
            return ryu_cand

    return DEFAULT_AMIIBO_DIR if DEFAULT_AMIIBO_DIR.is_dir() else None


def _normalize_stem(stem: str) -> str:
    clean = stem.strip()
    for prefix in ("[补给+小贩果] ", "[独占面具-必掉] "):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    if " - " in clean and any(ord(ch) > 127 for ch in clean.split(" - ", 1)[0]):
        clean = clean.split(" - ", 1)[1].strip()
    return clean


def scan_amiibo_cards(amiibo_dir: Path | None = None) -> list[dict]:
    """Return sorted list of Amiibo cards: 2 swappable masks first (skipped in daily auto-next), 24 daily supply cards next."""
    folder = Path(amiibo_dir) if amiibo_dir else find_active_amiibo_dir()
    if folder is None or not folder.is_dir():
        return []
    cards: list[dict] = []
    for p in sorted(folder.glob("*.bin")):
        fname = p.name
        stem = p.stem
        low = fname.lower()
        if "1277" in low or "fairy_child_mask" in low or "fairy child mask" in low:
            zh_name, short_r, detail_r = MASK_REWARDS["1277"]
            cards.append({
                "key": "mask:1277",
                "file_name": fname,
                "en_name": stem,
                "name": zh_name,
                "path": str(p),
                "category": "mask",
                "daily_limit": False,
                "skip_auto": True,
                "reward_short": short_r,
                "reward_detail": detail_r,
                "sort_prio": 0,
            })
        elif "1279" in low or "princess_mask" in low or "princess mask" in low:
            zh_name, short_r, detail_r = MASK_REWARDS["1279"]
            cards.append({
                "key": "mask:1279",
                "file_name": fname,
                "en_name": stem,
                "name": zh_name,
                "path": str(p),
                "category": "mask",
                "daily_limit": False,
                "skip_auto": True,
                "reward_short": short_r,
                "reward_detail": detail_r,
                "sort_prio": 1,
            })
        else:
            eng = _normalize_stem(stem)
            zh = SUPPLY_NAME_MAP.get(eng.lower(), eng)
            cards.append({
                "key": f"supply:{eng.lower()}",
                "file_name": fname,
                "en_name": eng,
                "name": zh,
                "path": str(p),
                "category": "supply",
                "daily_limit": True,
                "skip_auto": False,
                "reward_short": SUPPLY_REWARD_SHORT,
                "reward_detail": SUPPLY_REWARD_DETAIL,
                "sort_prio": 2,
            })
    cards.sort(key=lambda c: (c["sort_prio"], c["en_name"].lower()))
    return cards


def _canonicalize_log_key(k: str) -> str:
    if k.startswith(("supply:", "mask:")):
        return k
    low = k.lower()
    if "1277" in low:
        return "mask:1277"
    if "1279" in low:
        return "mask:1279"
    eng = _normalize_stem(Path(k).stem).lower()
    return f"supply:{eng}"


def load_daily_used(log_path: Path = DAILY_LOG_PATH) -> set[str]:
    today = date.today().isoformat()
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
        if data.get("date") == today:
            return {_canonicalize_log_key(x) for x in data.get("used", [])}
    except Exception:
        pass
    return set()


def mark_daily_used(card_key: str, log_path: Path = DAILY_LOG_PATH) -> set[str]:
    today = date.today().isoformat()
    used = load_daily_used(log_path)
    used.add(_canonicalize_log_key(card_key))
    try:
        log_path.write_text(
            json.dumps({"date": today, "used": sorted(used)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return used


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi")
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
]
_k32.ReadProcessMemory.restype = wintypes.BOOL
_k32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
]
_k32.WriteProcessMemory.restype = wintypes.BOOL
_k32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
_k32.VirtualAllocEx.restype = ctypes.c_void_p
_k32.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
_k32.VirtualFreeEx.restype = wintypes.BOOL
_k32.CreateRemoteThread.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
]
_k32.CreateRemoteThread.restype = wintypes.HANDLE
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.WaitForSingleObject.restype = wintypes.DWORD
_k32.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_int64)]
_k32.QueryPerformanceCounter.restype = wintypes.BOOL
_k32.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_int64)]
_k32.QueryPerformanceFrequency.restype = wintypes.BOOL
_k32.GetExitCodeThread.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.GetExitCodeThread.restype = wintypes.BOOL
_psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
_psapi.GetModuleBaseNameW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]

_RVA_UNLOAD_AMIIBO = 0x19F5FD0
_RVA_LOAD_NFC_TAG = 0x19F6910
_RVA_QWIDGET_MAPPER = 0x5EAED0
_SIG_LOAD_NFC_TAG = bytes.fromhex("4156565755534883ec20")
_SIG_UNLOAD_AMIIBO = bytes.fromhex("564883ec2083b99801000003")


def _find_lichii_main_hwnd(pid: int) -> int:
    hits = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        wpid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and _user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            _user32.GetClassNameW(hwnd, cls, 64)
            if "QWindowIcon" in cls.value:
                hits.append(int(hwnd))
        return True

    _user32.EnumWindows(_cb, 0)
    return hits[0] if hits else 0


class FritchiiNfcBridge:
    """Zero-menu direct memory reader & loader for Fritchii NfcDevice."""

    def __init__(self):
        self.pid: int | None = None
        self.lichii_base: int = 0
        self.qt_base: int = 0
        self.nfc_ptr: int = 0
        self.verified_sigs: bool = False
        self._last_scan: float = 0.0

    def reset(self):
        self.pid = None
        self.lichii_base = 0
        self.qt_base = 0
        self.nfc_ptr = 0
        self.verified_sigs = False

    def _rbytes(self, h, addr: int, n: int) -> bytes | None:
        buf = ctypes.create_string_buffer(n)
        rd = ctypes.c_size_t(0)
        if _k32.ReadProcessMemory(h, addr, buf, n, ctypes.byref(rd)) and rd.value == n:
            return buf.raw
        return None

    def _r64(self, h, addr: int) -> int:
        b = self._rbytes(h, addr, 8)
        return struct.unpack("<Q", b)[0] if b else 0

    def _r32(self, h, addr: int) -> int:
        b = self._rbytes(h, addr, 4)
        return struct.unpack("<I", b)[0] if b else -1

    def _ensure_resolved(self) -> bool:
        if self.pid and pid_exists(self.pid) and self.nfc_ptr and self.verified_sigs:
            return True
        now = time.monotonic()
        if self.pid and not pid_exists(self.pid):
            self.reset()
        if now - self._last_scan < 2.0:
            return False
        self._last_scan = now

        pid = None
        for p_id, nm, _exe in iter_processes():
            if "lichii" in nm:
                pid = p_id
                break
        if not pid:
            self.reset()
            return False

        h = _k32.OpenProcess(0x0010 | 0x0400, False, pid)
        if not h:
            return False
        try:
            mods = (wintypes.HMODULE * 256)()
            needed = wintypes.DWORD()
            if not _psapi.EnumProcessModules(h, mods, ctypes.sizeof(mods), ctypes.byref(needed)):
                return False
            nmods = needed.value // ctypes.sizeof(wintypes.HMODULE)
            l_base = int(mods[0]) if nmods else 0
            q_base = 0
            for i in range(nmods):
                nb = ctypes.create_unicode_buffer(260)
                _psapi.GetModuleBaseNameW(h, mods[i], nb, 260)
                if nb.value.lower() == "qt6widgets.dll":
                    q_base = int(mods[i])
                    break
            if not l_base or not q_base:
                return False

            if self._rbytes(h, l_base + _RVA_LOAD_NFC_TAG, len(_SIG_LOAD_NFC_TAG)) != _SIG_LOAD_NFC_TAG:
                return False
            if self._rbytes(h, l_base + _RVA_UNLOAD_AMIIBO, len(_SIG_UNLOAD_AMIIBO)) != _SIG_UNLOAD_AMIIBO:
                return False

            hwnd = _find_lichii_main_hwnd(pid)
            if not hwnd:
                return False

            mapper = self._r64(h, q_base + _RVA_QWIDGET_MAPPER)
            d = self._r64(h, mapper) if mapper else 0
            nbuck = self._r64(h, d + 0x10) if d else 0
            spans = self._r64(h, d + 0x20) if d else 0
            if not spans or nbuck == 0 or nbuck > 65536:
                return False

            gmain = 0
            nspans = max(1, (nbuck + 127) >> 7)
            for s in range(nspans):
                entries = self._r64(h, spans + s * 0x90 + 0x80)
                if not entries:
                    continue
                raw = self._rbytes(h, entries, 128 * 16)
                if not raw:
                    continue
                for j in range(128):
                    k, v = struct.unpack_from("<QQ", raw, j * 16)
                    if k == hwnd:
                        gmain = v
                        break
                if gmain:
                    break

            if not gmain:
                return False

            sys_ptr = self._r64(h, gmain + 0x40)
            impl = self._r64(h, sys_ptr) if sys_ptr else 0
            nfc = self._r64(h, impl + 0x80) if impl else 0
            if nfc < 0x10000:
                return False

            self.pid = pid
            self.lichii_base = l_base
            self.qt_base = q_base
            self.nfc_ptr = nfc
            self.verified_sigs = True
            return True
        finally:
            _k32.CloseHandle(h)

    def get_nfc_state(self) -> int | None:
        if not self._ensure_resolved():
            return None
        h = _k32.OpenProcess(0x0010 | 0x0400, False, self.pid)
        if not h:
            return None
        try:
            st = self._r32(h, self.nfc_ptr + 0x198)
            if st < 0 or st > 10:
                self.reset()
                return None
            return st
        finally:
            _k32.CloseHandle(h)

    def load_amiibo_direct(self, bin_path: str) -> tuple[bool, str]:
        p = Path(bin_path)
        if not p.is_file():
            return (False, f"找不到文件：{p.name}")
        raw = p.read_bytes()
        if not (532 <= len(raw) <= 1024):
            return (False, f"无效的 Amiibo 文件大小：{len(raw)} 字节")

        self._last_scan = 0.0
        if not self._ensure_resolved():
            return (False, "未连接到 Fritchii 模拟器 NfcDevice（请确认游戏已启动）")

        h = _k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0002 | 0x0400, False, self.pid)
        if not h:
            return (False, "无法打开 Fritchii 进程内存权限")

        alloc = 0
        try:
            state_now = self._r32(h, self.nfc_ptr + 0x198)
            if state_now not in (2, 3):
                return (False, "请先在游戏内点击「呼唤 amiibo」进入扫描等待状态，再按手柄 L3+○")

            alloc = _k32.VirtualAllocEx(h, None, 2048, 0x3000, 0x40)
            if not alloc:
                return (False, "申请模拟器远程内存失败")

            data_addr = alloc
            span_addr = alloc + 0x420
            code_addr = alloc + 0x440

            span_bytes = struct.pack("<QQ", data_addr, len(raw))
            fn_unload = self.lichii_base + _RVA_UNLOAD_AMIIBO
            fn_load = self.lichii_base + _RVA_LOAD_NFC_TAG

            code = bytearray()
            code += b"\x48\x83\xEC\x28"
            code += b"\x48\xB9" + struct.pack("<Q", self.nfc_ptr)
            code += b"\x83\xB9\x98\x01\x00\x00\x03"
            code += b"\x75\x16"
            code += b"\x48\xB8" + struct.pack("<Q", fn_unload)
            code += b"\xFF\xD0"
            code += b"\x48\xB9" + struct.pack("<Q", self.nfc_ptr)
            code += b"\x48\xBA" + struct.pack("<Q", span_addr)
            code += b"\x48\xB8" + struct.pack("<Q", fn_load)
            code += b"\xFF\xD0"
            code += b"\x48\x83\xC4\x28"
            code += b"\xC3"

            wr = ctypes.c_size_t(0)
            if not _k32.WriteProcessMemory(h, data_addr, raw, len(raw), ctypes.byref(wr)):
                return (False, "写入 Amiibo 数据失败")
            if not _k32.WriteProcessMemory(h, span_addr, span_bytes, len(span_bytes), ctypes.byref(wr)):
                return (False, "写入 Amiibo 描述失败")
            if not _k32.WriteProcessMemory(h, code_addr, bytes(code), len(code), ctypes.byref(wr)):
                return (False, "写入调用桩失败")

            tid = wintypes.DWORD(0)
            th = _k32.CreateRemoteThread(h, None, 0, code_addr, None, 0, ctypes.byref(tid))
            if not th:
                return (False, "启动远程调用失败")
            try:
                _k32.WaitForSingleObject(th, 2500)
                rc = wintypes.DWORD(99)
                _k32.GetExitCodeThread(th, ctypes.byref(rc))
            finally:
                _k32.CloseHandle(th)

            if rc.value == 0:
                return (True, f"已直接注入：{p.stem}")
            if rc.value == 3:
                return (False, "请先在游戏内点击「呼唤 amiibo」进入扫描等待状态")
            return (False, f"NfcDevice 返回状态码 {rc.value}")
        except Exception as exc:
            return (False, f"直接载入异常：{exc}")
        finally:
            if alloc:
                _k32.VirtualFreeEx(h, alloc, 0, 0x8000)
            _k32.CloseHandle(h)


def _qpc_now_ns() -> int:
    cnt = ctypes.c_int64()
    freq = ctypes.c_int64()
    _k32.QueryPerformanceCounter(ctypes.byref(cnt))
    _k32.QueryPerformanceFrequency(ctypes.byref(freq))
    return (cnt.value * 1_000_000_000) // freq.value if freq.value else 0


def _validate_amiibo_bytes(raw: bytes) -> tuple[bool, str]:
    if len(raw) != 540:
        return (False, f"NX2navi/NTAG215 需要精确 540 字节 Amiibo 文件（当前 {len(raw)} 字节）")
    if raw[0x0C:0x10] != b"\xF1\x10\xFF\xEE":
        return (False, "Amiibo 文件 Capability Container (0x0C) 无效")
    bcc0 = 0x88 ^ raw[0] ^ raw[1] ^ raw[2]
    bcc1 = raw[4] ^ raw[5] ^ raw[6] ^ raw[7]
    if raw[3] != bcc0 or raw[8] != bcc1:
        return (False, "Amiibo UID 校验字节 (BCC0/BCC1) 不匹配")
    return (True, "")


class Nx2naviNfcBridge:
    """Zero-menu direct memory reader & loader for NX2navi (ocarina.exe) native amiibo.c subsystem."""

    _DEFAULT_RVAS = {
        "amiibo_get_reader_state": 0x102A6DE0,
        "amiibo_scan_and_tap": 0x102A71C0,
        "amiibo_remove_tag": 0x102A7230,
    }

    def __init__(self):
        self.pid: int | None = None
        self.base: int = 0
        self.fn_scan_and_tap: int = 0
        self.fn_remove_tag: int = 0
        self.addr_dev_present: int = 0
        self.addr_mounted: int = 0
        self.addr_tag_present: int = 0
        self.addr_detecting: int = 0
        self.addr_stop_ns: int = 0
        self._last_scan: float = 0.0
        self._last_stop_ns: int = 0
        self._last_detect_ts: float = 0.0

    def reset(self):
        self.pid = None
        self.base = 0
        self.fn_scan_and_tap = 0
        self.fn_remove_tag = 0
        self.addr_dev_present = 0
        self.addr_mounted = 0
        self.addr_tag_present = 0
        self.addr_detecting = 0
        self.addr_stop_ns = 0
        self._last_stop_ns = 0
        self._last_detect_ts = 0.0

    def _rbytes(self, h, addr: int, n: int) -> bytes | None:
        buf = ctypes.create_string_buffer(n)
        rd = ctypes.c_size_t(0)
        if _k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(rd)) and rd.value == n:
            return buf.raw
        return None

    def _parse_map_rvas(self, exe_path: Path) -> dict[str, int]:
        mp = exe_path.parent / "build-cache" / "ocarina.map"
        if not mp.is_file():
            return dict(self._DEFAULT_RVAS)
        wanted = {
            "__image_base__",
            "amiibo_get_reader_state",
            "amiibo_scan_and_tap",
            "amiibo_remove_tag",
        }
        addrs: dict[str, int] = {}
        try:
            with mp.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "amiibo_" in line or "__image_base__" in line:
                        parts = line.split()
                        if len(parts) >= 2 and parts[0].startswith("0x") and parts[1] in wanted:
                            addrs[parts[1]] = int(parts[0], 16)
        except OSError:
            return dict(self._DEFAULT_RVAS)
        if not {"amiibo_get_reader_state", "amiibo_scan_and_tap", "amiibo_remove_tag"}.issubset(addrs):
            return dict(self._DEFAULT_RVAS)
        ib = addrs.get("__image_base__", 0x140000000)
        return {k: v - ib for k, v in addrs.items() if k != "__image_base__"}

    def _ensure_resolved(self) -> bool:
        if self.pid and pid_exists(self.pid) and self.addr_detecting and self.fn_scan_and_tap:
            return True
        now = time.monotonic()
        if self.pid and not pid_exists(self.pid):
            self.reset()
        if now - self._last_scan < 2.0:
            return False
        self._last_scan = now

        pid = None
        exe_path = None
        for p_id, nm, exe in iter_processes({"ocarina.exe"}):
            if nm == "ocarina.exe":
                pid = p_id
                exe_path = Path(exe) if exe else None
                break
        if not pid:
            self.reset()
            return False

        rvas = self._parse_map_rvas(exe_path) if exe_path else dict(self._DEFAULT_RVAS)
        h = _k32.OpenProcess(0x0010 | 0x0400, False, pid)
        if not h:
            return False
        try:
            mods = (wintypes.HMODULE * 512)()
            needed = wintypes.DWORD()
            if not _psapi.EnumProcessModules(h, mods, ctypes.sizeof(mods), ctypes.byref(needed)):
                return False
            base = int(mods[0]) if needed.value else 0
            if not base:
                return False

            fn_reader = base + rvas["amiibo_get_reader_state"]
            code = self._rbytes(h, fn_reader, 0xA0)
            if not code:
                return False

            dev_addr = mounted_addr = tag_addr = detect_addr = stop_addr = 0
            for i in range(len(code) - 7):
                if code[i : i + 2] == b"\x80\x3d":
                    disp = struct.unpack_from("<i", code, i + 2)[0]
                    imm = code[i + 6]
                    target = fn_reader + i + 7 + disp
                    if imm == 1 and not dev_addr:
                        dev_addr = target
                    elif imm == 0:
                        if not mounted_addr:
                            mounted_addr = target
                        elif not tag_addr:
                            tag_addr = target
                elif code[i : i + 2] == b"\x0f\xb6" and (code[i + 2] & 0xC7) == 0x05 and not detect_addr:
                    disp = struct.unpack_from("<i", code, i + 3)[0]
                    detect_addr = fn_reader + i + 7 + disp
            for i in range(len(code) - 8):
                if code[i : i + 3] == b"\x48\x83\x3d" and code[i + 7] == 0 and not stop_addr:
                    disp = struct.unpack_from("<i", code, i + 3)[0]
                    stop_addr = fn_reader + i + 8 + disp
                    break

            if not (dev_addr and mounted_addr and tag_addr and detect_addr and stop_addr):
                return False

            self.pid = pid
            self.base = base
            self.fn_scan_and_tap = base + rvas["amiibo_scan_and_tap"]
            self.fn_remove_tag = base + rvas["amiibo_remove_tag"]
            self.addr_dev_present = dev_addr
            self.addr_mounted = mounted_addr
            self.addr_tag_present = tag_addr
            self.addr_detecting = detect_addr
            self.addr_stop_ns = stop_addr
            return True
        finally:
            _k32.CloseHandle(h)

    def get_nfc_state(self) -> int | None:
        if not self._ensure_resolved():
            return None
        h = _k32.OpenProcess(0x0010 | 0x0400, False, self.pid)
        if not h:
            return None
        try:
            dev_b = self._rbytes(h, self.addr_dev_present, 1)
            det_b = self._rbytes(h, self.addr_detecting, 1)
            tag_b = self._rbytes(h, self.addr_tag_present, 1)
            mnt_b = self._rbytes(h, self.addr_mounted, 1)
            stp_b = self._rbytes(h, self.addr_stop_ns, 8)
            if not (dev_b and det_b and tag_b and mnt_b and stp_b):
                self.reset()
                return None
            if dev_b[0] == 0:
                return None
            if mnt_b[0] or tag_b[0]:
                return 3
            now = time.monotonic()
            stop_ns = struct.unpack("<Q", stp_b)[0]
            if det_b[0]:
                self._last_detect_ts = now
                self._last_stop_ns = stop_ns
                return 2
            if stop_ns:
                if stop_ns != self._last_stop_ns:
                    self._last_stop_ns = stop_ns
                    self._last_detect_ts = now
                qpc_ns = _qpc_now_ns()
                if qpc_ns >= stop_ns and (qpc_ns - stop_ns) < 1_100_000_000:
                    return 2
                if (now - self._last_detect_ts) < 1.1:
                    return 2
            return 1
        finally:
            _k32.CloseHandle(h)

    def load_amiibo_direct(self, bin_path: str) -> tuple[bool, str]:
        p = Path(bin_path)
        if not p.is_file():
            return (False, f"找不到文件：{p.name}")
        raw = p.read_bytes()
        ok_bin, err_bin = _validate_amiibo_bytes(raw)
        if not ok_bin:
            return (False, err_bin)

        self._last_scan = 0.0
        state_now = self.get_nfc_state()
        if state_now is None:
            return (False, "未连接到 NX2navi (ocarina.exe) Amiibo 子系统")
        if state_now not in (2, 3):
            return (False, "请先在游戏内点击「呼唤 amiibo」进入扫描等待状态，再按手柄 L3+○")

        h = _k32.OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0002 | 0x0400, False, self.pid)
        if not h:
            return (False, "无法打开 ocarina.exe 进程内存权限")

        alloc = 0
        try:
            alloc = _k32.VirtualAllocEx(h, None, 2048, 0x3000, 0x40)
            if not alloc:
                return (False, "申请 NX2navi 远程内存失败")

            path_bytes = str(p.resolve()).encode("utf-8") + b"\x00"
            path_addr = alloc
            code_addr = alloc + 0x400

            code = bytearray()
            code += b"\x48\x83\xEC\x28"
            code += b"\x48\xB8" + struct.pack("<Q", self.fn_remove_tag)
            code += b"\xFF\xD0"
            code += b"\x48\xB9" + struct.pack("<Q", path_addr)
            code += b"\x48\xB8" + struct.pack("<Q", self.fn_scan_and_tap)
            code += b"\xFF\xD0"
            code += b"\x0F\xB6\xC0"
            code += b"\x48\x83\xC4\x28"
            code += b"\xC3"

            wr = ctypes.c_size_t(0)
            if not _k32.WriteProcessMemory(h, path_addr, path_bytes, len(path_bytes), ctypes.byref(wr)):
                return (False, "写入 Amiibo 路径失败")
            if not _k32.WriteProcessMemory(h, code_addr, bytes(code), len(code), ctypes.byref(wr)):
                return (False, "写入 NX2navi 调用桩失败")

            tid = wintypes.DWORD(0)
            th = _k32.CreateRemoteThread(h, None, 0, code_addr, None, 0, ctypes.byref(tid))
            if not th:
                return (False, "启动远程调用失败")
            try:
                _k32.WaitForSingleObject(th, 2500)
                rc = wintypes.DWORD(0)
                _k32.GetExitCodeThread(th, ctypes.byref(rc))
            finally:
                _k32.CloseHandle(th)

            if rc.value == 1:
                return (True, f"已直接刷卡：{p.stem}")
            return (False, f"NX2navi amiibo_scan_and_tap 失败 (code={rc.value})")
        except Exception as exc:
            return (False, f"NX2navi 刷卡异常：{exc}")
        finally:
            if alloc:
                _k32.VirtualFreeEx(h, alloc, 0, 0x8000)
            _k32.CloseHandle(h)


_BRIDGE = FritchiiNfcBridge()
_NX2NAVI_BRIDGE = Nx2naviNfcBridge()
_LAST_NFC_KIND: str | None = None


def _foreground_pid() -> int:
    try:
        hwnd = _user32.GetForegroundWindow()
        if hwnd:
            wpid = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            return int(wpid.value)
    except Exception:
        pass
    return 0


def _running_emulator_kinds() -> list[str]:
    fg_pid = _foreground_pid()
    found: list[tuple[int, str]] = []
    for pid, nm, _exe in iter_processes():
        if nm == "ocarina.exe":
            found.append((0 if pid == fg_pid else 1, "nx2navi"))
        elif "lichii" in nm:
            found.append((0 if pid == fg_pid else 1, "fritchii"))
    found.sort(key=lambda x: x[0])
    out: list[str] = []
    for _prio, kind in found:
        if kind not in out:
            out.append(kind)
    return out


def _bridge_for(kind: str):
    return _NX2NAVI_BRIDGE if kind == "nx2navi" else _BRIDGE


def get_nfc_state() -> int | None:
    global _LAST_NFC_KIND
    kinds = _running_emulator_kinds()
    if not kinds:
        return None
    fallback_st: int | None = None
    fallback_kind: str | None = None
    for kind in kinds:
        st = _bridge_for(kind).get_nfc_state()
        if st in (2, 3):
            _LAST_NFC_KIND = kind
            return st
        if st is not None and fallback_st is None:
            fallback_st = st
            fallback_kind = kind
    if fallback_kind is not None:
        _LAST_NFC_KIND = fallback_kind
    return fallback_st


def load_amiibo_in_emulator(bin_path: str) -> tuple[bool, str]:
    """Load an Amiibo .bin directly into the active NX2navi or Fritchii process without opening menus."""
    kinds = _running_emulator_kinds()
    if not kinds:
        return (False, "未检测到运行中的 NX2navi (ocarina.exe) 或 Fritchii (lichii.exe)")
    ordered = list(kinds)
    if _LAST_NFC_KIND in ordered:
        ordered.remove(_LAST_NFC_KIND)
        ordered.insert(0, _LAST_NFC_KIND)
    for kind in ordered:
        br = _bridge_for(kind)
        if br.get_nfc_state() in (2, 3):
            return br.load_amiibo_direct(bin_path)
    return _bridge_for(ordered[0]).load_amiibo_direct(bin_path)
