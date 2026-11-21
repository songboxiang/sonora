#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Squeezelite GUI 原创应用图标 / logo（Lyrion Material 风格）。

设计语言：Material 圆角方形 + 浮动操作按钮(FAB) + 声波弧线，
配色取自 LMS Material Skin 的官方 Lyrion 色（#589e81 / #6cac92 / #0d292d）。
仅设计阶段需要 Pillow；最终用户只需 assets/app.icns。

用法： python3 assets/make_icon.py
产出： assets/logo.svg、assets/logo-1024.png、assets/app.icns
"""
import os
import struct
import math
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S, SS, M = 1024, 3, 64          # 画布、超采样倍数、四周留白
W = S * SS

GREEN_TOP = (108, 172, 146)     # #6cac92
GREEN_BOT = (63, 122, 97)      # #3f7a61
DEEP = (13, 41, 45)            # #0d292d
WHITE = (255, 255, 255)


def q(v):
    return int(round(v * SS))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_master():
    # 1) 圆角方形遮罩（macOS Big Sur 风格，四周留白）
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [q(M), q(M), q(S - M), q(S - M)], radius=q(200), fill=255)

    # 2) 竖直渐变 + 顶部高光（Material elevation）
    bg = Image.new("RGBA", (W, W))
    px = bg.load()
    for y in range(W):
        c = lerp(GREEN_TOP, GREEN_BOT, y / (W - 1))
        for x in range(W):
            px[x, y] = (c[0], c[1], c[2], 255)
    hi = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    for y in range(q(M), q(M + 250)):
        a = int(44 * (1 - (y - q(M)) / q(250)))
        hd.line([(0, y), (W, y)], fill=(255, 255, 255, a))
    bg = Image.alpha_composite(bg, hi)
    img = Image.composite(bg, Image.new("RGBA", (W, W), (0, 0, 0, 0)), mask)

    cx, cy, R = q(512), q(498), q(186)

    # 3) FAB 投影
    shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse([cx - R, cy - R + q(16), cx + R, cy + R + q(16)],
               fill=(6, 23, 26, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(q(18)))
    img = Image.alpha_composite(img, shadow)

    # 4) 声波弧线（左右各两条，透明度递减）
    waves = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    wd = ImageDraw.Draw(waves)
    for rr, alpha, lw in ((262, 205, 24), (316, 115, 24)):
        r = q(rr)
        wd.arc([cx - r, cy - r, cx + r, cy + r], -48, 48,
               fill=(255, 255, 255, alpha), width=q(lw))
        wd.arc([cx - r, cy - r, cx + r, cy + r], 132, 228,
               fill=(255, 255, 255, alpha), width=q(lw))
    img = Image.alpha_composite(img, waves)

    # 5) 白色 FAB + 播放三角
    d = ImageDraw.Draw(img)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(*WHITE, 255))
    d.polygon([(q(456), q(396)), (q(456), q(600)), (q(601), q(498))],
              fill=(*DEEP, 255))

    return img.resize((S, S), Image.LANCZOS)


SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"
     width="1024" height="1024" role="img" aria-label="Squeezelite GUI">
  <title>Squeezelite GUI - Lyrion Material style logo</title>
  <defs>
    <linearGradient id="lyrion" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#6cac92"/>
      <stop offset="1" stop-color="#3f7a61"/>
    </linearGradient>
    <clipPath id="squircle"><rect x="64" y="64" width="896" height="896" rx="200"/></clipPath>
    <filter id="fabShadow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="18"/>
    </filter>
  </defs>
  <g clip-path="url(#squircle)">
    <rect x="64" y="64" width="896" height="896" fill="url(#lyrion)"/>
    <rect x="64" y="64" width="896" height="250" fill="#ffffff" opacity="0.10"/>
  </g>
  <g fill="none" stroke="#ffffff" stroke-width="24" stroke-linecap="round">
    <path d="M687 303 A262 262 0 0 1 687 693" opacity="0.80"/>
    <path d="M337 693 A262 262 0 0 1 337 303" opacity="0.80"/>
    <path d="M723 263 A316 316 0 0 1 723 733" opacity="0.45"/>
    <path d="M301 733 A316 316 0 0 1 301 263" opacity="0.45"/>
  </g>
  <circle cx="512" cy="514" r="186" fill="#062024" opacity="0.35" filter="url(#fabShadow)"/>
  <circle cx="512" cy="498" r="186" fill="#ffffff"/>
  <path d="M456 396 L456 600 L601 498 Z" fill="#0d292d"/>
</svg>
'''


def build_icns(pngs):
    # macOS ICNS：icns magic + 总长 + [type + 段长 + PNG 数据]...
    types = [(b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
             (b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)]
    body = b""
    for t, sz in types:
        data = pngs[sz]
        body += t + struct.pack(">I", 8 + len(data)) + data
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def main():
    master = make_master()
    master.save(os.path.join(HERE, "logo-1024.png"))

    pngs = {}
    for sz in (16, 32, 64, 128, 256, 512, 1024):
        im = master if sz == 1024 else master.resize((sz, sz), Image.LANCZOS)
        buf = BytesIO()
        im.save(buf, format="PNG", optimize=True)
        pngs[sz] = buf.getvalue()

    icns = build_icns(pngs)
    with open(os.path.join(HERE, "app.icns"), "wb") as f:
        f.write(icns)
    with open(os.path.join(HERE, "logo.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)

    # 自检
    assert icns[:4] == b"icns"
    assert struct.unpack(">I", icns[4:8])[0] == len(icns)
    off, entries = 8, []
    while off < len(icns):
        t = icns[off:off + 4]
        ln = struct.unpack(">I", icns[off + 4:off + 8])[0]
        assert icns[off + 8:off + 12] == b"\x89PNG", t
        entries.append((t.decode(), ln - 8))
        off += ln
    assert off == len(icns)
    print("ICON_OK", "icns_bytes=", len(icns),
          "entries=", entries,
          "master=", master.size, master.mode)
    for name in ("logo.svg", "logo-1024.png", "app.icns", "make_icon.py"):
        print("  ", name, os.path.getsize(os.path.join(HERE, name)), "bytes")


if __name__ == "__main__":
    main()
