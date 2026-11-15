"""Dual-source OoT state reader (Portable): Live RAM (ocarina.exe / lichii.exe / hookshot.exe) + auto-discovered save slots."""
import atexit
import ctypes
from ctypes import wintypes
import math
import os
import struct
import time
from pathlib import Path
from typing import Any

from portable_config import APP_DIR, load_config
from win_proc import get_process_name, iter_processes, pid_exists

DEFAULT_SAVE_DIR = APP_DIR / "saves"
GAMEDATA_INSTANCE_PTR_VA = 0x7004E842A8  # Verified from exefs/main GOT 0x4c7e180 -> .bss 0x4e842a8
MAIN_GOT_GAMEDATA_OFF = 0x4C7E180
MAIN_BSS_GAMEDATA_OFF = 0x4E842A8
_OOT_TITLE_ID = "0400486024DEC000"

# BoolExp HaveDefeatedEnemy_* flags have SaveFileIndex=-1 and wrap Int kill-count hashes (>0)
BOSS_DEFEAT_INT_HASHES: dict[int, int] = {
    0xC866BDAA: 0xEE850AD3,  # Gohma
    0xE4E3FDB8: 0x1DA458D0,  # Dodongo
    0x94899D9B: 0x4F344BA7,  # BigOcto
    0x52C59EC3: 0x725379E3,  # Barinade
    0x59682CC8: 0x1381A973,  # Poe_Meg
    0x92CB86BB: 0xC9175B2A,  # PhantomGanon
    0x27A76E5B: 0x8829B312,  # FlareDancer
    0xE46A9E97: 0xF6BBB871,  # Volvagia
    0x27B6BDE8: 0x892D68DE,  # DarkLink
    0x4C96EB50: 0x88461890,  # Morpha
    0xA386FB13: 0xB4396BB4,  # BongoBongo
    0x7229636C: 0xA3490368,  # IronKnuckle_Nabooru
    0x4FE914E3: 0x76EB9D9E,  # Twinrova
    0x0C3743B0: 0xE349F29F,  # Ganondorf
    0xE84B960E: 0x6D834709,  # Ganon
}

SCENE_ALIASES: dict[str, str] = {
    "IngoRanch": "LonLonRanch",
    "CrumblingGanonCastle": "GanonCastle",
    "FinalBattleField": "GanonCastle",
    "SageRoom": "TimeTemple",
}

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

_EMU_PROC_HINTS = {"ocarina.exe", "lichii", "hookshot.exe", "eden", "yuzu", "citron", "suyu", "ryujinx"}


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD


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


def _newest_slot_parent_under(root: Path, max_depth: int = 5) -> tuple[float, Path] | None:
    """Return (newest_mtime, save_profile_dir) for a tree containing slot_00..05/progress.sav."""
    if not root.is_dir():
        return None
    best: tuple[float, Path] | None = None
    try:
        for p in root.rglob("progress.sav"):
            try:
                rel_len = len(p.relative_to(root).parts)
            except Exception:
                continue
            if rel_len > max_depth:
                continue
            slot_dir = p.parent
            if not slot_dir.name.startswith("slot_"):
                continue
            save_dir = slot_dir.parent
            try:
                hdr = p.read_bytes()[:4]
                if len(hdr) < 4 or struct.unpack_from("<I", hdr, 0)[0] != 0x01020304:
                    continue
                mt = p.stat().st_mtime
                cap = slot_dir / "caption.sav"
                if cap.is_file():
                    mt = max(mt, cap.stat().st_mtime)
            except OSError:
                continue
            if best is None or mt > best[0]:
                best = (mt, save_dir)
    except OSError:
        pass
    return best


def find_active_save_dir(custom_save_dir: str | Path | None = None) -> Path | None:
    """Auto-discover OoT save directory from config, running emulator/port, local ./saves, or %APPDATA%."""
    cfg_val = custom_save_dir
    if not cfg_val:
        cfg_val = load_config().get("save_dir") or ""
    if cfg_val:
        cand = Path(str(cfg_val)).expanduser()
        if not cand.is_absolute():
            cand = APP_DIR / cand
        if cand.is_dir():
            hit = _newest_slot_parent_under(cand, max_depth=4)
            if hit:
                return hit[1]
            return cand

    # 1. Inspect currently running game processes (foreground emulator preferred when multiple are open)
    fg_pid = _foreground_pid()
    emu_candidates: list[tuple[int, float, Path]] = []
    for pid, nm, exe in iter_processes(_EMU_PROC_HINTS):
        if not exe:
            continue
        exe_dir = Path(exe).resolve().parent
        is_fg = 0 if pid == fg_pid else 1
        if nm == "ocarina.exe":
            for sub in (exe_dir / "profile" / "save", exe_dir / "saves"):
                hit = _newest_slot_parent_under(sub, max_depth=4)
                if hit:
                    emu_candidates.append((is_fg, -hit[0], hit[1]))
        elif nm == "hookshot.exe":
            for sub in (
                exe_dir.parent / "user" / "save",
                exe_dir / "user" / "save",
                exe_dir / "saves",
                exe_dir / "profile" / "save",
            ):
                hit = _newest_slot_parent_under(sub, max_depth=5)
                if hit:
                    emu_candidates.append((is_fg, -hit[0], hit[1]))
        else:
            for sub in (
                exe_dir / "user" / "nand" / "user" / "save",
                exe_dir / "portable" / "bis" / "user" / "save",
                exe_dir / "bis" / "user" / "save",
            ):
                hit = _newest_slot_parent_under(sub, max_depth=6)
                if hit:
                    emu_candidates.append((is_fg, -hit[0], hit[1]))
    if emu_candidates:
        emu_candidates.sort(key=lambda x: (x[0], x[1]))
        return emu_candidates[0][2]

    # 2. Check portable local ./saves folder
    local_hit = _newest_slot_parent_under(APP_DIR / "saves", max_depth=4)
    if local_hit:
        return local_hit[1]

    # 3. Check standard %APPDATA% Switch emulator folders
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        ad_candidates: list[tuple[float, Path]] = []
        for emu in ("eden", "yuzu", "suyu", "citron"):
            hit = _newest_slot_parent_under(Path(appdata) / emu / "nand" / "user" / "save", max_depth=6)
            if hit:
                ad_candidates.append(hit)
        ryu_hit = _newest_slot_parent_under(Path(appdata) / "Ryujinx" / "bis" / "user" / "save", max_depth=6)
        if ryu_hit:
            ad_candidates.append(ryu_hit)
        if ad_candidates:
            ad_candidates.sort(key=lambda x: x[0], reverse=True)
            return ad_candidates[0][1]

    # 4. Fallback to local ./saves even if empty
    return DEFAULT_SAVE_DIR if DEFAULT_SAVE_DIR.is_dir() else None


class _MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def _read_mem(handle, addr: int, size: int) -> bytes | None:
    if not addr or addr < 0x10000 or size <= 0:
        return None
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
    if not ok or read.value != size:
        return None
    return buf.raw


class LiveMemoryReader:
    """Reads live GameDataMgr tables from Hookshot (hookshot.exe), Fritchii (lichii.exe), or NX2navi (ocarina.exe)."""

    def __init__(self, table_counts: dict[str, int]):
        self.table_counts = table_counts
        self.pid: int | None = None
        self.proc_kind: str = ""
        self.handle = None
        self.arena_base: int = 0
        self.gamedata_ptr_host: int = 0
        self.mgr_ptr: int = 0
        self.tables: dict[str, tuple[int, int, int, int]] = {}
        self.bool_hash_to_idx: dict[int, int] = {}
        self.int_hash_to_idx: dict[int, int] = {}
        self.enum_hash_to_idx: dict[int, int] = {}
        self.str64_hash_to_idx: dict[int, int] = {}
        self.vec3_hash_to_idx: dict[int, int] = {}
        self._wanted_u32: set[int] = set()
        self._skull_hashes: frozenset[int] = frozenset()
        self._b64_flat_verified: bool = False
        self._scratch_cap: int = 320 * 1024
        self._scratch_ba = bytearray(self._scratch_cap)
        self._scratch_read = ctypes.c_size_t(0)
        self._last_pid_scan: float = 0.0
        self._last_arena_scan: float = 0.0
        atexit.register(self.close)

    def _ensure_wanted_hashes(self, db: dict[str, Any]):
        if self._wanted_u32:
            return
        w: set[int] = set(db.get("cap_hashes", {}).values())
        w.update(BOSS_DEFEAT_INT_HASHES.keys())
        w.update(BOSS_DEFEAT_INT_HASHES.values())
        for lst_key in ("heart_pieces", "quests"):
            for it in db.get(lst_key, ()):
                ft = it.get("flag_type")
                fk = it.get("flag_key")
                if ft == "bool" and isinstance(fk, int):
                    w.add(fk)
                elif ft == "any_bool" and isinstance(fk, list):
                    w.update(x for x in fk if isinstance(x, int))
                elif ft == "int_ge" and isinstance(fk, list) and fk:
                    w.add(int(fk[0]))
        self._wanted_u32 = w
        self._skull_hashes = frozenset(s["flag_key"] for s in db.get("skulltulas", ()))

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None
        self.pid = None
        self.proc_kind = ""
        self.arena_base = 0
        self.gamedata_ptr_host = 0
        self.mgr_ptr = 0
        self._b64_flat_verified = False
        self.tables.clear()
        self.bool_hash_to_idx.clear()
        self.int_hash_to_idx.clear()
        self.enum_hash_to_idx.clear()
        self.str64_hash_to_idx.clear()
        self.vec3_hash_to_idx.clear()

    def _find_pid(self) -> tuple[int, str] | None:
        fg_pid = _foreground_pid()
        if self.pid and pid_exists(self.pid):
            if fg_pid and fg_pid != self.pid:
                fg_nm = get_process_name(fg_pid)
                if fg_nm == "ocarina.exe":
                    return (fg_pid, "ocarina")
                if "lichii" in fg_nm:
                    return (fg_pid, "lichii")
                if fg_nm == "hookshot.exe":
                    return (fg_pid, "hookshot")
            # Do not get stuck on Hookshot's stub launcher before bin\hookshot.exe spawns
            if not (self.proc_kind == "hookshot" and not self.gamedata_ptr_host):
                return (self.pid, self.proc_kind)
        now = time.monotonic()
        if now - self._last_pid_scan < 3.0:
            if self.pid and pid_exists(self.pid):
                return (self.pid, self.proc_kind)
            return None
        self._last_pid_scan = now
        cands: list[tuple[tuple[int, int], int, str]] = []
        for pid, nm, exe in iter_processes({"ocarina.exe", "lichii", "hookshot.exe"}):
            is_fg = 0 if pid == fg_pid else 1
            if nm == "ocarina.exe":
                cands.append(((is_fg, 0), pid, "ocarina"))
            elif "lichii" in nm:
                cands.append(((is_fg, 0), pid, "lichii"))
            elif nm == "hookshot.exe":
                is_bin = 0 if (exe and Path(exe).parent.name.lower() == "bin") else 1
                cands.append(((is_fg, is_bin), pid, "hookshot"))
        if cands:
            cands.sort(key=lambda x: x[0])
            return (cands[0][1], cands[0][2])
        if self.pid and pid_exists(self.pid):
            return (self.pid, self.proc_kind)
        return None

    def _rguest(self, guest_va: int, size: int) -> memoryview | bytes | None:
        if not guest_va or guest_va < 0x10000 or size <= 0:
            return None
        host_va = self.arena_base + guest_va
        if host_va < 0x10000:
            return None
        if size > self._scratch_cap:
            self._scratch_cap = size
            self._scratch_ba = bytearray(self._scratch_cap)
        c_buf = (ctypes.c_char * size).from_buffer(self._scratch_ba)
        ok = kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(host_va), c_buf, size, ctypes.byref(self._scratch_read)
        )
        if not ok or self._scratch_read.value != size:
            return None
        return memoryview(self._scratch_ba)[:size]

    def _resolve_lichii_arena(self) -> bool:
        addr = 0x10000000000
        mbi = _MBI()
        while addr < 0x7FFFFFFFFFFF:
            if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            sz = mbi.RegionSize
            if mbi.State == 0x1000 and mbi.Type == 0x40000 and mbi.Protect == 0x2 and sz >= 20 * 1024 * 1024:
                got_raw = _read_mem(self.handle, base + MAIN_GOT_GAMEDATA_OFF, 8)
                bss_raw = _read_mem(self.handle, base + MAIN_BSS_GAMEDATA_OFF, 8)
                if got_raw and bss_raw:
                    got_val = struct.unpack("<Q", got_raw)[0]
                    mgr_guest = struct.unpack("<Q", bss_raw)[0]
                    main_guest = got_val - MAIN_BSS_GAMEDATA_OFF
                    if 0x10000000 <= main_guest < 0x1000000000 and (main_guest & 0xFFF) == 0 and mgr_guest > 0x10000000:
                        arena = base - main_guest
                        probe = _read_mem(self.handle, arena + mgr_guest, 0x40)
                        if probe:
                            bool_cnt = self.table_counts.get("Bool", 11292)
                            if any(struct.unpack_from("<I", probe, o)[0] == bool_cnt for o in range(0, 0x38, 4)):
                                self.arena_base = arena
                                self.gamedata_ptr_host = base + MAIN_BSS_GAMEDATA_OFF
                                return True
            addr = base + sz
        return False

    def _probe_hookshot_main(self, host_main: int) -> bool:
        got_raw = _read_mem(self.handle, host_main + MAIN_GOT_GAMEDATA_OFF, 8)
        bss_raw = _read_mem(self.handle, host_main + MAIN_BSS_GAMEDATA_OFF, 8)
        if not got_raw or not bss_raw:
            return False
        got_val = struct.unpack("<Q", got_raw)[0]
        mgr_guest = struct.unpack("<Q", bss_raw)[0]
        main_guest = got_val - MAIN_BSS_GAMEDATA_OFF
        if not (0x10000000 <= main_guest < 0x1000000000) or (main_guest & 0xFFF) != 0 or mgr_guest <= 0x10000000:
            return False
        arena = host_main - main_guest
        bool_cnt = self.table_counts.get("Bool", 11292)
        for cand_arena in ((arena,) if arena == 0 else (arena, 0)):
            probe = _read_mem(self.handle, cand_arena + mgr_guest, 0x40)
            if probe and any(struct.unpack_from("<I", probe, o)[0] == bool_cnt for o in range(0, 0x38, 4)):
                self.arena_base = cand_arena
                self.gamedata_ptr_host = host_main + MAIN_BSS_GAMEDATA_OFF
                return True
        return False

    def _resolve_hookshot_arena(self) -> bool:
        if self._probe_hookshot_main(0x80020000):
            return True
        addr = 0x10000
        mbi = _MBI()
        tried: set[int] = {0x80020000}
        while addr < 0x7FFFFFFFFFFF:
            if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            alloc_base = mbi.AllocationBase or base
            sz = mbi.RegionSize
            readable = (mbi.Protect & 0xEE) != 0 and (mbi.Protect & 0x100) == 0
            if mbi.State == 0x1000 and readable and sz >= 64 * 1024:
                roots = [base]
                if alloc_base and alloc_base != base:
                    roots.append(alloc_base)
                    roots.append(alloc_base + 0x80000000)
                roots.append(0x80000000)
                for root_base in roots:
                    if not root_base:
                        continue
                    for off in (0x20000, *range(0, 0x100000, 0x1000)):
                        cand_main = root_base + off
                        if cand_main in tried:
                            continue
                        if base <= cand_main + MAIN_GOT_GAMEDATA_OFF <= base + sz - 8:
                            tried.add(cand_main)
                            if self._probe_hookshot_main(cand_main):
                                return True
            addr = base + sz
        return False

    def _ensure_attached(self) -> bool:
        found = self._find_pid()
        if not found:
            self.close()
            return False
        pid, kind = found
        if pid != self.pid or not self.handle:
            self.close()
            h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
            if not h:
                return False
            self.pid = pid
            self.proc_kind = kind
            self.handle = h
        if self.proc_kind == "ocarina":
            self.arena_base = 0
            self.gamedata_ptr_host = GAMEDATA_INSTANCE_PTR_VA
        elif not self.gamedata_ptr_host:
            now_a = time.monotonic()
            if now_a - self._last_arena_scan < 2.5:
                return False
            self._last_arena_scan = now_a
            resolved = self._resolve_hookshot_arena() if self.proc_kind == "hookshot" else self._resolve_lichii_arena()
            if not resolved:
                return False
        raw_ptr = _read_mem(self.handle, self.gamedata_ptr_host, 8)
        if not raw_ptr:
            self.gamedata_ptr_host = 0
            return False
        mgr = struct.unpack("<Q", raw_ptr)[0]
        if mgr < 0x10000000:
            return False
        if mgr != self.mgr_ptr:
            self.mgr_ptr = mgr
            self._b64_flat_verified = False
            self.tables.clear()
            self.bool_hash_to_idx.clear()
            self.int_hash_to_idx.clear()
            self.enum_hash_to_idx.clear()
            self.str64_hash_to_idx.clear()
            self.vec3_hash_to_idx.clear()
        if not self.tables:
            self._calibrate_tables()
        return bool(self.tables)

    def _calibrate_tables(self):
        blob = self._rguest(self.mgr_ptr, 0xE00)
        if not blob:
            return
        targets = {
            self.table_counts.get("Bool", 11292): "Bool",
            self.table_counts.get("Int", 1259): "Int",
            self.table_counts.get("Enum", 130): "Enum",
            self.table_counts.get("String64", 54): "String64",
            self.table_counts.get("Vector3", 26): "Vector3",
        }
        b64_cnt = self.table_counts.get("Bool64bitKey", 11657)
        for off in range(0, 0xD80, 8):
            cnt, _pad, entries_ptr, hash_ptr = struct.unpack_from("<IIQQ", blob, off)
            if cnt in targets and entries_ptr > 0x10000000 and hash_ptr > 0x10000000:
                _, hcap = struct.unpack_from("<II", blob, off + 24)
                if cnt <= hcap <= cnt * 8:
                    tname = targets[cnt]
                    if tname not in self.tables:
                        self.tables[tname] = (cnt, entries_ptr, hash_ptr, hcap)
            elif cnt == b64_cnt and entries_ptr > 0x10000000:
                if "Bool64bitKey" not in self.tables:
                    self.tables["Bool64bitKey"] = (cnt, entries_ptr, hash_ptr, 0)

    def _read_u32_hash_map(self, hash_ptr: int, hcap: int, max_cnt: int, filter_set: set[int] | None = None) -> dict[int, int]:
        raw = self._rguest(hash_ptr, hcap * 8)
        if not raw:
            return {}
        out: dict[int, int] = {}
        for i in range(hcap):
            h, idx = struct.unpack_from("<II", raw, i * 8)
            if h != 0 and idx < max_cnt and (filter_set is None or h in filter_set):
                out[h] = idx
        return out

    def read_state(self, db: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_wanted_hashes(db)
        if not self._ensure_attached():
            return None
        try:
            res: dict[str, Any] = {"source": "live_memory", "bools": {}, "ints": {}, "b64": set(), "location": None}

            if "Bool" in self.tables:
                cnt, entries_ptr, hash_ptr, hcap = self.tables["Bool"]
                if not self.bool_hash_to_idx:
                    self.bool_hash_to_idx = self._read_u32_hash_map(hash_ptr, hcap, cnt, self._wanted_u32)
                raw = self._rguest(entries_ptr, cnt * 0x18)
                if not raw or not self.bool_hash_to_idx:
                    return None
                bools = res["bools"]
                for h, idx in self.bool_hash_to_idx.items():
                    bools[h] = raw[idx * 0x18 + 0x16] != 0

            if "Int" in self.tables:
                cnt, entries_ptr, hash_ptr, hcap = self.tables["Int"]
                if not self.int_hash_to_idx:
                    self.int_hash_to_idx = self._read_u32_hash_map(hash_ptr, hcap, cnt, self._wanted_u32)
                if self.int_hash_to_idx:
                    ints = self._read_ints(entries_ptr, cnt, db)
                    if ints:
                        res["ints"] = ints
                        for bexp_h, sub_h in BOSS_DEFEAT_INT_HASHES.items():
                            if sub_h in ints:
                                res["bools"][bexp_h] = ints[sub_h] > 0

            if "Enum" in self.tables:
                cnt, entries_ptr, hash_ptr, hcap = self.tables["Enum"]
                if not self.enum_hash_to_idx:
                    self.enum_hash_to_idx = self._read_u32_hash_map(hash_ptr, hcap, cnt, self._wanted_u32)
                if self.enum_hash_to_idx:
                    enums = self._read_enums(entries_ptr, cnt, db)
                    if enums:
                        res["enums"] = enums

            if "String64" in self.tables:
                cnt, entries_ptr, hash_ptr, hcap = self.tables["String64"]
                if not self.str64_hash_to_idx:
                    self.str64_hash_to_idx = self._read_u32_hash_map(hash_ptr, hcap, cnt)
                loc_h = db["cap_hashes"].get("CaptionData.LocationName")
                if loc_h and loc_h in self.str64_hash_to_idx:
                    loc = self._read_string64(entries_ptr, cnt, self.str64_hash_to_idx[loc_h], db["locations"])
                    if loc:
                        res["location"] = loc

            if "Bool64bitKey" in self.tables:
                cnt, entries_ptr, hash_ptr, hcap = self.tables["Bool64bitKey"]
                b64 = self._read_b64(entries_ptr, cnt, hash_ptr, hcap, db["skulltulas"])
                if b64 is not None:
                    res["b64"] = b64
                    res["b64_ok"] = True

            if "Vector3" in self.tables:
                cnt, entries_ptr, hash_ptr, hcap = self.tables["Vector3"]
                if not self.vec3_hash_to_idx:
                    self.vec3_hash_to_idx = self._read_u32_hash_map(hash_ptr, hcap, cnt)
                pos_h = db["cap_hashes"].get("Player_Pos_For_Map")
                if pos_h and pos_h in self.vec3_hash_to_idx:
                    pos = self._read_vector3(entries_ptr, cnt, self.vec3_hash_to_idx[pos_h])
                    if pos is not None:
                        res["player_pos"] = pos
                        if res["location"] == "HyruleField":
                            x, _y, z = pos
                            if -185 <= x <= -15 and 165 <= z <= 355:
                                res["location"] = "LonLonRanch"
                            elif ((x + 205.4) ** 2 + (z - 559.2) ** 2) <= 205.0 ** 2:
                                res["location"] = "LakeHylia"

            return res
        except Exception:
            return None

    def _read_ints(self, entries_ptr: int, cnt: int, db: dict[str, Any]) -> dict[int, int] | None:
        h_ml = db["cap_hashes"].get("PlayerStatus.MaxLife")
        h_life = db["cap_hashes"].get("PlayerStatus.Life")
        idx_ml = self.int_hash_to_idx.get(h_ml) if h_ml else None
        idx_lf = self.int_hash_to_idx.get(h_life) if h_life else None
        if idx_ml is None:
            return None
        raw = self._rguest(entries_ptr, cnt * 0x28)
        if not raw:
            return None
        for stride, pref_offs in ((0x28, (0x1C, 0x20)), (0x18, ()), (0x20, ()), (0x10, ())):
            if cnt * stride > len(raw):
                continue
            offs = list(pref_offs) + [o for o in range(0, stride - 3, 4) if o not in pref_offs]
            for voff in offs:
                ml = struct.unpack_from("<i", raw, idx_ml * stride + voff)[0]
                if 12 <= ml <= 80 and ml % 4 == 0:
                    if idx_lf is not None:
                        lf = struct.unpack_from("<i", raw, idx_lf * stride + voff)[0]
                        if not (0 <= lf <= ml):
                            continue
                    return {
                        h: struct.unpack_from("<i", raw, idx * stride + voff)[0]
                        for h, idx in self.int_hash_to_idx.items()
                    }
        return None

    def _read_enums(self, entries_ptr: int, cnt: int, db: dict[str, Any]) -> dict[int, int] | None:
        raw = self._rguest(entries_ptr, cnt * 0x38)
        if not raw:
            return None
        if cnt * 0x38 <= len(raw):
            return {
                h: struct.unpack_from("<I", raw, idx * 0x38 + 0x1C)[0]
                for h, idx in self.enum_hash_to_idx.items()
            }
        return None

    def _read_string64(self, entries_ptr: int, cnt: int, idx: int, valid_locs: dict[str, str]) -> str | None:
        raw_mv = self._rguest(entries_ptr, cnt * 0x70)
        if not raw_mv:
            return None
        raw = bytes(raw_mv)
        for stride in (0x70, 0x58, 0x60, 0x50, 0x68):
            if cnt * stride > len(raw):
                continue
            chunk = raw[idx * stride : (idx + 1) * stride]
            soffs = [4] + [o for o in range(0, stride - 4, 4) if o != 4]
            for soff in soffs:
                sub = chunk[soff : soff + 64]
                nul = sub.find(b"\x00")
                if 3 <= nul <= 63:
                    txt = sub[:nul].decode("utf-8", errors="ignore")
                    base_loc = txt.split("/", 1)[0]
                    if base_loc in SCENE_ALIASES:
                        return SCENE_ALIASES[base_loc]
                    if txt in valid_locs:
                        return txt
                    if base_loc in valid_locs:
                        return base_loc
                    if txt == "Title" or base_loc == "Title":
                        return "Title"
        return None

    def _read_vector3(self, entries_ptr: int, cnt: int, idx: int) -> tuple[float, float, float] | None:
        raw = self._rguest(entries_ptr, cnt * 0x40)
        if not raw:
            return None
        for stride, pref_offs in ((0x40, (0x24, 0x30)), (0x28, ()), (0x20, ()), (0x24, ()), (0x30, ())):
            if cnt * stride > len(raw):
                continue
            base = idx * stride
            offs = list(pref_offs) + [o for o in range(0, stride - 11, 4) if o not in pref_offs]
            for voff in offs:
                x, y, z = struct.unpack_from("<3f", raw, base + voff)
                if all(math.isfinite(v) and -5000.0 <= v <= 5000.0 for v in (x, y, z)) and (abs(x) > 0.01 or abs(y) > 0.01 or abs(z) > 0.01):
                    return (x, y, z)
        return None

    def _read_b64(self, entries_ptr: int, cnt: int, hash_ptr: int, hcap: int, skulltulas: list[dict[str, Any]]) -> set[int] | None:
        skull_hashes = self._skull_hashes or {s["flag_key"] for s in skulltulas}
        raw_flat = self._rguest(entries_ptr, cnt * 0x10)
        if raw_flat and len(raw_flat) >= cnt * 0x10:
            if not self._b64_flat_verified:
                matched_sk = 0
                for i in range(cnt):
                    hv = struct.unpack_from("<Q", raw_flat, i * 0x10)[0]
                    if hv in skull_hashes:
                        matched_sk += 1
                self._b64_flat_verified = matched_sk >= 50
            if self._b64_flat_verified:
                active_flat: set[int] = set()
                for off in range(0, cnt * 0x10, 0x10):
                    if raw_flat[off + 0x0E] != 0:
                        hv = struct.unpack_from("<Q", raw_flat, off)[0]
                        if hv:
                            active_flat.add(hv)
                if len(active_flat & skull_hashes) <= 100:
                    return active_flat
        if not hcap or hash_ptr < 0x10000000:
            return None
        ht = self._rguest(hash_ptr, hcap * 16)
        if not ht:
            return None
        h_to_idx: dict[int, int] = {}
        for i in range(hcap):
            h, idx, _ = struct.unpack_from("<QII", ht, i * 16)
            if h != 0 and idx < cnt:
                h_to_idx[h] = idx
        if not (skull_hashes & set(h_to_idx)):
            return None
        raw = self._rguest(entries_ptr, cnt * 0x18)
        if not raw:
            return None
        for stride, voff in ((0x18, 0x16), (0x10, 0x0E), (0x10, 0x08), (0x18, 0x10)):
            if cnt * stride > len(raw):
                continue
            active = {h for h, idx in h_to_idx.items() if raw[idx * stride + voff] != 0}
            if 0 < len(active & skull_hashes) <= 100:
                return active
        return None


class SaveFileReader:
    """Reads progress.sav and caption.sav from the most recently updated slot (or specified slot)."""

    def __init__(self, save_dir: Path | str | None = None, slot: int | str = "auto"):
        self.save_dir: Path | None = Path(save_dir) if save_dir else None
        self.slot = slot
        self._cache_key: tuple[str, float] | None = None
        self._cache_state: dict[str, Any] | None = None

    def _pick_slot(self) -> tuple[str, Path, Path, float] | None:
        if self.save_dir is None or not self.save_dir.is_dir():
            return None
        if isinstance(self.slot, int):
            slots = [self.slot]
        else:
            slots = list(range(6))

        best = None
        for s in slots:
            sname = f"slot_{s:02d}"
            sdir = self.save_dir / sname
            prog = sdir / "progress.sav"
            cap = sdir / "caption.sav"
            if not prog.exists():
                continue
            try:
                mt = prog.stat().st_mtime
                if cap.exists():
                    mt = max(mt, cap.stat().st_mtime)
            except OSError:
                continue
            if best is None or mt > best[3]:
                best = (sname, prog, cap, mt)
        return best

    def read_state(self, db: dict[str, Any]) -> dict[str, Any] | None:
        picked = self._pick_slot()
        if not picked:
            return None
        sname, prog_path, cap_path, mtime = picked
        if self._cache_key == (sname, mtime) and self._cache_state is not None:
            return self._cache_state

        try:
            sav = prog_path.read_bytes()
        except OSError:
            return None

        if len(sav) < 0x175D8 or struct.unpack_from("<I", sav, 0)[0] != 0x01020304:
            return None

        offset_pos = struct.unpack_from("<I", sav, 8)[0]
        kv32: dict[int, int] = {}
        for p in range(0x28, offset_pos, 8):
            h, v = struct.unpack_from("<II", sav, p)
            if h:
                kv32[h] = v

        active_b64: set[int] = set()
        known_b64 = {s["flag_key"] for s in db["skulltulas"]} | {
            hp["flag_key"] for hp in db["heart_pieces"] if hp["flag_type"] == "b64"
        }
        start_off = 0x1FB94
        for probe in range(offset_pos, len(sav) - 8, 4):
            val = struct.unpack_from("<Q", sav, probe)[0]
            if val in known_b64:
                start_off = probe
                while start_off >= offset_pos + 8:
                    prev_val = struct.unpack_from("<Q", sav, start_off - 8)[0]
                    if prev_val == 0 or prev_val < 0x1000000:
                        break
                    start_off -= 8
                break

        for off in range(start_off, len(sav) - 7, 8):
            val = struct.unpack_from("<Q", sav, off)[0]
            if val:
                active_b64.add(val)

        location = None
        if cap_path.exists():
            try:
                cap = cap_path.read_bytes()
                cap_offset_pos = struct.unpack_from("<I", cap, 8)[0]
                loc_hash = db["cap_hashes"].get("CaptionData.LocationName", 0xF74E0E8E)
                for p in range(0x28, min(cap_offset_pos, len(cap)), 8):
                    h, v = struct.unpack_from("<II", cap, p)
                    if h == loc_hash and cap_offset_pos <= v < len(cap):
                        end = cap.find(b"\x00", v)
                        if end > v:
                            raw_loc = cap[v:end].decode("utf-8", errors="ignore")
                            base_loc = raw_loc.split("/", 1)[0] if "/" in raw_loc else raw_loc
                            location = SCENE_ALIASES.get(base_loc, base_loc)
                        break
            except OSError:
                pass

        pos_hash = db["cap_hashes"].get("Player_Pos_For_Map")
        player_pos = None
        if pos_hash and pos_hash in kv32:
            poff = kv32[pos_hash]
            if offset_pos <= poff <= len(sav) - 12:
                player_pos = struct.unpack_from("<3f", sav, poff)
                if location == "HyruleField":
                    x, _y, z = player_pos
                    if -185 <= x <= -15 and 165 <= z <= 355:
                        location = "LonLonRanch"
                    elif ((x + 205.4) ** 2 + (z - 559.2) ** 2) <= 205.0 ** 2:
                        location = "LakeHylia"

        state = {
            "source": "save_file",
            "slot_name": sname,
            "kv32": kv32,
            "b64": active_b64,
            "location": location or "HyruleField",
            "player_pos": player_pos,
            "mtime": mtime,
        }
        self._cache_key = (sname, mtime)
        self._cache_state = state
        return state


class UnifiedStateReader:
    """Combines auto-discovered SaveFileReader + LiveMemoryReader (supports RAM-only mode on any PC)."""

    def __init__(self, db: dict[str, Any], save_dir: Path | str | None = None, slot: int | str = "auto"):
        self.db = db
        self._explicit_save_dir = save_dir
        self._last_dir_probe = 0.0
        self._last_mem_pid: int | None = None
        resolved = find_active_save_dir(save_dir)
        self.save_reader = SaveFileReader(resolved, slot)
        self.mem_reader = LiveMemoryReader(db.get("table_counts", {}))

    def _maybe_refresh_save_dir(self, disk_ok: bool):
        if self._explicit_save_dir:
            return
        now = time.monotonic()
        cur_pid = self.mem_reader.pid
        pid_changed = cur_pid is not None and cur_pid != self._last_mem_pid
        if pid_changed:
            self._last_mem_pid = cur_pid
        if pid_changed or (not disk_ok and (now - self._last_dir_probe >= 3.0)):
            self._last_dir_probe = now
            new_dir = find_active_save_dir(None)
            if new_dir and new_dir != self.save_reader.save_dir:
                self.save_reader.save_dir = new_dir
                self.save_reader._cache_key = None
                self.save_reader._cache_state = None

    def read(self) -> dict[str, Any] | None:
        disk = self.save_reader.read_state(self.db)
        mem = self.mem_reader.read_state(self.db)
        self._maybe_refresh_save_dir(disk is not None)
        if disk is None and self.save_reader.save_dir is not None:
            disk = self.save_reader.read_state(self.db)

        if mem and disk:
            h_ml = self.db.get("cap_hashes", {}).get("PlayerStatus.MaxLife")
            mem_ml = mem.get("ints", {}).get(h_ml, 0) if h_ml else 12
            mem_loc = mem.get("location")
            if mem_ml < 12 or mem_loc == "Title":
                out = dict(disk)
                out["is_loading"] = True
                return out
            merged_kv = dict(disk["kv32"])
            for h, v in mem.get("bools", {}).items():
                merged_kv[h] = 1 if v else 0
            for h, v in mem.get("ints", {}).items():
                merged_kv[h] = v
            for h, v in mem.get("enums", {}).items():
                merged_kv[h] = v
            b64 = mem["b64"] if mem.get("b64_ok") else disk["b64"]
            loc = mem_loc or disk["location"]
            ppos = mem.get("player_pos") or disk.get("player_pos")
            if loc == "HyruleField" and ppos:
                x, _y, z = ppos
                if -185 <= x <= -15 and 165 <= z <= 355:
                    loc = "LonLonRanch"
                elif ((x + 205.4) ** 2 + (z - 559.2) ** 2) <= 205.0 ** 2:
                    loc = "LakeHylia"
            return {
                "source": "live_memory",
                "slot_name": disk.get("slot_name", "live"),
                "kv32": merged_kv,
                "b64": b64,
                "location": loc,
                "player_pos": ppos,
                "mtime": disk["mtime"],
            }

        if mem and not disk:
            h_ml = self.db.get("cap_hashes", {}).get("PlayerStatus.MaxLife")
            mem_ml = mem.get("ints", {}).get(h_ml, 0) if h_ml else 12
            mem_loc = mem.get("location")
            if mem_ml < 12 or mem_loc == "Title" or not mem.get("b64_ok"):
                return None
            live_kv: dict[int, int] = {}
            for h, v in mem.get("bools", {}).items():
                live_kv[h] = 1 if v else 0
            for h, v in mem.get("ints", {}).items():
                live_kv[h] = v
            for h, v in mem.get("enums", {}).items():
                live_kv[h] = v
            loc = mem_loc or "HyruleField"
            ppos = mem.get("player_pos")
            if loc == "HyruleField" and ppos:
                x, _y, z = ppos
                if -185 <= x <= -15 and 165 <= z <= 355:
                    loc = "LonLonRanch"
                elif ((x + 205.4) ** 2 + (z - 559.2) ** 2) <= 205.0 ** 2:
                    loc = "LakeHylia"
            return {
                "source": "live_memory",
                "slot_name": "live",
                "kv32": live_kv,
                "b64": mem["b64"],
                "location": loc,
                "player_pos": ppos,
                "mtime": time.time(),
            }

        return disk
