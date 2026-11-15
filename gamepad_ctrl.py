"""Universal + PS5 DualSense native gamepad & touchpad swipe poller (zero third-party deps).

Supports:
- Sony PS5 DualSense (VID 0x054C, PID 0x0CE6 / 0x0DF2) & PS4 DualShock 4 via Windows winmm + HID
  * Including native Touchpad finger X/Y swipe gestures (Left/Right = switch tab/rail, Up/Down = scroll)
- Nintendo Switch Pro (VID 0x057E) & generic DirectInput gamepads via Windows winmm
- Xbox / DS4Windows / Steam Input virtual XInput controllers via xinput1_4 / xinput1_3 / xinput9_1_0

Conflict-free control bindings (never interfere with OoT gameplay; ZERO Home / Menu / Shoulder usage):
- PS5 Touchpad Swipe Left / Right         : switch tab/rail (or switch 2 masks while calling Amiibo)
- PS5 Touchpad Swipe Up / Down            : scroll view up / down (or pick Amiibo card while calling Amiibo)
- PS5 Touchpad Click OR L3+R3 (any pad)   : toggle full overlay panel <-> compact/fullscreen HUD
- L3 + Circle/B/A(Switch) (any pad)       : load selected Amiibo directly into emulator
- R3 + Touchpad Click (or L3+Touchpad)    : open / close Amiibo selector directly
- R3 + D-Pad Left / Right                 : switch tab / cycle left rail (or switch 2 masks while calling Amiibo)
- R3 + D-Pad Up / Down                    : scroll view / step Amiibo cards (universal fallback)
- R3 + Triangle/Y, Square/X, Cross/A      : cycle preview region / snap back to auto live location
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import threading
import time


# WinMM structures for DirectInput / HID / PS5 DualSense / Switch Pro
JOY_RETURNALL = 0x000000FF
JOYERR_NOERROR = 0
SONY_VID = 0x054C
DUALSENSE_PIDS = {0x0CE6, 0x0DF2}
DUALSHOCK4_PIDS = {0x05C4, 0x09CC}
SWITCH_VID = 0x057E


class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


class JOYCAPS(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("szPname", wintypes.WCHAR * 32),
        ("wXmin", wintypes.UINT),
        ("wXmax", wintypes.UINT),
        ("wYmin", wintypes.UINT),
        ("wYmax", wintypes.UINT),
        ("wZmin", wintypes.UINT),
        ("wZmax", wintypes.UINT),
        ("wNumButtons", wintypes.UINT),
        ("wPeriodMin", wintypes.UINT),
        ("wPeriodMax", wintypes.UINT),
        ("wRmin", wintypes.UINT),
        ("wRmax", wintypes.UINT),
        ("wUmin", wintypes.UINT),
        ("wUmax", wintypes.UINT),
        ("wVmin", wintypes.UINT),
        ("wVmax", wintypes.UINT),
        ("wCaps", wintypes.UINT),
        ("wMaxAxes", wintypes.UINT),
        ("wNumAxes", wintypes.UINT),
        ("wMaxButtons", wintypes.UINT),
        ("szRegKey", wintypes.WCHAR * 32),
        ("szOEMVxD", wintypes.WCHAR * 260),
    ]


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


@dataclass
class GamepadSnapshot:
    connected: bool
    kind: str           # "ps5" | "ps4" | "switch" | "xbox" | "generic" | "none"
    label: str          # Human-readable label e.g. "PS5 DualSense"
    l1_r1: bool = False
    r1: bool = False
    dpad_up: bool = False
    dpad_down: bool = False
    dpad_left: bool = False
    dpad_right: bool = False
    l3_r3: bool = False
    btn_l3: bool = False
    btn_r3: bool = False
    touchpad: bool = False
    btn_north: bool = False  # PS5 △ / Xbox Y
    btn_west: bool = False   # PS5 □ / Xbox X
    btn_south: bool = False  # PS5 × / Xbox A
    btn_east: bool = False   # PS5 ○ / Xbox B / Switch A
    ry_norm: float = 0.0     # Right stick vertical [-1..+1], positive = up
    touch_active: bool = False
    touch_id: int = -1       # DualSense hardware touch sequence ID [0..127]
    touch_x: int = 0         # DualSense Touchpad X [0..1919]
    touch_y: int = 0         # DualSense Touchpad Y [0..1079]
    touch_dy: float = 0.0    # Continuous per-frame touchpad Y delta for 1px smooth scroll
    touch_vy: float = 0.0    # Instantaneous finger Y speed (units/sec); 0 if finger paused before lift
    touch_lifted: bool = False


class _RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]


class _RID_DEVICE_INFO_HID(ctypes.Structure):
    _fields_ = [
        ("dwVendorId", wintypes.DWORD),
        ("dwProductId", wintypes.DWORD),
        ("dwVersionNumber", wintypes.DWORD),
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
    ]


class _RID_U(ctypes.Union):
    _fields_ = [("pad", ctypes.c_byte * 24), ("hid", _RID_DEVICE_INFO_HID)]


class _RID_DEVICE_INFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("dwType", wintypes.DWORD), ("u", _RID_U)]


class _HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT), ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT), ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT), ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT), ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT), ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT), ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT), ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


def parse_dualsense_touch_report(buf: bytes) -> tuple[bool, int, int] | None:
    """Parse touch point 0 from DualSense USB (rid 0x01, 64B) or BT (rid 0x31, >=78B) HID report."""
    if len(buf) < 38:
        return None
    rid = buf[0]
    if rid == 0x01 and len(buf) >= 37:
        off = 33
    elif rid == 0x31 and len(buf) >= 38:
        off = 34
    else:
        return None
    active = (buf[off] & 0x80) == 0
    x = buf[off + 1] | ((buf[off + 2] & 0x0F) << 8)
    y = (buf[off + 2] >> 4) | (buf[off + 3] << 4)
    return (active, x, y)


def _parse_dualsense_full_packet(buf: bytes) -> GamepadSnapshot | None:
    """Parse full 252Hz DualSense USB (rid 0x01, 64B) or BT (rid 0x31, >=78B) HID report in one atomic read."""
    if len(buf) < 38:
        return None
    rid = buf[0]
    if rid == 0x01 and len(buf) >= 37:
        base = 1
        toff = 33
    elif rid == 0x31 and len(buf) >= 38:
        base = 2
        toff = 34
    else:
        return None

    ry_byte = buf[base + 3]
    ry_norm = (127.5 - float(ry_byte)) / 127.5
    if abs(ry_norm) < 0.25:
        ry_norm = 0.0

    b0 = buf[base + 7]
    b1 = buf[base + 8]
    b2 = buf[base + 9]
    hat = b0 & 0x0F
    up = hat in (0, 1, 7)
    right = hat in (1, 2, 3)
    down = hat in (3, 4, 5)
    left = hat in (5, 6, 7)

    btn_west = bool(b0 & 0x10)
    btn_south = bool(b0 & 0x20)
    btn_east = bool(b0 & 0x40)
    btn_north = bool(b0 & 0x80)
    l1 = bool(b1 & 0x01)
    r1 = bool(b1 & 0x02)
    btn_l3 = bool(b1 & 0x40)
    btn_r3 = bool(b1 & 0x80)
    touchpad_click = bool(b2 & 0x02)

    t_raw = buf[toff]
    t_active = (t_raw & 0x80) == 0
    t_id = t_raw & 0x7F
    tx = buf[toff + 1] | ((buf[toff + 2] & 0x0F) << 8)
    ty = (buf[toff + 2] >> 4) | (buf[toff + 3] << 4)

    return GamepadSnapshot(
        connected=True,
        kind="ps5",
        label="PS5 DualSense",
        l1_r1=(l1 and r1),
        r1=r1,
        dpad_up=up,
        dpad_down=down,
        dpad_left=left,
        dpad_right=right,
        l3_r3=(btn_l3 and btn_r3),
        btn_l3=btn_l3,
        btn_r3=btn_r3,
        touchpad=touchpad_click,
        btn_north=btn_north,
        btn_west=btn_west,
        btn_south=btn_south,
        btn_east=btn_east,
        ry_norm=ry_norm,
        touch_active=t_active,
        touch_id=t_id,
        touch_x=tx,
        touch_y=ty,
    )


class DualSenseTouchpadReader:
    """Non-blocking 252Hz background shared-HID reader for PS5 DualSense buttons, sticks, and touchpad."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active = False
        self._touch_id = -1
        self._x = 0
        self._y = 0
        self._prev_pkt_y: int | None = None
        self._accum_dy: float = 0.0
        self._inst_vy: float = 0.0  # Touchpad Y units/sec from 250Hz hardware stream
        self._last_move_ts: float = 0.0
        self._latest_snap: GamepadSnapshot | None = None
        self._ts = 0.0
        self._stop = False
        self._handle = None
        try:
            self._user32 = ctypes.WinDLL("user32")
            self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._hid = ctypes.WinDLL("hid", use_last_error=True)
            self._k32.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            self._k32.CreateFileW.restype = wintypes.HANDLE
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        except Exception:
            self._user32 = None

    def get_full_snap(self) -> GamepadSnapshot | None:
        """Return atomic 252Hz DualSense snapshot + drained exact Y delta & instantaneous Y velocity."""
        now = time.monotonic()
        with self._lock:
            if self._latest_snap is None or (now - self._ts) > 0.45:
                return None
            dy = self._accum_dy
            self._accum_dy = 0.0
            vy = self._inst_vy if (now - self._last_move_ts) <= 0.030 else 0.0
            s = self._latest_snap
            return GamepadSnapshot(
                connected=True,
                kind=s.kind,
                label=s.label,
                l1_r1=s.l1_r1,
                r1=s.r1,
                dpad_up=s.dpad_up,
                dpad_down=s.dpad_down,
                dpad_left=s.dpad_left,
                dpad_right=s.dpad_right,
                l3_r3=s.l3_r3,
                btn_l3=s.btn_l3,
                btn_r3=s.btn_r3,
                touchpad=s.touchpad,
                btn_north=s.btn_north,
                btn_west=s.btn_west,
                btn_south=s.btn_south,
                btn_east=s.btn_east,
                ry_norm=s.ry_norm,
                touch_active=s.touch_active,
                touch_id=s.touch_id,
                touch_x=s.touch_x,
                touch_y=s.touch_y,
                touch_dy=dy,
                touch_vy=vy,
            )

    def get_touch(self) -> tuple[bool, int, int, float, float]:
        """Return (active, x, y, drained_accum_dy, recent_vy_units_per_sec)."""
        now = time.monotonic()
        with self._lock:
            if self._active and (now - self._ts) > 0.35:
                self._active = False
                self._prev_pkt_y = None
                self._accum_dy = 0.0
                self._inst_vy = 0.0
            dy = self._accum_dy
            self._accum_dy = 0.0
            vy = self._inst_vy if (now - self._last_move_ts) <= 0.030 else 0.0
            return (self._active, self._x, self._y, dy, vy)

    def close(self):
        self._stop = True
        h = self._handle
        if h and self._k32:
            try:
                self._k32.CancelIoEx(wintypes.HANDLE(h), None)
                self._k32.CloseHandle(wintypes.HANDLE(h))
            except Exception:
                pass
            self._handle = None

    def _find_dualsense_hid_path(self) -> str | None:
        cnt = wintypes.UINT(0)
        self._user32.GetRawInputDeviceList(None, ctypes.byref(cnt), ctypes.sizeof(_RAWINPUTDEVICELIST))
        if cnt.value == 0:
            return None
        devs = (_RAWINPUTDEVICELIST * cnt.value)()
        self._user32.GetRawInputDeviceList(devs, ctypes.byref(cnt), ctypes.sizeof(_RAWINPUTDEVICELIST))
        for d in devs:
            if d.dwType != 2:
                continue
            info = _RID_DEVICE_INFO(cbSize=ctypes.sizeof(_RID_DEVICE_INFO))
            sz = wintypes.UINT(ctypes.sizeof(info))
            self._user32.GetRawInputDeviceInfoW(d.hDevice, 0x2000000B, ctypes.byref(info), ctypes.byref(sz))
            if info.u.hid.dwVendorId == SONY_VID and info.u.hid.dwProductId in DUALSENSE_PIDS:
                nsz = wintypes.UINT(0)
                self._user32.GetRawInputDeviceInfoW(d.hDevice, 0x20000007, None, ctypes.byref(nsz))
                if nsz.value > 0:
                    nbuf = ctypes.create_unicode_buffer(nsz.value)
                    self._user32.GetRawInputDeviceInfoW(d.hDevice, 0x20000007, nbuf, ctypes.byref(nsz))
                    return nbuf.value
        return None

    def _loop(self):
        invalid = ctypes.c_void_p(-1).value
        while not self._stop:
            path = None
            try:
                path = self._find_dualsense_hid_path()
            except Exception:
                pass
            if not path:
                time.sleep(2.0)
                continue
            h = self._k32.CreateFileW(path, 0x80000000, 3, None, 3, 0, None)
            if not h or h == invalid:
                time.sleep(2.0)
                continue
            self._handle = h
            rep_len = 64
            try:
                ppd = ctypes.c_void_p()
                if self._hid.HidD_GetPreparsedData(wintypes.HANDLE(h), ctypes.byref(ppd)):
                    caps = _HIDP_CAPS()
                    if self._hid.HidP_GetCaps(ppd, ctypes.byref(caps)):
                        rep_len = max(64, int(caps.InputReportByteLength))
                    self._hid.HidD_FreePreparsedData(ppd)
            except Exception:
                pass
            buf = ctypes.create_string_buffer(rep_len)
            rd = wintypes.DWORD(0)
            while not self._stop:
                ok = self._k32.ReadFile(wintypes.HANDLE(h), buf, rep_len, ctypes.byref(rd), None)
                if not ok or rd.value == 0:
                    break
                full = _parse_dualsense_full_packet(buf.raw[:rd.value])
                if full is not None:
                    act, tid, tx, ty = full.touch_active, full.touch_id, full.touch_x, full.touch_y
                    now = time.monotonic()
                    with self._lock:
                        if act and not full.touchpad:
                            if self._active and tid == self._touch_id and self._prev_pkt_y is not None:
                                pdy = ty - self._prev_pkt_y
                                dt = max(0.002, now - self._ts)
                                if -220 <= pdy <= 220:
                                    self._accum_dy += pdy
                                    if abs(pdy) >= 2:
                                        raw_vy = pdy / dt
                                        self._inst_vy = 0.5 * self._inst_vy + 0.5 * raw_vy
                                        self._last_move_ts = now
                                    elif (now - self._last_move_ts) > 0.028:
                                        self._inst_vy = 0.0
                            else:
                                self._accum_dy = 0.0
                                self._inst_vy = 0.0
                            self._prev_pkt_y = ty
                        else:
                            self._prev_pkt_y = None
                            self._accum_dy = 0.0
                            if full.touchpad:
                                self._inst_vy = 0.0
                        self._active = act
                        self._touch_id = tid
                        self._x = tx
                        self._y = ty
                        self._latest_snap = full
                        self._ts = now
            try:
                self._k32.CloseHandle(wintypes.HANDLE(h))
            except Exception:
                pass
            self._handle = None
            with self._lock:
                self._active = False
                self._latest_snap = None
            if not self._stop:
                time.sleep(1.0)


def _pov_to_dpad(pov: int) -> tuple[bool, bool, bool, bool]:
    if pov == 0xFFFF or pov > 36000:
        return (False, False, False, False)
    up = pov <= 4500 or pov >= 31500
    right = 4500 <= pov <= 13500
    down = 13500 <= pov <= 22500
    left = 22500 <= pov <= 31500
    return (up, down, left, right)


def _normalize_axis(raw: float, vmin: int, vmax: int) -> float:
    if vmax <= vmin:
        return 0.0
    mid = (float(vmin) + float(vmax)) * 0.5
    half = (float(vmax) - float(vmin)) * 0.5
    if half <= 0.0:
        return 0.0
    return (mid - raw) / half


def _has_active_input(snap: GamepadSnapshot | None) -> bool:
    if snap is None or not snap.connected:
        return False
    return bool(
        snap.btn_l3 or snap.btn_r3 or snap.l3_r3 or snap.touchpad or snap.touch_active
        or snap.dpad_up or snap.dpad_down or snap.dpad_left or snap.dpad_right
        or snap.btn_north or snap.btn_west or snap.btn_south or snap.btn_east
        or abs(snap.ry_norm) >= 0.28
    )


class UniversalGamepadPoller:
    """Polls PS5 DualSense / DirectInput (winmm) and XInput without interfering with gameplay."""

    def __init__(self):
        try:
            self.winmm = ctypes.WinDLL("winmm")
        except Exception:
            self.winmm = None

        self.xinput = None
        for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
            try:
                self.xinput = ctypes.WinDLL(dll)
                break
            except Exception:
                continue

        self._prev_edges: set[str] = set()
        self._caps_cache: dict[int, tuple[int, int, int, int, int, int, int, int]] = {}
        self._active_joy_id: int | None = None
        self._last_joy_scan: float = 0.0
        self._last_xi_scan: float = 0.0
        self._active_xi_id: int | None = None
        self._touch_reader = DualSenseTouchpadReader()
        self._touch_down = False
        self._touch_id = -1
        self._touch_mode = "undecided"  # "undecided" | "vertical" | "horizontal" | "clicked"
        self._touch_start_x = 0
        self._touch_start_y = 0
        self._horiz_anchor_x = 0
        self._horiz_step_count = 0
        self._touch_prev_y = 0
        self._touch_last_vy: float = 0.0
        self._touch_last_scroll_y = 0
        self._touch_horiz_fired = False
        self._touch_vert_locked = False
        self.last_snap = GamepadSnapshot(False, "none", "未连接手柄")

    def close(self):
        if self._touch_reader:
            self._touch_reader.close()

    def _read_winmm(self) -> GamepadSnapshot | None:
        if not self.winmm:
            return None
        ji = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=JOY_RETURNALL)
        if self._active_joy_id is not None:
            cand_ids = [self._active_joy_id]
        else:
            now = time.monotonic()
            if now - self._last_joy_scan < 2.0:
                return None
            self._last_joy_scan = now
            cand_ids = list(range(min(int(self.winmm.joyGetNumDevs()), 8)))

        best_fallback: GamepadSnapshot | None = None
        best_fallback_id: int | None = None
        for i in cand_ids:
            if self.winmm.joyGetPosEx(i, ctypes.byref(ji)) != JOYERR_NOERROR:
                if i == self._active_joy_id:
                    self._active_joy_id = None
                continue
            if i not in self._caps_cache:
                jc = JOYCAPS()
                if self.winmm.joyGetDevCapsW(i, ctypes.byref(jc), ctypes.sizeof(jc)) == JOYERR_NOERROR:
                    self._caps_cache[i] = (
                        int(jc.wMid), int(jc.wPid), int(jc.wNumButtons), int(jc.wCaps),
                        int(jc.wRmin), int(jc.wRmax), int(jc.wVmin), int(jc.wVmax),
                    )
                else:
                    self._caps_cache[i] = (0, 0, 12, 0, 0, 65535, 0, 65535)
            vid, pid, num_btns, w_caps, r_min, r_max, v_min, v_max = self._caps_cache[i]
            b = int(ji.dwButtons)
            up, down, left, right = _pov_to_dpad(int(ji.dwPOV))

            if (w_caps & 0x02) and r_max > r_min:
                ry_norm = _normalize_axis(float(ji.dwRpos), r_min, r_max)
            elif (w_caps & 0x08) and v_max > v_min and not (vid == SONY_VID and (pid in DUALSENSE_PIDS or pid in DUALSHOCK4_PIDS)):
                ry_norm = _normalize_axis(float(ji.dwVpos), v_min, v_max)
            else:
                ry_norm = 0.0

            if vid == SONY_VID and pid in DUALSENSE_PIDS:
                kind, label = "ps5", "PS5 DualSense"
                # DualSense HID button bits under Windows winmm:
                # 0:Square 1:Cross 2:Circle 3:Triangle 4:L1 5:R1 6:L2 7:R2 8:Create 9:Options 10:L3 11:R3 12:PS 13:Touchpad
                l1_r1 = bool((b & 0x0010) and (b & 0x0020))
                r1 = bool(b & 0x0020)
                l3_r3 = bool((b & 0x0400) and (b & 0x0800))
                btn_l3 = bool(b & 0x0400)
                btn_r3 = bool(b & 0x0800)
                touchpad = bool(b & 0x2000)
                btn_west = bool(b & 0x0001)
                btn_south = bool(b & 0x0002)
                btn_east = bool(b & 0x0004)
                btn_north = bool(b & 0x0008)
            elif vid == SONY_VID and pid in DUALSHOCK4_PIDS:
                kind, label = "ps4", "PS4 DualShock 4"
                l1_r1 = bool((b & 0x0010) and (b & 0x0020))
                r1 = bool(b & 0x0020)
                l3_r3 = bool((b & 0x0400) and (b & 0x0800))
                btn_l3 = bool(b & 0x0400)
                btn_r3 = bool(b & 0x0800)
                touchpad = bool(b & 0x2000)
                btn_west = bool(b & 0x0001)
                btn_south = bool(b & 0x0002)
                btn_east = bool(b & 0x0004)
                btn_north = bool(b & 0x0008)
            elif vid == SWITCH_VID:
                kind, label = "switch", "Switch Pro 手柄"
                # Switch Pro HID: 0:B 1:A 2:Y 3:X 4:L 5:R 6:ZL 7:ZR 8:- 9:+ 10:L3 11:R3
                l1_r1 = bool((b & 0x0010) and (b & 0x0020))
                r1 = bool(b & 0x0020)
                l3_r3 = bool((b & 0x0400) and (b & 0x0800))
                btn_l3 = bool(b & 0x0400)
                btn_r3 = bool(b & 0x0800)
                touchpad = False
                btn_south = bool(b & 0x0001)
                btn_east = bool(b & 0x0002)
                btn_west = bool(b & 0x0004)
                btn_north = bool(b & 0x0008)
            else:
                kind, label = "generic", "通用手柄"
                l1_r1 = bool((b & 0x0010) and (b & 0x0020))
                r1 = bool(b & 0x0020)
                if num_btns == 10:
                    # Legacy 10-button DirectInput pad (analog triggers on Z axis): 8=L3, 9=R3
                    btn_l3 = bool(b & 0x0100)
                    btn_r3 = bool(b & 0x0200)
                else:
                    # Standard >=12-button DirectInput pad: 8=Select/Back, 9=Start (never map menu buttons!), 10=L3, 11=R3
                    btn_l3 = bool(b & 0x0400)
                    btn_r3 = bool(b & 0x0800)
                l3_r3 = bool(btn_l3 and btn_r3)
                touchpad = False
                btn_south = bool(b & 0x0001)
                btn_east = bool(b & 0x0002)
                btn_west = bool(b & 0x0004)
                btn_north = bool(b & 0x0008)

            if abs(ry_norm) < 0.28:
                ry_norm = 0.0
            t_act, t_x, t_y, t_dy, t_vy = self._touch_reader.get_touch() if kind == "ps5" else (False, 0, 0, 0.0, 0.0)
            snap = GamepadSnapshot(
                connected=True,
                kind=kind,
                label=label,
                l1_r1=l1_r1,
                r1=r1,
                dpad_up=up,
                dpad_down=down,
                dpad_left=left,
                dpad_right=right,
                l3_r3=l3_r3,
                btn_l3=btn_l3,
                btn_r3=btn_r3,
                touchpad=touchpad,
                btn_north=btn_north,
                btn_west=btn_west,
                btn_south=btn_south,
                btn_east=btn_east,
                ry_norm=ry_norm,
                touch_active=t_act,
                touch_x=t_x,
                touch_y=t_y,
                touch_dy=t_dy,
                touch_vy=t_vy,
            )
            if kind in ("ps5", "ps4", "switch") or _has_active_input(snap):
                self._active_joy_id = i
                return snap
            if best_fallback is None:
                best_fallback = snap
                best_fallback_id = i
        if best_fallback is not None:
            self._active_joy_id = best_fallback_id
            return best_fallback
        return None

    def _read_xinput(self) -> GamepadSnapshot | None:
        if not self.xinput:
            return None
        st = XINPUT_STATE()
        if self._active_xi_id is not None:
            xi_ids = [self._active_xi_id]
        else:
            now = time.monotonic()
            if now - self._last_xi_scan < 2.5:
                return None
            self._last_xi_scan = now
            xi_ids = [0, 1, 2, 3]
        for u in xi_ids:
            if self.xinput.XInputGetState(u, ctypes.byref(st)) != 0:
                if u == self._active_xi_id:
                    self._active_xi_id = None
                continue
            self._active_xi_id = u
            gp = st.Gamepad
            w = int(gp.wButtons)
            ry_norm = float(gp.sThumbRY) / 32767.0
            if abs(ry_norm) < 0.28:
                ry_norm = 0.0
            return GamepadSnapshot(
                connected=True,
                kind="xbox",
                label="XInput 手柄",
                l1_r1=bool((w & 0x0100) and (w & 0x0200)),
                r1=bool(w & 0x0200),
                dpad_up=bool(w & 0x0001),
                dpad_down=bool(w & 0x0002),
                dpad_left=bool(w & 0x0004),
                dpad_right=bool(w & 0x0008),
                l3_r3=bool((w & 0x0040) and (w & 0x0080)),
                btn_l3=bool(w & 0x0040),
                btn_r3=bool(w & 0x0080),
                touchpad=False,
                btn_south=bool(w & 0x1000),
                btn_east=bool(w & 0x2000),
                btn_west=bool(w & 0x4000),
                btn_north=bool(w & 0x8000),
                ry_norm=ry_norm,
            )
        return None

    def poll_actions(self, snap_override: GamepadSnapshot | None = None) -> tuple[GamepadSnapshot, list[str]]:
        """Poll controller state and emit debounced semantic actions + smooth scroll."""
        if snap_override is not None:
            snap = snap_override
        else:
            # Fast-path: 252Hz atomic DualSense HID snapshot (0.003ms, zero winmm/XInput syscall overhead!)
            ds_snap = self._touch_reader.get_full_snap() if self._touch_reader else None
            if ds_snap is not None:
                snap = ds_snap
            else:
                hid_snap = self._read_winmm()
                xi_snap = self._read_xinput()
                if _has_active_input(xi_snap) and not _has_active_input(hid_snap):
                    snap = xi_snap
                elif _has_active_input(hid_snap) and not _has_active_input(xi_snap):
                    snap = hid_snap
                elif hid_snap and hid_snap.kind in ("ps5", "ps4", "switch"):
                    snap = hid_snap
                else:
                    snap = xi_snap or hid_snap or GamepadSnapshot(False, "none", "未连接手柄")

        self.last_snap = snap
        if not snap.connected:
            self._prev_edges.clear()
            return snap, []

        held_now: set[str] = set()
        if snap.l3_r3 or (snap.touchpad and not snap.btn_l3 and not snap.btn_r3):
            held_now.add("toggle_panel")
        if snap.touchpad and (snap.btn_r3 or snap.btn_l3) and not snap.l3_r3:
            held_now.add("open_amiibo")
        if snap.btn_l3 and not snap.btn_r3 and not snap.touchpad and snap.btn_east:
            held_now.add("load_amiibo")
        if snap.btn_r3 and not snap.btn_l3 and not snap.touchpad:
            if snap.dpad_left:
                held_now.add("prev_view")
            if snap.dpad_right:
                held_now.add("next_view")
            if snap.dpad_up:
                held_now.add("scroll_up")
            if snap.dpad_down:
                held_now.add("scroll_down")
            if snap.btn_north:
                held_now.add("next_region")
            if snap.btn_west:
                held_now.add("prev_region")
            if snap.btn_south:
                held_now.add("snap_live_region")

        actions = [
            act for act in (
                "toggle_panel", "open_amiibo", "prev_view", "next_view",
                "scroll_up", "scroll_down", "next_region", "prev_region",
                "snap_live_region", "load_amiibo",
            )
            if act in held_now and act not in self._prev_edges
        ]
        self._prev_edges = held_now

        # Continuous smooth scrolling while holding R3 + Right Stick tilt (if tilted)
        if snap.btn_r3 and not snap.btn_l3 and abs(snap.ry_norm) >= 0.35:
            actions.append("stick_up" if snap.ry_norm > 0 else "stick_down")

        # Smart PS5 DualSense Touchpad Intent Classifier:
        # Mutually-exclusive axis lock ("undecided" -> "horizontal" | "vertical" | "clicked")
        # - Immediate click suppression: pressing physical touchpad button cancels stray thumb squish
        # - Horizontal lock (|dx| >= 42 & |dx| >= |dy|*1.35): crisp tab/mask switch at 150 units (~4mm), zero accidental scroll
        # - Vertical lock (|dy| >= 22 & |dy| > |dx|*0.95): instant 1:1 pixel tracking, zero accidental tab flip on curved strokes
        hw_dy = snap.touch_dy
        snap.touch_dy = 0.0
        snap.touch_lifted = False

        if snap.touchpad:
            self._touch_mode = "clicked"
            self._touch_last_vy = 0.0
        elif snap.touch_active:
            new_contact = (not self._touch_down) or (snap.touch_id >= 0 and self._touch_id >= 0 and snap.touch_id != self._touch_id)
            if new_contact:
                self._touch_down = True
                self._touch_id = snap.touch_id
                self._touch_mode = "undecided"
                self._touch_start_x = snap.touch_x
                self._touch_start_y = snap.touch_y
                self._horiz_anchor_x = snap.touch_x
                self._horiz_step_count = 0
                self._touch_prev_y = snap.touch_y
                self._touch_last_vy = 0.0
                self._touch_last_scroll_y = snap.touch_y
                self._touch_horiz_fired = False
                self._touch_vert_locked = False
            elif self._touch_mode != "clicked":
                dx = snap.touch_x - self._touch_start_x
                dy_total = snap.touch_y - self._touch_start_y
                fallback_dy = float(snap.touch_y - self._touch_prev_y)
                self._touch_prev_y = snap.touch_y
                eff_dy = hw_dy if hw_dy != 0.0 else fallback_dy

                if self._touch_mode == "undecided":
                    if abs(dx) >= 80 and abs(dx) >= abs(dy_total) * 1.55:
                        self._touch_mode = "horizontal"
                        self._horiz_anchor_x = self._touch_start_x
                    elif abs(dy_total) >= 22 and abs(dy_total) > abs(dx) * 0.85:
                        self._touch_mode = "vertical"
                        self._touch_vert_locked = True
                        # Include initial lock travel smoothly so first frame feels instant (zero deadzone jump)
                        eff_dy = float(dy_total) * 0.55

                if self._touch_mode == "horizontal":
                    # Strictly 1 swipe = 1 tab switch per finger contact, requiring a deliberate >=340-unit (~9mm) stroke
                    if not self._touch_horiz_fired and abs(dx) >= 340:
                        actions.append("next_view" if dx > 0 else "prev_view")
                        self._touch_horiz_fired = True
                elif self._touch_mode == "vertical":
                    if -260.0 <= eff_dy <= 260.0:
                        snap.touch_dy = eff_dy
                    self._touch_last_vy = snap.touch_vy if snap_override is None else (eff_dy * 120.0)
                    dy_step = snap.touch_y - self._touch_last_scroll_y
                    if abs(dy_step) >= 48:
                        actions.append("scroll_down" if dy_step > 0 else "scroll_up")
                        self._touch_last_scroll_y = snap.touch_y
        else:
            if self._touch_down and self._touch_mode == "vertical":
                snap.touch_lifted = True
                snap.touch_vy = self._touch_last_vy
            self._touch_down = False
            self._touch_id = -1
            self._touch_mode = "undecided"
            self._touch_last_vy = 0.0
            self._touch_horiz_fired = False
            self._touch_vert_locked = False

        return snap, actions
