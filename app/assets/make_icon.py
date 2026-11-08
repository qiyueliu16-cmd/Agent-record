#!/usr/bin/env python3
"""生成「Agent执行记录」的 macOS 图标 AppIcon.icns。

纯 Python 标准库实现（zlib + struct 手写 PNG / icns），**不需要 Pillow、
不需要 iconutil、不需要任何第三方包**。图形语言与工作台一致：
深墨绿圆角底 + 浅色记录卡 + 三行「步骤 + 决策点」+ 结果图块。

    python3 app/assets/make_icon.py

build_desktop_app.py 会在缺少图标时自动调用本脚本，因此下载者
无需手工执行，也不会因为没装 Pillow 而得到一个无图标的 .app。
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "AppIcon.icns"
S = 512

BG_TOP = (36, 96, 79)
BG_BOTTOM = (12, 44, 37)
PAPER = bytes((250, 250, 246, 255))
INK = bytes((18, 59, 49, 255))
MINT = bytes((122, 199, 168, 255))
SOFT = bytes((197, 214, 205, 255))
LINE = bytes((222, 230, 224, 255))
STRIPE = bytes((150, 178, 165, 255))
ACCENT = bytes((165, 92, 67, 255))
FIG_BG = bytes((236, 243, 237, 255))
DOT = (bytes((214, 108, 92, 255)), bytes((222, 178, 92, 255)), bytes((126, 180, 140, 255)))
TRANSPARENT = bytes((0, 0, 0, 0))


def k(v: float) -> int:
    return round(v * S / 512)


def rounded(x: int, y: int, x0: int, y0: int, x1: int, y1: int, r: int) -> bool:
    """点 (x, y) 是否落在圆角矩形内。"""
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    dx = max(x0 + r - x, 0, x - (x1 - r))
    dy = max(y0 + r - y, 0, y - (y1 - r))
    return dx * dx + dy * dy <= r * r


def circle(x: int, y: int, cx: int, cy: int, r: int) -> bool:
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def setpx(buf: bytearray, x: int, y: int, color: bytes) -> None:
    i = (y * S + x) * 4
    buf[i:i + 4] = color


def render() -> bytes:
    buf = bytearray(S * S * 4)
    # 底：整块圆角渐变
    for y in range(S):
        t = y / (S - 1)
        grad = bytes(tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,))
        for x in range(k(44), S - k(44) + 1):
            if rounded(x, y, k(44), k(44), S - k(44), S - k(44), k(98)):
                setpx(buf, x, y, grad)

    # 记录卡（只在卡片包围盒内判断内部元素，避免全画布逐像素判断）
    for y in range(k(96), k(420) + 1):
        for x in range(k(120), k(392) + 1):
            if not rounded(x, y, k(120), k(96), k(392), k(420), k(24)):
                continue
            c = PAPER
            if rounded(x, y, k(146), k(126), k(300), k(146), k(10)):
                c = SOFT
            for i in range(3):
                if circle(x, y, k(150 + i * 26), k(126), k(7)):
                    c = DOT[i]
            if rounded(x, y, k(336), k(122), k(366), k(152), k(9)):
                c = MINT
            for base in (178, 232, 286):
                if k(base) - k(30) <= y <= k(base) + k(36):
                    if circle(x, y, k(156), k(base + 3), k(13)):
                        c = INK
                    elif circle(x, y, k(156), k(base + 3), k(8)):
                        c = MINT
                    elif rounded(x, y, k(182), k(base - 8), k(182 + 150), k(base + 4), k(6)):
                        c = STRIPE if base != 232 else SOFT
                    elif rounded(x, y, k(182), k(base + 14), k(182 + 92), k(base + 22), k(4)):
                        c = LINE
                    elif rounded(x, y, k(326), k(base - 18), k(360), k(base + 18), k(8)):
                        c = FIG_BG
                    elif rounded(x, y, k(334), k(base - 10), k(352), k(base + 10), k(5)):
                        c = MINT if base == 232 else STRIPE
                if y == k(base + 34) and k(146) <= x <= k(366):
                    c = LINE
            if rounded(x, y, k(250), k(330), k(366), k(396), k(14)):
                c = FIG_BG
            for i, (bx, bh) in enumerate(((268, 30), (296, 48), (324, 38))):
                if rounded(x, y, k(bx), k(382 - bh), k(bx + 18), k(382), k(5)):
                    c = MINT if i == 1 else (ACCENT if i == 0 else STRIPE)
            setpx(buf, x, y, c)
    return bytes(buf)


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def to_png(rgba: bytes) -> bytes:
    ihdr = struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0)
    scanlines = b"".join(b"\x00" + rgba[y * S * 4:(y + 1) * S * 4] for y in range(S))
    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", zlib.compress(scanlines, 9))
            + png_chunk(b"IEND", b""))


def to_icns(png: bytes) -> bytes:
    # ic09 = 512x512 PNG；条目头 8 字节 = 类型 + 长度
    entry = b"ic09" + struct.pack(">I", 8 + len(png)) + png
    return b"icns" + struct.pack(">I", 8 + len(entry)) + entry


def main() -> int:
    data = to_icns(to_png(render()))
    OUT.write_bytes(data)
    print(f"已生成 {OUT}  ({len(data) / 1024:.0f} KB，纯标准库)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
