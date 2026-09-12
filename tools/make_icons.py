#!/usr/bin/env python3
"""生成 web/icons/ 下的全部图标资源。

为什么是手写光栅器而不是 Pillow：本机没有可用的图像库，而这个图标只有
圆角矩形和四个方格，用不上通用图形库。几何定义只此一处，改设计改这里重跑即可。

图形的含义与站点一致：墨色底 + 2x2 教室格，其中一格是绿的（绿 = 空闲）。
出来就是站点界面上那个教室芯片网格的缩写。

用法：
    python tools/make_icons.py
"""

import os
import struct
import zlib

# 与 web/style.css 的 token 对齐，别在别处另写一套颜色
INK = (24, 24, 27)          # --ink（浅色主题）
TILE_WHITE = (250, 250, 250)  # --on-ink
FREE_GREEN = (74, 222, 128)   # --free-on-ink
HAIRLINE = (250, 250, 250, 26)  # 圆角款的一线浅描边，防止深色壁纸上糊掉

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, '..', 'web', 'icons')

SUPERSAMPLE = 4  # 每像素 4x4 子采样 -> 16 级灰度，足够消除锯齿


def rounded_rect(u, v, x0, y0, x1, y1, r):
    """点 (u, v) 是否落在圆角矩形内。"""
    if u < x0 or u > x1 or v < y0 or v > y1:
        return False
    rad = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    if rad <= 0:
        return True
    cx = min(max(u, x0 + rad), x1 - rad)
    cy = min(max(v, y0 + rad), y1 - rad)
    if u == cx or v == cy:
        return True
    return (u - cx) ** 2 + (v - cy) ** 2 <= rad * rad


def glyph_cells(glyph_side):
    """2x2 教室格，归一化到整个画布。返回 [(x0, y0, x1, y1, color), ...]。

    第三格（右上）是绿的：图形在说"这间空着"。
    """
    left = (1 - glyph_side) / 2
    gap = glyph_side * 0.085
    cell = (glyph_side - gap) / 2
    radius = cell * 0.30

    cells = []
    for row in range(2):
        for col in range(2):
            x0 = left + col * (cell + gap)
            y0 = left + row * (cell + gap)
            color = FREE_GREEN if (row == 0 and col == 1) else TILE_WHITE
            cells.append((x0, y0, x0 + cell, y0 + cell, radius, color))
    return cells


def sample_color(u, v, style):
    """单个子采样点的颜色，返回 RGBA。"""
    if style == 'maskable':
        # 满幅底色：交给启动器去裁切，内容留在安全圈内
        base = (INK[0], INK[1], INK[2], 255)
        cells = glyph_cells(0.56)
        border = False
    elif style == 'ios':
        # iOS 自己会切圆角，所以给满幅方图，不能自带透明角
        base = (INK[0], INK[1], INK[2], 255)
        cells = glyph_cells(0.62)
        border = False
    elif style == 'rounded':
        if not rounded_rect(u, v, 0.0, 0.0, 1.0, 1.0, 0.22):
            return (0, 0, 0, 0)
        base = (INK[0], INK[1], INK[2], 255)
        cells = glyph_cells(0.66)
        border = True
    else:
        raise ValueError(style)

    for (x0, y0, x1, y1, r, color) in cells:
        if rounded_rect(u, v, x0, y0, x1, y1, r):
            return (color[0], color[1], color[2], 255)

    if border:
        # 距边缘 4% 以内的窄带
        edge = 0.035
        inner = rounded_rect(u, v, edge, edge, 1 - edge, 1 - edge, 0.22 - edge / 2)
        outer = rounded_rect(u, v, 0.0, 0.0, 1.0, 1.0, 0.22)
        if outer and not inner:
            return HAIRLINE

    return base


def render(size, style):
    """返回 RGBA 像素行列表。"""
    step = 1.0 / (size * SUPERSAMPLE)
    offset = step / 2
    rows = []

    for py in range(size):
        row = bytearray()
        for px in range(size):
            acc_r = acc_g = acc_b = acc_a = 0
            for sy in range(SUPERSAMPLE):
                v = (py * SUPERSAMPLE + sy) * step + offset
                for sx in range(SUPERSAMPLE):
                    u = (px * SUPERSAMPLE + sx) * step + offset
                    r, g, b, a = sample_color(u, v, style)
                    # 先乘 alpha 再平均，否则透明像素的黑会污染边缘
                    acc_r += r * a
                    acc_g += g * a
                    acc_b += b * a
                    acc_a += a
            n = SUPERSAMPLE * SUPERSAMPLE
            a = acc_a / n
            if a < 0.5:
                row += bytes((0, 0, 0, 0))
            else:
                row += bytes((
                    round(acc_r / acc_a),
                    round(acc_g / acc_a),
                    round(acc_b / acc_a),
                    round(a),
                ))
        rows.append(row)
    return rows


def write_png(path, size, rows):
    raw = b''.join(b'\x00' + bytes(row) for row in rows)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as fh:
        fh.write(png)
    return len(png)


TARGETS = [
    ('icon-192.png', 192, 'rounded'),
    ('icon-512.png', 512, 'rounded'),
    ('icon-maskable-192.png', 192, 'maskable'),
    ('icon-maskable-512.png', 512, 'maskable'),
    ('apple-touch-icon.png', 180, 'ios'),
    ('favicon-32.png', 32, 'rounded'),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, size, style in TARGETS:
        path = os.path.join(OUT_DIR, name)
        written = write_png(path, size, render(size, style))
        print('%-24s %4dx%-4d %-9s %6d bytes' % (name, size, size, style, written))


if __name__ == '__main__':
    main()
