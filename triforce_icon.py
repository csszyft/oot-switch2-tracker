"""Pure-Python stdlib procedural golden Triforce icon renderer (Win32 HICON + BMP/PNG ICO)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
from pathlib import Path
import struct
import zlib

_SQRT3 = 1.7320508075688772


def _point_in_tri(px: float, py: float, ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> bool:
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = (d1 < 0.0) or (d2 < 0.0) or (d3 < 0.0)
    has_pos = (d1 > 0.0) or (d2 > 0.0) or (d3 > 0.0)
    return not (has_neg and has_pos)


def _signed_dist_rrect(px: float, py: float, cx: float, cy: float, hx: float, hy: float, r: float) -> float:
    dx = abs(px - cx) - (hx - r)
    dy = abs(py - cy) - (hy - r)
    ox = dx if dx > 0.0 else 0.0
    oy = dy if dy > 0.0 else 0.0
    inside = dx if dx > dy else dy
    if inside > 0.0:
        inside = 0.0
    return math.hypot(ox, oy) + inside - r


def _blend(dst: tuple[float, float, float, float], src: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    sr, sg, sb, sa = src
    if sa <= 0.0:
        return dst
    if sa >= 1.0:
        return src
    dr, dg, db, da = dst
    out_a = sa + da * (1.0 - sa)
    if out_a <= 1e-6:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        (sr * sa + dr * da * (1.0 - sa)) / out_a,
        (sg * sa + dg * da * (1.0 - sa)) / out_a,
        (sb * sa + db * da * (1.0 - sa)) / out_a,
        out_a,
    )


def render_triforce_bgra(size: int) -> bytes:
    """Render crisp anti-aliased size x size BGRA (top-down, straight alpha) Triforce badge in pure stdlib Python."""
    s = float(size)
    cx = s * 0.5
    cy = s * 0.5
    pad = s * (0.03 if size <= 32 else 0.045)
    half = s * 0.5 - pad
    rad = s * 0.21
    rim_w = max(1.15, s * (0.056 if size <= 32 else 0.040))

    # Centered equilateral Triforce geometry
    t_cy = s * 0.5 + s * 0.026
    tri_h = s * (0.64 if size <= 32 else 0.56)
    half_w = tri_h / _SQRT3
    top = (cx, t_cy - tri_h * 0.56)
    bl = (cx - half_w, t_cy + tri_h * 0.44)
    br = (cx + half_w, t_cy + tri_h * 0.44)
    mid_l = ((top[0] + bl[0]) * 0.5, (top[1] + bl[1]) * 0.5)
    mid_r = ((top[0] + br[0]) * 0.5, (top[1] + br[1]) * 0.5)
    mid_b = ((bl[0] + br[0]) * 0.5, (bl[1] + br[1]) * 0.5)

    sub_tris = (
        (top, mid_l, mid_r),
        (mid_l, bl, mid_b),
        (mid_r, mid_b, br),
    )
    tri_centers = tuple(
        ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0)
        for a, b, c in sub_tris
    )
    # Gap between the 3 sub-triangles (tighter on small icons, clean crisp dark divider)
    gap = max(0.32, s * (0.012 if size <= 32 else 0.008))

    # Bounding boxes for fast skipping
    tri_min_y = top[1] - 1.5
    tri_max_y = bl[1] + 1.5
    tri_min_x = bl[0] - 1.5
    tri_max_x = br[0] + 1.5

    def _sample(sx: float, sy: float) -> tuple[float, float, float, float]:
        sd = _signed_dist_rrect(sx, sy, cx, cy, half, half, rad)
        if sd >= 0.65:
            return (0.0, 0.0, 0.0, 0.0)
        # Smooth outer edge AA
        badge_a = 1.0 if sd <= -0.65 else max(0.0, min(1.0, (0.65 - sd) / 1.30))

        # Obsidian fill + subtle warm radial glow behind Triforce
        r, g, b = 14.0, 19.0, 29.0
        if size >= 40:
            gd = math.hypot(sx - cx, sy - t_cy) / (s * 0.36)
            if gd < 1.0:
                glow = (1.0 - gd) ** 2 * 0.16
                r += 240.0 * glow
                g += 190.0 * glow
                b += 65.0 * glow

        # Antique gold border rim
        if sd > -rim_w - 0.65:
            rim_cov = 1.0 if sd >= -rim_w + 0.65 else max(0.0, min(1.0, (sd - (-rim_w - 0.65)) / 1.30))
            t_col = (224.0, 186.0, 106.0)
            r = r * (1.0 - rim_cov) + t_col[0] * rim_cov
            g = g * (1.0 - rim_cov) + t_col[1] * rim_cov
            b = b * (1.0 - rim_cov) + t_col[2] * rim_cov

        col = (r, g, b, badge_a)

        # Triforce facets
        if tri_min_x <= sx <= tri_max_x and tri_min_y <= sy <= tri_max_y:
            for (p0, p1, p2), (tcx, tcy) in zip(sub_tris, tri_centers):
                # Shrink slightly from centroid for crisp inter-triangle gap
                if _point_in_tri(sx, sy, p0[0], p0[1], p1[0], p1[1], p2[0], p2[1]):
                    # Check edge distance for bevel / divider line
                    e0 = abs((p1[0] - p0[0]) * (sy - p0[1]) - (p1[1] - p0[1]) * (sx - p0[0])) / math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                    e1 = abs((p2[0] - p1[0]) * (sy - p1[1]) - (p2[1] - p1[1]) * (sx - p1[0])) / math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    e2 = abs((p0[0] - p2[0]) * (sy - p2[1]) - (p0[1] - p2[1]) * (sx - p2[0])) / math.hypot(p0[0] - p2[0], p0[1] - p2[1])
                    min_e = e0 if e0 < e1 else e1
                    if e2 < min_e:
                        min_e = e2
                    if min_e < gap:
                        break
                    # 3D bevel facet shading
                    if size >= 28:
                        if _point_in_tri(sx, sy, p0[0], p0[1], p1[0], p1[1], tcx, tcy):
                            tr, tg, tb = 255.0, 232.0, 134.0
                        elif _point_in_tri(sx, sy, p0[0], p0[1], tcx, tcy, p2[0], p2[1]):
                            tr, tg, tb = 244.0, 198.0, 76.0
                        else:
                            tr, tg, tb = 214.0, 158.0, 42.0
                        if min_e < gap + 0.9:
                            tr = min(255.0, tr + 14.0)
                            tg = min(255.0, tg + 14.0)
                            tb = min(255.0, tb + 22.0)
                    else:
                        tr, tg, tb = 250.0, 210.0, 88.0
                    col = _blend(col, (tr, tg, tb, 1.0))
                    break
        return col

    offsets = (0.125, 0.375, 0.625, 0.875)
    out = bytearray(size * size * 4)
    idx = 0
    for y in range(size):
        fy = float(y)
        in_tri_y = tri_min_y <= fy + 1.0 and fy <= tri_max_y
        for x in range(size):
            fx = float(x)
            sd_c = _signed_dist_rrect(fx + 0.5, fy + 0.5, cx, cy, half, half, rad)
            need_ss = abs(sd_c) < 1.8 or abs(sd_c + rim_w) < 1.8 or (
                in_tri_y and tri_min_x <= fx + 1.0 and fx <= tri_max_x
            )
            if not need_ss:
                sr, sg, sb, sa = _sample(fx + 0.5, fy + 0.5)
            else:
                ar = ag = ab = aa = 0.0
                for oy in offsets:
                    sy = fy + oy
                    for ox in offsets:
                        cr, cg, cb, ca = _sample(fx + ox, sy)
                        if ca > 0.0:
                            ar += cr * ca
                            ag += cg * ca
                            ab += cb * ca
                            aa += ca
                if aa > 1e-6:
                    sr, sg, sb = ar / aa, ag / aa, ab / aa
                    sa = aa / 16.0
                else:
                    sr = sg = sb = sa = 0.0
            a_i = max(0, min(255, int(round(sa * 255.0))))
            if a_i == 0:
                idx += 4
            else:
                out[idx] = max(0, min(255, int(round(sb))))
                out[idx + 1] = max(0, min(255, int(round(sg))))
                out[idx + 2] = max(0, min(255, int(round(sr))))
                out[idx + 3] = a_i
                idx += 4
    return bytes(out)


def _bgra_to_png(size: int, bgra: bytes) -> bytes:
    stride = size * 4
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        row = bgra[y * stride : (y + 1) * stride]
        for i in range(0, stride, 4):
            raw.extend((row[i + 2], row[i + 1], row[i], row[i + 3]))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def _bgra_to_dib_ico_entry(size: int, bgra: bytes) -> bytes:
    """Build standard Windows BITMAPINFOHEADER + bottom-up BGRA + 1bpp AND mask for crisp ICO/PE resources."""
    stride = size * 4
    and_stride = ((size + 31) // 32) * 4
    bih = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, size * stride, 0, 0, 0, 0)
    xor_bits = bytearray(size * stride)
    and_bits = bytearray(size * and_stride)
    for y in range(size):
        src_y = size - 1 - y
        src_row = bgra[src_y * stride : (src_y + 1) * stride]
        xor_bits[y * stride : (y + 1) * stride] = src_row
        for x in range(size):
            if src_row[x * 4 + 3] == 0:
                and_bits[y * and_stride + (x >> 3)] |= 0x80 >> (x & 7)
    return bih + bytes(xor_bits) + bytes(and_bits)


def build_ico_bytes(sizes: tuple[int, ...] = (256, 128, 64, 48, 40, 32, 24, 20, 16)) -> bytes:
    """Build Windows-spec ICO binary: uncompressed 32-bit DIB for <=128px, PNG for 256px."""
    blobs: list[bytes] = []
    for sz in sizes:
        bgra = render_triforce_bgra(sz)
        blobs.append(_bgra_to_png(sz, bgra) if sz >= 256 else _bgra_to_dib_ico_entry(sz, bgra))
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = []
    offset = 6 + 16 * len(sizes)
    for sz, blob in zip(sizes, blobs):
        wb = 0 if sz >= 256 else sz
        entries.append(struct.pack("<BBBBHHII", wb, wb, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    return header + b"".join(entries) + b"".join(blobs)


def create_win32_hicon(size: int) -> int:
    """Create a DPI-exact 32-bit RGBA Win32 HICON in memory directly from procedural BGRA (zero .ico file needed)."""
    try:
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.CreateIconFromResourceEx.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        u32.CreateIconFromResourceEx.restype = wintypes.HICON
        dib = _bgra_to_dib_ico_entry(size, render_triforce_bgra(size))
        buf = ctypes.create_string_buffer(dib)
        h = int(u32.CreateIconFromResourceEx(buf, len(dib), True, 0x00030000, size, size, 0) or 0)
        return h
    except Exception:
        return 0


def apply_win32_triforce_icon(hwnd: int) -> list[int]:
    """Bind DPI-exact procedural Triforce ICON_BIG & ICON_SMALL handles onto a Win32 HWND."""
    if not hwnd:
        return []
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.SendMessageW.restype = ctypes.c_ssize_t
    u32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    u32.SetClassLongPtrW.restype = ctypes.c_void_p
    handles: list[int] = []
    try:
        try:
            dpi = int(u32.GetDpiForWindow(hwnd) or 96)
        except Exception:
            dpi = 96
        try:
            cx_big = int(u32.GetSystemMetricsForDpi(11, dpi) or 32)
            cx_sm = int(u32.GetSystemMetricsForDpi(49, dpi) or 16)
        except Exception:
            cx_big = int(u32.GetSystemMetrics(11) or 32)
            cx_sm = int(u32.GetSystemMetrics(49) or 16)
        h_big = create_win32_hicon(cx_big)
        h_sm = create_win32_hicon(cx_sm)
        if h_big:
            handles.append(h_big)
            u32.SendMessageW(hwnd, 0x0080, 1, h_big)
            u32.SetClassLongPtrW(hwnd, -14, h_big)
        if h_sm:
            handles.append(h_sm)
            u32.SendMessageW(hwnd, 0x0080, 0, h_sm)
            u32.SetClassLongPtrW(hwnd, -34, h_sm)
    except Exception:
        pass
    return handles


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate standard Windows Triforce .ico procedurally")
    ap.add_argument("--write-ico", required=True, help="Output .ico path")
    args = ap.parse_args()
    out_p = Path(args.write_ico)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_bytes(build_ico_bytes())
    print(f"Wrote {out_p} ({out_p.stat().st_size} bytes)")
