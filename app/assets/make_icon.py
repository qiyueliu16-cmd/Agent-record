#!/usr/bin/env python3
"""生成「Agent执行记录」的 macOS 图标（.icns）。

纯几何绘制，不依赖字体与中文字符：深墨绿圆角底 + 浅色记录卡 +
三行「步骤 + 决策点」+ 右下角结果图块。对应「记代码、记选择、出带图报告」。

    /usr/bin/python3 assets/make_icon.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
S = 1024
SS = 2
W = S * SS
PAPER = (250, 250, 246, 255)
INK = (18, 59, 49, 255)
MINT = (122, 199, 168, 255)
SOFT = (197, 214, 205, 255)
LINE = (222, 230, 224, 255)


def k(v: float) -> int:
    return round(v * W / S)


def main() -> None:
    canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))

    bg = Image.new("RGB", (1, W))
    px = bg.load()
    for y in range(W):
        t = y / (W - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip((36, 96, 79), (12, 44, 37)))
    grad = bg.resize((W, W)).convert("RGBA")
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle((k(44), k(44), W - k(44), W - k(44)),
                                           radius=k(196), fill=255)
    canvas.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((k(44), k(44), W - k(44), W - k(44)), radius=k(196),
                        outline=(255, 255, 255, 38), width=k(3))

    # 记录卡
    card = (k(168), k(196), W - k(168), W - k(168))
    shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (card[0] + k(8), card[1] + k(16), card[2] + k(8), card[3] + k(16)),
        radius=k(52), fill=(0, 0, 0, 90))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(k(18))))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(card, radius=k(52), fill=PAPER)

    # 标题栏：三个小圆点 + 标题条
    for i, color in enumerate(((214, 108, 92), (222, 178, 92), (126, 180, 140))):
        cx = card[0] + k(58 + i * 46)
        cy = card[1] + k(52)
        d.ellipse((cx - k(11), cy - k(11), cx + k(11), cy + k(11)), fill=color + (255,))
    d.rounded_rectangle((card[0] + k(230), card[1] + k(42), card[0] + k(430),
                         card[1] + k(64)), radius=k(11), fill=SOFT)

    # 三行记录：左侧序号圆点 + 文本条 + 右侧决策方块
    for i, width in enumerate((0.62, 0.48, 0.56)):
        y = card[1] + k(150 + i * 116)
        r = k(24)
        cx = card[0] + k(70)
        d.ellipse((cx - r, y - r, cx + r, y + r), fill=INK)
        d.ellipse((cx - r + k(9), y - r + k(9), cx + r - k(9), y + r - k(9)), fill=MINT)
        d.rounded_rectangle((card[0] + k(126), y - k(13),
                             card[0] + k(126 + 420 * width), y + k(13)),
                            radius=k(13), fill=(150, 178, 165, 255) if i % 2 == 0 else SOFT)
        d.rounded_rectangle((card[0] + k(126), y + k(32),
                             card[0] + k(126 + 260 * width), y + k(46)),
                            radius=k(7), fill=LINE)
        # 决策点：A / B 选项方块
        bx = card[2] - k(150)
        d.rounded_rectangle((bx, y - k(28), bx + k(56), y + k(28)),
                            radius=k(10), fill=(232, 239, 233, 255))
        d.rounded_rectangle((bx + k(12), y - k(14), bx + k(44), y + k(14)),
                            radius=k(6), fill=MINT if i == 1 else (168, 190, 178, 255))
        d.line((card[0] + k(52), y + k(58), card[2] - k(52), y + k(58)),
               fill=LINE, width=k(3))

    # 右下角结果图块（小图表）
    fig = (card[2] - k(230), card[3] - k(230), card[2] - k(52), card[3] - k(52))
    d.rounded_rectangle(fig, radius=k(24), fill=(236, 243, 237, 255))
    base = fig[3] - k(38)
    for i, h in enumerate((70, 118, 92)):
        x = fig[0] + k(42 + i * 48)
        d.rounded_rectangle((x, base - k(h), x + k(30), base), radius=k(6),
                            fill=MINT if i == 1 else (150, 178, 165, 255))

    icon = canvas.resize((S, S), Image.LANCZOS)
    icon.save(HERE / "AppIcon.png")

    iconset = HERE / "AppIcon.iconset"
    iconset.mkdir(exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            size = base * scale
            name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
            icon.resize((size, size), Image.LANCZOS).save(iconset / name)
    out = HERE / "AppIcon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    print(f"icns {out} {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
