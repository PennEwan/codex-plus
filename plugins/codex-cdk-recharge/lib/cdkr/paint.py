"""The look of the recharge card, borrowed from the Codex 小助手 quota card (desktop/ball_render.py).

Pure functions only (no Tk), so they are tested directly. Colors are (r, g, b) tuples;
Tk wants "#rrggbb" strings, see `hexc`.
"""
from __future__ import annotations

import math

# 小助手 ball_render.py: card size and ink.
CARD_W = 340
CARD_RADIUS = 30        # 小助手 uses 38 with a soft anti-aliased edge; a clipped Win32 region looks rounder a bit smaller
PAD_X, PAD_TOP, PAD_BOTTOM = 26, 22, 20
INK = (23, 25, 31)                  # #17191f
CARD_BG = (237, 243, 248)           # #edf3f8
PIN_BLUE = (90, 144, 214)           # #5a90d6
NOTE_BLUE = (47, 98, 168)
OK_GREEN = (47, 158, 107)
BAD_RED = (196, 64, 52)
STATUS_OK, STATUS_STALE = (99, 245, 140), (143, 144, 148)
CHIP_GREY = (120, 130, 145)

# Light-skin aurora palettes (小助手 PALETTES, from quota-float desktopPalette.ts).
PALETTES = {
    "healthy": {"cool": (185, 213, 238), "glow": (223, 244, 229), "warm": (199, 221, 242), "opacity": .42},
    "caution": {"cool": (183, 208, 236), "glow": (255, 240, 186), "warm": (244, 201, 121), "opacity": .5,
                "glow_fade": .58, "warm_at": (.12, .96), "warm_fade": .66, "lin_warm": (228, 231, 237),
                "lin_end": (241, 245, 248), "angle": 213},
    "critical": {"cool": (196, 206, 224), "glow": (255, 216, 168), "warm": (240, 114, 96), "opacity": .56,
                 "glow_fade": .60, "warm_at": (.11, .98), "warm_fade": .68, "lin_warm": (227, 228, 233),
                 "lin_end": (243, 245, 248), "angle": 213},
}


def mix(a, b, t: float) -> tuple:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hexc(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def unhex(value: str) -> tuple:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def tint(rgb, alpha: float, over=CARD_BG) -> tuple:
    """`rgb` at `alpha` opacity over the card background (Tk has no alpha)."""
    return mix(over, rgb, alpha)


def aurora_rows(level: str, width: int, height: int, inset: float = .39) -> list[list[str]]:
    """The card background as rows of "#rrggbb": a linear gradient with three radial glows on top,
    laid over #edf3f8 (小助手 ball_render.aurora, without Pillow)."""
    palette = PALETTES[level]
    cool, glow, warm = palette["cool"], palette["glow"], palette["warm"]
    lin_warm, lin_end = palette.get("lin_warm", warm), palette.get("lin_end", (255, 195, 124))
    angle = math.radians(palette.get("angle", 145))
    sa, ca = math.sin(angle), math.cos(angle)
    box_w, box_h = width * (1 + 2 * inset), height * (1 + 2 * inset)
    reach = math.hypot(box_w, box_h) / math.sqrt(2)
    length = abs(box_w * sa) + abs(box_h * ca)
    stops = ((0, cool), (.47, (199, 201, 209)), (.83, lin_warm), (1, lin_end))
    blobs = (((.52, .12), .22, .52, cool, .9),
             (palette.get("warm_at", (.82, .82)), .14, palette.get("warm_fade", .34), warm, .64),
             ((.28, .68), .18, palette.get("glow_fade", .43), glow, .78))
    blobs = [(cx * box_w, cy * box_h, solid, fade, tone, strength) for (cx, cy), solid, fade, tone, strength in blobs]
    opacity = palette["opacity"]
    rows = []
    for j in range(height):
        y = j + .5 + inset * height
        row = []
        for i in range(width):
            x = i + .5 + inset * width
            t = max(0.0, min(1.0, ((x - box_w / 2) * sa - (y - box_h / 2) * ca) / length + .5))
            for (s0, c0), (s1, c1) in zip(stops, stops[1:]):
                if t <= s1:
                    color = _mixf(c0, c1, (t - s0) / (s1 - s0))
                    break
            for bx, by, solid, fade, tone, strength in blobs:
                d = math.hypot(x - bx, y - by) / reach
                a = strength if d <= solid else strength * max(0.0, 1 - (d - solid) / (fade - solid))
                if a > 0:
                    color = _mixf(color, tone, a)
            row.append(hexc(_mixf(CARD_BG, color, opacity)))
        rows.append(row)
    return rows


def _mixf(a, b, t: float) -> tuple:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def round_rect_points(x0: float, y0: float, x1: float, y1: float, r: float, steps: int = 8) -> list[float]:
    """Flat [x, y, x, y, …] polygon of a rounded rectangle, for Canvas.create_polygon."""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r == 0:
        return [x0, y0, x1, y0, x1, y1, x0, y1]
    points: list[float] = []
    corners = ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180))
    for cx, cy, start in corners:
        for k in range(steps + 1):
            a = math.radians(start + 90 * k / steps)
            points += [cx + r * math.cos(a), cy + r * math.sin(a)]
    # snap the extreme points exactly onto the box so edges line up with neighbouring shapes
    return [min(max(v, lo), hi) for v, lo, hi in
            ((p, x0 if i % 2 == 0 else y0, x1 if i % 2 == 0 else y1) for i, p in enumerate(points))]
