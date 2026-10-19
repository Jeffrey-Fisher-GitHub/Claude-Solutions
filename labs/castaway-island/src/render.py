"""
Castaway Island — renderer.

Draws the closing 15 seconds of every simulated day (golden hour -> sunset ->
nightfall at the beach camp) and pipes the frames to ffmpeg.

    python3 src/render.py --days 1-30 --out videos/month-01.mp4
    python3 src/render.py --timelapse --out videos/two-years-timelapse.mp4
    python3 src/render.py --still 365 0.45 --out docs/day365.png

Everything is drawn procedurally with Pillow + NumPy; there are no image assets.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 854, 480
HZ = 220                      # horizon line
FPS = 12
SECONDS = 15
NF = FPS * SECONDS            # frames per day

FONT_DIR = Path("/usr/share/fonts/opentype/inter")


@lru_cache(None)
def font(name: str, size: int):
    return ImageFont.truetype(str(FONT_DIR / f"{name}.otf"), size)


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def keyframes(keys, t):
    """keys: list of (t, np.array). Linear interpolation."""
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return lerp(v0, v1, (t - t0) / (t1 - t0))
    return keys[-1][1]


A = np.array
SKY_TOP = [(0.0, A([96, 150, 205.])), (0.22, A([74, 104, 170.])), (0.42, A([38, 52, 118.])),
           (0.62, A([16, 22, 64.])), (0.82, A([7, 10, 32.])), (1.0, A([4, 6, 20.]))]
SKY_HZ = [(0.0, A([255, 206, 130.])), (0.22, A([255, 138, 76.])), (0.42, A([206, 92, 96.])),
          (0.62, A([92, 58, 102.])), (0.82, A([30, 28, 62.])), (1.0, A([12, 15, 34.]))]
TINT = [(0.0, A([1.0, .88, .74])), (0.22, A([.86, .62, .52])), (0.42, A([.48, .40, .55])),
        (0.62, A([.22, .21, .36])), (0.82, A([.11, .12, .24])), (1.0, A([.075, .085, .18]))]

# ------------------------------------------------------------------ geometry
MOUNTAIN = [(372, HZ + 6), (430, 186), (480, 150), (520, 118), (560, 88), (588, 70), (612, 60),
            (634, 66), (668, 84), (712, 108), (770, 128), (820, 142), (854, 150), (854, HZ + 40)]
HILLS = [(352, 334), (380, 290), (410, 258), (452, 236), (510, 220), (570, 212), (640, 206),
         (720, 200), (790, 194), (854, 188), (854, 334)]
SAND = [(0, 384), (90, 378), (200, 362), (290, 344), (360, 326), (430, 314), (520, 312),
        (640, 312), (854, 308), (854, H), (0, H)]
RIVER = [(546, 142), (538, 170), (522, 196), (500, 222), (478, 248), (462, 272), (450, 294),
         (436, 312), (422, 320)]
CAMPFIRE = (470, 392)
SIGNAL = (248, 372)
SUN_X = 150


def shore_y(x):
    pts = SAND[:8]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


# ------------------------------------------------------------------ static assets
class Static:
    def __init__(self):
        rng = np.random.default_rng(7)
        # stars
        stars = np.zeros((HZ, W), np.float32)
        n = 520
        ys = rng.integers(0, HZ - 6, n)
        xs = rng.integers(0, W, n)
        b = rng.random(n) ** 3 * 230 + 25
        stars[ys, xs] = b
        self.stars = stars * (np.linspace(1, 0.25, HZ)[:, None])
        # glow kernels
        yy, xx = np.mgrid[-60:61, -60:61]
        r = np.sqrt(xx ** 2 + yy ** 2)
        self.glow60 = np.clip(1 - r / 60, 0, 1) ** 2.2
        yy, xx = np.mgrid[-24:25, -24:25]
        r = np.sqrt(xx ** 2 + yy ** 2)
        self.glow24 = np.clip(1 - r / 24, 0, 1) ** 2
        yy, xx = np.mgrid[-90:91, -90:91]
        r = np.sqrt(xx ** 2 + yy ** 2)
        self.sunglow = np.clip(1 - r / 90, 0, 1) ** 2.5
        self.rows = (np.linspace(0, 1, HZ)[:, None] ** 1.6).astype(np.float32)
        self.srows = np.linspace(0, 1, H - HZ, dtype=np.float32)[:, None]
        # sea glitter pattern
        g = rng.random((H - HZ, 80)) ** 12
        self.glitter = g.astype(np.float32)
        xs_ = np.abs(np.linspace(-1, 1, 80, dtype=np.float32))
        ys_ = np.linspace(0, 1, H - HZ, dtype=np.float32)[:, None]
        self.glitter_fade = ((1 - xs_ ** 1.5)[None, :] * (1 - ys_) ** 1.5)[..., None].astype(np.float32)
        # trees (fixed layout, removed nearest-camp-first as timber is felled)
        rr = random.Random(11)
        trees = []
        for _ in range(170):
            x = rr.uniform(372, 852)
            top = hills_top(x)
            y = rr.uniform(top + 6, 312)
            trees.append((x, y, rr.uniform(9, 17), rr.random()))
        self.trees = sorted(trees, key=lambda t: t[1])
        cx, cy = 600, 300
        self.fell_order = sorted(range(len(trees)), key=lambda i: (trees[i][0] - cx) ** 2 + ((trees[i][1] - cy) * 2.2) ** 2)
        palms = []
        for i in range(16):
            x = 352 + i * 31 + rr.uniform(-8, 8)
            palms.append((x, shore_y(x) + rr.uniform(2, 14), rr.uniform(34, 52), rr.uniform(-0.35, 0.35)))
        for x in (24, 58, 312, 840):
            palms.append((x, shore_y(x) + 8, rr.uniform(30, 44), rr.uniform(-0.3, 0.3)))
        self.palms = palms
        self.mtn_canopy = []
        for _ in range(420):
            x = rr.uniform(380, 854)
            ytop = mountain_y(x)
            if ytop is None:
                continue
            y = rr.uniform(ytop + 14, HZ + 12)
            self.mtn_canopy.append((x, y, rr.uniform(4, 9), rr.random()))
        self.map_base = build_map_base()


def hills_top(x):
    for (x0, y0), (x1, y1) in zip(HILLS, HILLS[1:]):
        if x0 <= x <= x1 and x1 != x0:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return 200


def mountain_y(x):
    for (x0, y0), (x1, y1) in zip(MOUNTAIN, MOUNTAIN[1:]):
        if x0 <= x <= x1 and x1 != x0:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


# ------------------------------------------------------------------ island map
MAP_W, MAP_H = 168, 120
MAP_FEATURES = {          # map-pixel locations
    "camp": (66, 102), "summit": (92, 44), "taro": (56, 92), "breadfruit": (124, 62),
    "bananas": (98, 66), "coast": (84, 60), "cave": (86, 72), "clay": (76, 88),
    "springs": (98, 22), "wreck": (40, 116), "river": (80, 80),
}


def island_outline(scale=1.0):
    pts = []
    cx, cy = 84, 62
    for i in range(72):
        a = i / 72 * 2 * math.pi
        rx, ry = 74, 49
        n = 1 + 0.07 * math.sin(3 * a + 1) + 0.05 * math.sin(7 * a + 2) + 0.03 * math.sin(13 * a)
        if 1.3 < a < 2.1:              # south bay (lagoon)
            n -= 0.07 * math.sin((a - 1.3) / 0.8 * math.pi)
        pts.append((cx + math.cos(a) * rx * n * scale, cy + math.sin(a) * ry * n * scale))
    return pts


def build_map_base():
    S = 3
    im = Image.new("RGBA", (MAP_W * S, MAP_H * S), (18, 52, 74, 235))
    d = ImageDraw.Draw(im)
    sc = lambda pts: [(x * S, y * S) for x, y in pts]
    reef = island_outline(1.12)
    d.line(sc(reef + [reef[0]]), fill=(120, 200, 210, 120), width=S)
    d.polygon(sc(island_outline()), fill=(214, 196, 150, 255))
    d.polygon(sc(island_outline(0.93)), fill=(58, 120, 70, 255))
    cx, cy = MAP_FEATURES["summit"]
    for k, col in ((34, (70, 128, 74)), (24, (86, 128, 80)), (15, (104, 124, 86)), (7, (128, 122, 104))):
        d.ellipse([(cx - k * 1.3) * S, (cy - k) * S, (cx + k * 1.3) * S, (cy + k) * S], fill=col + (255,))
    d.line(sc([(92, 46), (88, 60), (84, 72), (78, 86), (72, 96), (68, 104)]), fill=(110, 190, 230, 255), width=2 * S)
    return im.resize((MAP_W, MAP_H), Image.LANCZOS)


def draw_map(day, st: Static):
    im = st.map_base.copy()
    S = 3
    over = Image.new("RGBA", (MAP_W * S, MAP_H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    found = set(day["found"])
    pr = day["projects"]
    cx, cy = MAP_FEATURES["camp"]
    felled = day["wood"]["felled_total"]
    rclear = 4 + math.sqrt(felled) * 0.9
    d.ellipse([(cx - rclear * 1.3) * S, (cy - rclear - 3) * S, (cx + rclear * 1.3) * S, (cy + rclear - 6) * S], fill=(150, 170, 90, 200))
    n_g = sum(1 for k in pr if k.startswith("garden") and pr[k]["done"])
    for i in range(n_g):
        gx, gy = cx + 6 + (i % 3) * 4, cy - 10 - (i // 3) * 4
        d.rectangle([gx * S, gy * S, (gx + 3) * S, (gy + 2) * S], fill=(110, 190, 70, 255))
    if "summit" in found:
        d.line([(cx * S, cy * S), (78 * S, 80 * S), (88 * S, 60 * S), (92 * S, 46 * S)], fill=(250, 240, 210, 170), width=S)
    if "coast" in found:
        d.line([(x * S, y * S) for x, y in island_outline(0.985)] + [(island_outline(0.985)[0][0] * S, island_outline(0.985)[0][1] * S)], fill=(250, 240, 210, 110), width=S)
    for k in ("taro", "breadfruit", "bananas", "cave", "clay", "springs"):
        if k in found:
            x, y = MAP_FEATURES[k]
            d.ellipse([(x - 1.6) * S, (y - 1.6) * S, (x + 1.6) * S, (y + 1.6) * S], fill=(255, 220, 90, 255))
    x, y = MAP_FEATURES["summit"]
    if pr.get("peak_beacon", {}).get("done"):
        d.polygon([((x) * S, (y - 4) * S), ((x - 3) * S, (y + 1) * S), ((x + 3) * S, (y + 1) * S)], fill=(255, 120, 40, 255))
    wx, wy = MAP_FEATURES["wreck"]
    if not day["wreck_on_reef"]:
        wx, wy = wx - 6, wy + 2
    d.line([((wx - 3) * S, wy * S), ((wx + 3) * S, wy * S)], fill=(220, 220, 225, 255), width=2 * S)
    d.ellipse([(cx - 2.4) * S, (cy - 2.4) * S, (cx + 2.4) * S, (cy + 2.4) * S], fill=(255, 90, 60, 255), outline=(255, 255, 255, 255), width=S)
    if day["canoe_out"]:
        d.ellipse([(46 - 1.5) * S, (104 - 1.5) * S, (46 + 1.5) * S, (104 + 1.5) * S], fill=(250, 250, 250, 255))
    # fog of war
    fog = Image.new("L", (MAP_W * S, MAP_H * S), 170)
    fd = ImageDraw.Draw(fog)
    reveal = [(cx, cy - 8, 26)]
    if "summit" in found:
        reveal.append((92, 50, 40))
    for k in found:
        if k in MAP_FEATURES:
            x, y = MAP_FEATURES[k]
            reveal.append((x, y, 16))
    if "coast" in found:
        fog = Image.new("L", fog.size, 0)
        fd = ImageDraw.Draw(fog)
    else:
        for x, y, r in reveal:
            fd.ellipse([(x - r * 1.3) * S, (y - r) * S, (x + r * 1.3) * S, (y + r) * S], fill=0)
        fog = fog.filter(ImageFilter.GaussianBlur(10))
    over = over.resize((MAP_W, MAP_H), Image.LANCZOS)
    im.alpha_composite(over)
    fog_small = fog.resize((MAP_W, MAP_H), Image.LANCZOS)
    dark = Image.new("RGBA", (MAP_W, MAP_H), (10, 22, 34, 255))
    dark.putalpha(fog_small)
    im.alpha_composite(dark)
    dd = ImageDraw.Draw(im)
    dd.text((6, MAP_H - 24), "THE ISLAND", font=font("Inter-SemiBold", 9), fill=(235, 240, 245, 230))
    dd.text((6, MAP_H - 13), "1,200 acres", font=font("Inter-Regular", 8), fill=(200, 215, 225, 210))
    dd.line([(MAP_W - 36, MAP_H - 8), (MAP_W - 11, MAP_H - 8)], fill=(235, 240, 245, 230), width=1)
    dd.text((MAP_W - 38, MAP_H - 19), "500 m", font=font("Inter-Regular", 8), fill=(235, 240, 245, 230))
    mask = Image.new("L", (MAP_W, MAP_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, MAP_W - 1, MAP_H - 1], 8, fill=255)
    a = np.minimum(np.asarray(im.getchannel("A")), np.asarray(mask))
    im.putalpha(Image.fromarray(a))
    return im


# ------------------------------------------------------------------ drawing helpers (2x supersampled)
SS = 2


def P(pts):
    return [(x * SS, y * SS) for x, y in pts]


def palm(d, x, y, h, lean, col_trunk=(118, 92, 64), col_leaf=(44, 110, 52), sway=0.0):
    pts = []
    tx, ty = x, y
    for i in range(6):
        f = i / 5
        pts.append((x + lean * h * f * f + sway * f * f * 6, y - h * f))
    d.line(P(pts), fill=col_trunk, width=int(3.2 * SS))
    tx, ty = pts[-1]
    for k in range(7):
        a = -math.pi / 2 + (k - 3) * 0.55 + sway * 0.2
        L = h * 0.48
        ex, ey = tx + math.cos(a) * L * 1.15, ty + math.sin(a) * L * 0.55 + L * 0.42 * abs(math.cos(a))
        mx, my = (tx + ex) / 2, (ty + ey) / 2 - 5
        d.polygon(P([(tx, ty), (mx, my - 2), (ex, ey), (mx, my + 3)]), fill=col_leaf)
    d.ellipse(P([(tx - 3, ty - 1), (tx + 3, ty + 4)]), fill=(96, 76, 40))


def broadleaf(d, x, y, r, shade):
    g = int(70 + shade * 40)
    d.line(P([(x, y), (x, y - r * 0.9)]), fill=(80, 60, 40), width=int(2 * SS))
    for dx, dy, k, c in ((-0.5, -1.2, 0.75, -14), (0.5, -1.25, 0.8, -6), (0, -1.75, 0.85, 8)):
        d.ellipse(P([(x + dx * r - k * r, y + dy * r - k * r * 0.85), (x + dx * r + k * r, y + dy * r + k * r * 0.85)]),
                  fill=(36 + c // 2, g + c, 48 + c // 2))


def hut(d, x, base, w, h, p, cond, roof=(196, 164, 92), wall=(150, 112, 70), door_glow=False):
    if p <= 0:
        return
    posts = [x - w / 2 + 3, x - w / 6, x + w / 6, x + w / 2 - 3]
    ph = h * 0.55
    n_posts = max(1, min(4, int(p / 0.25 + 1)))
    collapsed = cond < 0.55 and p >= 1
    if collapsed:
        d.polygon(P([(x - w / 2, base), (x + w / 2, base), (x + w / 2 - 6, base - 9), (x - w / 2 + 10, base - 14)]), fill=(120, 96, 60))
        d.polygon(P([(x - w / 2 - 4, base - 10), (x + w / 3, base - 26), (x + w / 2 + 6, base - 8)]), fill=tuple(int(c * .8) for c in roof))
        for i in range(5):
            xx = x - w / 2 + i * w / 4.5
            d.line(P([(xx, base), (xx + 6, base - 12 - (i % 2) * 6)]), fill=(90, 70, 50), width=SS * 2)
        return
    for px in posts[:n_posts]:
        d.line(P([(px, base), (px, base - ph)]), fill=(100, 74, 46), width=int(2.5 * SS))
    if p >= 0.35:
        d.line(P([(x - w / 2, base - ph), (x + w / 2, base - ph)]), fill=(100, 74, 46), width=int(2 * SS))
    if p >= 0.55:
        wf = min(1, (p - 0.55) / 0.3)
        d.rectangle(P([(x - w / 2 + 2, base - ph * wf), (x + w / 2 - 2, base)]), fill=wall)
        for i in range(int(w / 5)):
            xx = x - w / 2 + 3 + i * 5
            d.line(P([(xx, base - ph * wf), (xx, base)]), fill=tuple(c - 18 for c in wall), width=1)
        if wf >= 1:
            dc = (255, 196, 110) if door_glow else (60, 40, 26)
            d.rectangle(P([(x - 5, base - ph * 0.72), (x + 5, base)]), fill=dc)
    if p >= 0.8:
        rf = min(1, (p - 0.8) / 0.2)
        ridge = base - ph - (h - ph) * rf
        d.polygon(P([(x - w / 2 - 6, base - ph + 2), (x, ridge), (x + w / 2 + 6, base - ph + 2)]), fill=roof)
        for i in range(1, 5):
            yy = base - ph + 2 - (base - ph + 2 - ridge) * i / 5
            half = (w / 2 + 6) * (1 - i / 5)
            d.line(P([(x - half, yy), (x + half, yy)]), fill=tuple(int(c * 0.82) for c in roof), width=1)
        if cond < 0.85:   # patched / damaged
            d.polygon(P([(x + 2, ridge + 6), (x + w / 4, base - ph - 2), (x + 4, base - ph)]), fill=(90, 70, 40))
    else:
        if p >= 0.6:
            d.line(P([(x - w / 2, base - ph), (x, base - h), (x + w / 2, base - ph)]), fill=(100, 74, 46), width=SS * 2)


# ------------------------------------------------------------------ day layer
class DayLayers:
    pass


def build_day(day, meta, st: Static, prev_events=None):
    rng = random.Random(day["day"] * 31 + 5)
    pr = day["projects"]
    prog = lambda k: pr.get(k, {}).get("p", 0.0)
    cond = lambda k: pr.get(k, {}).get("c", 1.0)
    weather = day["weather"]
    lay = DayLayers()

    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # mountain
    d.polygon(P(MOUNTAIN), fill=(76, 104, 84))
    d.polygon(P([(560, 88), (588, 70), (612, 60), (634, 66), (668, 84), (640, 92), (612, 80), (590, 92)]), fill=(118, 116, 104))
    for x, y, r, s in st.mtn_canopy:
        g = int(84 + s * 30)
        d.ellipse(P([(x - r, y - r * 0.7), (x + r, y + r * 0.7)]), fill=(46, g, 58))
    # waterfall
    d.line(P([(548, 128), (546, 146)]), fill=(210, 232, 240), width=SS * 3)
    # hills
    d.polygon(P(HILLS), fill=(62, 118, 60))
    # river on hills
    d.line(P(RIVER), fill=(96, 168, 196), width=SS * 4, joint="curve")
    # gardens on the slope
    felled = day["wood"]["felled_total"]
    n_felled_draw = int(min(len(st.trees) * 0.55, felled * 0.42))
    felled_set = set(st.fell_order[:n_felled_draw])
    garden_keys = [f"garden{i}" for i in range(1, 7)]
    garden_slots = [(650, 262), (712, 258), (774, 254), (680, 238), (742, 234), (804, 230)]
    garden_rects = []
    for k, (gx, gy) in zip(garden_keys, garden_slots):
        p = prog(k)
        if p <= 0:
            continue
        w = 54 * min(1, p * 1.4)
        d.polygon(P([(gx - w / 2, gy + 10), (gx + w / 2, gy + 10), (gx + w / 2 - 3, gy), (gx - w / 2 + 3, gy)]), fill=(122, 92, 58))
        d.line(P([(gx - w / 2, gy + 10), (gx + w / 2, gy + 10)]), fill=(150, 130, 100), width=SS * 2)
        garden_rects.append((gx - 34, gy - 8, gx + 34, gy + 48))
        done = pr[k]["done"]
        if done:
            age = day["day"] - done
            m = min(1.0, age / 110)
            for row in range(3):
                for i in range(9):
                    xx = gx - 22 + i * 5.5
                    yy = gy + 2.5 + row * 3
                    rr = 0.8 + 1.8 * m
                    d.ellipse(P([(xx - rr, yy - rr), (xx + rr, yy + rr * 0.6)]), fill=(70 + int(40 * m), 150 + int(30 * m), 60))
    if prog("nursery") > 0:
        for i in range(int(16 * prog("nursery"))):
            xx = 640 + i * 4.5
            d.line(P([(xx, 232), (xx, 228)]), fill=(120, 200, 90), width=SS)
    # jungle trees on the hills
    planted = day["wood"]["planted_total"]
    n_sap = int(min(len(felled_set), planted / 8))
    saps = list(felled_set)[:n_sap]
    for i, (x, y, r, s) in enumerate(st.trees):
        in_garden = any(a <= x <= c and b <= y <= e for a, b, c, e in garden_rects)
        if i in felled_set or in_garden:
            if i in saps and not in_garden:
                d.line(P([(x, y), (x, y - 6)]), fill=(80, 70, 40), width=SS)
                d.ellipse(P([(x - 3, y - 9), (x + 3, y - 4)]), fill=(90, 170, 80))
            elif i in felled_set and not in_garden:
                d.ellipse(P([(x - 2, y - 1), (x + 2, y + 1)]), fill=(130, 100, 60))   # stump
            continue
        broadleaf(d, x, y, r, s)
    # kiln
    if prog("kiln") > 0.2:
        kx, ky = 410, 300
        d.chord(P([(kx - 13, ky - 22), (kx + 13, ky + 4)]), 180, 360, fill=(168, 104, 70))
        d.rectangle(P([(kx - 4, ky - 7), (kx + 4, ky)]), fill=(40, 20, 12))
    # bridge
    if prog("bridge") > 0.2:
        bx, by = 466, 266
        w = 30 * min(1, prog("bridge") * 1.2)
        d.arc(P([(bx - w / 2, by - 6), (bx + w / 2, by + 8)]), 180, 360, fill=(140, 100, 60), width=SS * 3)
        d.line(P([(bx - w / 2, by + 1), (bx - w / 2, by - 6), (bx + w / 2, by - 6), (bx + w / 2, by + 1)]), fill=(120, 86, 52), width=SS)
    # aqueduct
    if prog("aqueduct") > 0:
        pts = [(506, 226), (512, 252), (516, 280), (518, 304), (520, 318)]
        n = max(2, int(len(pts) * min(1, prog("aqueduct") * 1.1)))
        d.line(P(pts[:n]), fill=(190, 186, 120), width=SS * 2)
        for x, y in pts[1:n]:
            d.line(P([(x - 3, y + 4), (x, y), (x + 3, y + 4)]), fill=(120, 96, 60), width=SS)
        if prog("aqueduct") >= 1:
            d.rounded_rectangle(P([(512, 318), (530, 336)]), 3 * SS, fill=(130, 98, 62))
            d.line(P([(512, 324), (530, 324)]), fill=(90, 66, 40), width=SS)
    # sand
    d.polygon(P(SAND), fill=(222, 198, 146))
    d.line(P(SAND[:8]), fill=(240, 226, 186), width=SS * 3)
    # palms along the back of the beach
    for x, y, h, lean in st.palms:
        palm(d, x, y, h, lean)
    # salt pans
    if prog("salt") > 0:
        for i in range(int(4 * min(1, prog("salt") * 1.3))):
            x0 = 40 + i * 30
            d.polygon(P([(x0, 410), (x0 + 24, 410), (x0 + 22, 420), (x0 - 2, 420)]), fill=(206, 212, 214))
            d.line(P([(x0, 410), (x0 + 24, 410)]), fill=(150, 130, 100), width=SS)
    # back row
    hut(d, 478, 318, 34, 34, prog("hut4"), cond("hut4"))
    if prog("longhouse") > 0:
        hut(d, 604, 320, 132, 56, prog("longhouse"), cond("longhouse"), roof=(186, 150, 84), wall=(140, 104, 64))
        if prog("longhouse") >= 1 and cond("longhouse") > 0.55:
            for xx in (562, 646):
                d.rectangle(P([(xx - 4, 320 - 22), (xx + 4, 320 - 14)]), fill=(70, 50, 30))
    hut(d, 718, 318, 40, 38, prog("infirmary"), cond("infirmary"), wall=(196, 180, 150))
    if prog("infirmary") >= 1:
        d.rectangle(P([(735, 286), (746, 293)]), fill=(240, 240, 236))
        d.line(P([(735, 286), (735, 300)]), fill=(90, 70, 50), width=SS)
    if prog("school") > 0.2:
        sx, sb = 792, 318
        d.line(P([(sx - 22, sb), (sx - 22, sb - 24)]), fill=(100, 74, 46), width=SS * 2)
        d.line(P([(sx + 22, sb), (sx + 22, sb - 24)]), fill=(100, 74, 46), width=SS * 2)
        if prog("school") > 0.7:
            d.polygon(P([(sx - 28, sb - 22), (sx, sb - 34), (sx + 28, sb - 22)]), fill=(190, 160, 90))
            d.rectangle(P([(sx - 12, sb - 18), (sx + 12, sb - 8)]), fill=(46, 62, 52))
    if prog("latrine") > 0.3:
        d.rectangle(P([(838, 300), (852, 318)]), fill=(150, 120, 74))
    # ELT mast
    if prog("elt") > 0.3:
        d.line(P([(562, 352), (562, 296)]), fill=(150, 150, 156), width=SS)
        d.line(P([(562, 298), (548, 352)]), fill=(120, 120, 126), width=1)
        d.rectangle(P([(558, 342), (566, 352)]), fill=(232, 112, 40) if day["day"] < 34 else (110, 80, 60))
    # front row
    hut(d, 382, 356, 36, 34, prog("smokehouse"), cond("smokehouse"), roof=(120, 100, 70), wall=(110, 84, 58))
    if prog("leanto") > 0:
        lx, lb = 540, 358
        p = prog("leanto")
        d.line(P([(lx + 24, lb), (lx + 24, lb - 30 * min(1, p * 2))]), fill=(100, 74, 46), width=SS * 3)
        d.line(P([(lx - 24, lb), (lx - 24, lb - 30 * min(1, p * 2))]), fill=(100, 74, 46), width=SS * 3)
        if p > 0.4:
            c = cond("leanto")
            if c > 0.55:
                d.polygon(P([(lx - 34, lb - 1), (lx - 28, lb - 34), (lx + 30, lb - 34), (lx + 36, lb - 1)]), fill=(146, 160, 76))
                d.polygon(P([(lx - 28, lb - 34), (lx + 30, lb - 34), (lx + 26, lb - 40), (lx - 24, lb - 40)]), fill=(120, 140, 62))
                if day["day"] >= 3:
                    d.polygon(P([(lx - 6, lb - 34), (lx + 22, lb - 34), (lx + 20, lb - 24), (lx - 4, lb - 22)]), fill=(232, 110, 40))
            else:
                d.polygon(P([(lx - 34, lb), (lx + 30, lb - 12), (lx + 36, lb)]), fill=(120, 130, 70))
    hut(d, 632, 358, 44, 40, prog("hut1"), cond("hut1"))
    hut(d, 704, 360, 44, 40, prog("hut2"), cond("hut2"))
    hut(d, 780, 362, 44, 40, prog("hut3"), cond("hut3"))
    # chapel / bell
    if prog("chapel") > 0.3:
        cx_, cb = 840, 394
        d.line(P([(cx_ - 8, cb), (cx_ - 8, cb - 26), (cx_ + 8, cb - 26), (cx_ + 8, cb)]), fill=(110, 80, 50), width=SS * 2)
        d.chord(P([(cx_ - 5, cb - 24), (cx_ + 5, cb - 12)]), 180, 360, fill=(186, 140, 60))
        for i in range(5):
            d.ellipse(P([(cx_ - 14 + i * 7, cb + 2), (cx_ - 10 + i * 7, cb + 6)]), fill=(230, 90, 120) if i % 2 else (250, 210, 80))
    # SOS on the beach (stones and driftwood, seen at a low angle)
    p = prog("sos")
    if p > 0:
        letters = "SOS"[:max(1, min(3, int(p * 3 + 0.2)))]
        f_ = font("InterDisplay-Black", 64 * SS)
        tw_ = int(f_.getlength("SOS")) + 20
        timg = Image.new("L", (tw_, 90 * SS), 0)
        ImageDraw.Draw(timg).text((10, 0), letters, font=f_, fill=255)
        timg = timg.resize((int(tw_ * 1.05), 26 * SS), Image.LANCZOS)
        stone = Image.new("RGBA", timg.size, (96, 92, 86, 255))
        im.paste(stone, (602 * SS, 402 * SS), timg)
    # campfire ring
    fx, fy = CAMPFIRE
    for i in range(10):
        a = i / 10 * 2 * math.pi
        d.ellipse(P([(fx + math.cos(a) * 11 - 2.5, fy + math.sin(a) * 4 - 2), (fx + math.cos(a) * 11 + 2.5, fy + math.sin(a) * 4 + 2)]), fill=(120, 116, 110))
    if day["day"] > 120:   # log benches
        d.line(P([(fx - 48, fy - 12), (fx - 26, fy - 16)]), fill=(110, 80, 50), width=SS * 4)
        d.line(P([(fx + 26, fy - 16), (fx + 48, fy - 12)]), fill=(110, 80, 50), width=SS * 4)
        d.line(P([(fx - 30, fy + 16), (fx + 30, fy + 16)]), fill=(110, 80, 50), width=SS * 4)
    # signal fire pyre
    sx, sy = SIGNAL
    for i in range(5):
        d.line(P([(sx - 14 + i * 2, sy), (sx + 2 + i * 2, sy - 22)]), fill=(110, 84, 50), width=SS * 2)
        d.line(P([(sx + 14 - i * 2, sy), (sx - 2 - i * 2, sy - 22)]), fill=(100, 76, 46), width=SS * 2)
    # life rafts & debris in the early days
    if day["day"] <= 60:
        d.ellipse(P([(292, 370), (330, 382)]), fill=(240, 120, 40))
        d.ellipse(P([(298, 372), (324, 380)]), fill=(200, 90, 30))
    if day["day"] <= 24:
        r2 = random.Random(3)
        for _ in range(max(0, 10 - day["day"] // 3)):
            x = r2.uniform(80, 420); y = shore_y(x) + r2.uniform(6, 30)
            c = r2.choice([(70, 80, 110), (150, 60, 50), (40, 40, 44), (180, 170, 150)])
            d.rectangle(P([(x, y), (x + 9, y + 6)]), fill=c)
    # canoe on the sand
    if prog("canoe") > 0:
        p = prog("canoe")
        cxn, cyn = 336, 368
        if day.get("canoe_out") == "canoe" or p < 1:
            pass
        L = 44 * min(1, 0.3 + p)
        d.chord(P([(cxn - L / 2, cyn - 8), (cxn + L / 2, cyn + 4)]), 0, 180, fill=(96, 62, 36) if p >= 1 else (150, 112, 70))
    # crate (radio drop)
    if day["day"] >= 729:
        d.rectangle(P([(500, 372), (516, 384)]), fill=(70, 96, 70))
        d.ellipse(P([(504, 376), (512, 380)]), fill=(210, 220, 200))
    # wedding / feast torches
    torches = []
    if day["flags"].get("wedding") or day["day"] in (226, 365, 730) or day["flags"].get("birthday"):
        for i in range(7):
            tx = 360 + i * 30
            ty = shore_y(tx) + 18
            d.line(P([(tx, ty), (tx, ty - 18)]), fill=(90, 66, 40), width=SS * 2)
            torches.append((tx, ty - 20))
    if day["flags"].get("wedding"):
        d.arc(P([(330, 342), (380, 392)]), 180, 360, fill=(250, 160, 190), width=SS * 3)

    lay.land_big = im
    # --- sea objects drawn on a separate layer (above sea, below land not needed)
    sea = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sea)
    # wreck
    if day["wreck_on_reef"]:
        wx, wy = 104, 240
        sd.polygon(P([(wx - 46, wy), (wx + 30, wy - 2), (wx + 34, wy - 12), (wx - 44, wy - 13)]), fill=(196, 198, 204))
        for i in range(8):
            sd.ellipse(P([(wx - 38 + i * 8, wy - 10), (wx - 35 + i * 8, wy - 7)]), fill=(70, 80, 96))
        sd.polygon(P([(wx + 26, wy - 10), (wx + 36, wy - 42), (wx + 46, wy - 42), (wx + 42, wy - 10)]), fill=(210, 212, 218))
        sd.polygon(P([(wx + 34, wy - 34), (wx + 46, wy - 34), (wx + 45, wy - 28), (wx + 33, wy - 28)]), fill=(200, 60, 50))
    else:
        wx, wy = 70, 242
        sd.polygon(P([(wx, wy), (wx + 6, wy - 18), (wx + 14, wy - 17), (wx + 12, wy)]), fill=(150, 152, 158))
        sd.polygon(P([(wx + 5, wy - 14), (wx + 13, wy - 13), (wx + 13, wy - 10), (wx + 5, wy - 10)]), fill=(150, 60, 50))
    # weir
    p = prog("weir")
    if p > 0:
        c = cond("weir")
        pts = [(130, 368), (190, 312), (250, 352)]
        n_st = int(30 * min(1, p * 1.05) * (1 if c > 0.3 else 0.25))
        for i in range(n_st):
            f = i / 29
            if f < 0.5:
                x = lerp(pts[0][0], pts[1][0], f * 2); y = lerp(pts[0][1], pts[1][1], f * 2)
            else:
                x = lerp(pts[1][0], pts[2][0], f * 2 - 1); y = lerp(pts[1][1], pts[2][1], f * 2 - 1)
            sd.line(P([(x, y), (x, y - 7)]), fill=(96, 70, 44), width=SS * 2)
    # dock
    p = prog("dock")
    if p > 0:
        L = min(1, p * 1.05)
        x0, y0, x1, y1 = 336, 334, 288, 282
        ex, ey = lerp(x0, x1, L), lerp(y0, y1, L)
        sd.polygon(P([(x0 - 6, y0), (x0 + 6, y0), (ex + 4, ey), (ex - 4, ey)]), fill=(146, 112, 72))
        for i in range(int(8 * L)):
            f = i / 7
            px, py = lerp(x0, x1, f), lerp(y0, y1, f)
            sd.line(P([(px - 5, py + 1), (px - 5, py + 7)]), fill=(80, 60, 40), width=SS * 2)
    # outrigger moored at the dock (or on the sand while being built)
    p = prog("outrigger")
    if p > 0:
        if p >= 1:
            ox, oy = 266, 288
        else:
            ox, oy = 420, 352
        L = 56 * min(1, 0.25 + p)
        sd.chord(P([(ox - L / 2, oy - 6), (ox + L / 2, oy + 6)]), 0, 180, fill=(110, 70, 40))
        if p > 0.5:
            sd.line(P([(ox - L / 3, oy + 8), (ox + L / 3, oy + 8)]), fill=(140, 100, 60), width=SS * 2)
            sd.line(P([(ox - 8, oy), (ox - 8, oy + 8)]), fill=(120, 90, 50), width=SS)
            sd.line(P([(ox + 8, oy), (ox + 8, oy + 8)]), fill=(120, 90, 50), width=SS)
        if p > 0.8:
            sd.line(P([(ox, oy), (ox, oy - 42)]), fill=(120, 90, 50), width=SS * 2)
            sd.polygon(P([(ox + 1, oy - 40), (ox + 18, oy - 8), (ox + 1, oy - 6)]), fill=(226, 214, 186))
    # rescue ship
    if day["flags"].get("rescue"):
        sx_, sy_ = 230, 224
        sd.polygon(P([(sx_ - 40, sy_), (sx_ + 40, sy_), (sx_ + 34, sy_ + 6), (sx_ - 36, sy_ + 6)]), fill=(60, 64, 72))
        sd.rectangle(P([(sx_ - 14, sy_ - 10), (sx_ + 10, sy_)]), fill=(220, 220, 224))
        sd.line(P([(sx_, sy_ - 10), (sx_, sy_ - 22)]), fill=(200, 200, 204), width=SS)
    lay.sea_big = sea

    land = Image.alpha_composite(sea, im).resize((W, H), Image.LANCZOS)
    arr = np.asarray(land).astype(np.float32)
    alpha = arr[..., 3:4] / 255.0
    lay.landA = arr[..., :3] * alpha
    lay.inv = (1.0 - alpha).astype(np.float32)

    # --- emissive layers (glow at night)
    fire = np.zeros((H, W, 3), np.float32)
    lamps = np.zeros((H, W, 3), np.float32)

    def add(arr_, x, y, kern, col, k=1.0):
        r = kern.shape[0] // 2
        x, y = int(x), int(y)
        y0, y1, x0, x1 = max(0, y - r), min(H, y + r + 1), max(0, x - r), min(W, x + r + 1)
        if y0 >= y1 or x0 >= x1:
            return
        kk = kern[y0 - (y - r):y1 - (y - r), x0 - (x - r):x1 - (x - r)]
        arr_[y0:y1, x0:x1] += kk[..., None] * (np.array(col, np.float32) * k)

    stormy = weather in ("storm", "cyclone")
    if weather != "cyclone":
        add(fire, fx, fy - 6, st.glow60, (255, 150, 60), 1.0 if not stormy else 0.4)
        if day["day"] >= 1 and not stormy:
            add(fire, sx, sy - 14, st.glow60, (255, 140, 50), 0.9)
    lay.fires = []
    if weather != "cyclone":
        lay.fires.append((fx, fy, 1.0))
        if not stormy:
            lay.fires.append((sx, sy - 6, 1.35))
    for (k, x, y) in (("hut1", 632, 344), ("hut2", 704, 346), ("hut3", 780, 348), ("hut4", 478, 306),
                      ("infirmary", 718, 304), ("longhouse", 604, 302), ("smokehouse", 382, 344)):
        if prog(k) >= 1 and cond(k) > 0.55:
            add(lamps, x, y, st.glow24, (255, 170, 90), 0.85 if k != "longhouse" else 1.4)
    if prog("kiln") >= 1:
        add(lamps, 410, 296, st.glow24, (255, 110, 40), 0.9)
    if day["beacon_lit"] and weather != "cyclone":
        add(fire, 612, 56, st.glow24, (255, 150, 60), 1.4)
        lay.fires.append((612, 58, 0.35))
    for tx, ty in torches:
        add(fire, tx, ty, st.glow24, (255, 160, 70), 0.9)
        lay.fires.append((tx, ty + 2, 0.3))
    if day["flags"].get("rescue"):
        for x, y in ((200, 222), (262, 222), (230, 212)):
            add(lamps, x, y, st.glow24, (250, 250, 230), 1.2)
    if day["flags"].get("ship") == "missed":
        add(lamps, 40, HZ - 1, st.glow24, (255, 240, 200), 0.6)
    lay.fire_em = fire
    lay.lamp_em = lamps

    # clouds
    cover = {"clear": 0.12, "cloudy": 0.5, "rain": 0.8, "storm": 0.95, "cyclone": 1.0}[weather]
    cl = Image.new("L", (W // 2, HZ // 2), 0)
    cd = ImageDraw.Draw(cl)
    n = int(6 + cover * 34)
    for _ in range(n):
        x = rng.uniform(-40, W // 2 + 20)
        y = rng.uniform(4, HZ // 2 - 18) if rng.random() < 0.7 else rng.uniform(HZ // 2 - 30, HZ // 2 - 6)
        w = rng.uniform(30, 120)
        h = rng.uniform(5, 16)
        cd.ellipse([x, y, x + w, y + h], fill=int(150 + 105 * rng.random()))
    cl = cl.filter(ImageFilter.GaussianBlur(5)).resize((W, HZ), Image.BILINEAR)
    cm = np.asarray(cl).astype(np.float32) / 255.0
    if cover > 0.7:
        cm = np.clip(cm + (cover - 0.55), 0, 1)
    lay.cloud = np.clip(cm * (0.5 + cover), 0, 0.97)[..., None].astype(np.float32)
    lay.cloud_inv = 1 - lay.cloud
    lay.cover = cover
    return lay


# ------------------------------------------------------------------ HUD
TASK_LABEL = {"fish": "fish", "forage": "forage", "build": "build", "wood": "fell trees",
              "garden": "garden", "cook": "cook", "fire": "fire watch", "water": "water",
              "scout": "explore", "nurse": "nurse", "rest": "rest", "sick": "sick", "injured": "hurt",
              "shelter": "shelter"}


def wrap(text, f, width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.getlength(t) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_hud(day, meta, st):
    hud = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(hud)
    panel = (8, 14, 24, 150)
    white = (244, 246, 248, 255)
    soft = (200, 212, 222, 255)
    accent = (255, 196, 110, 255)
    dt = date.fromisoformat(day["date"])
    # top-left
    d.rounded_rectangle([10, 10, 262, 84], 10, fill=panel)
    d.text((22, 13), f"DAY {day['day']}", font=font("InterDisplay-Bold", 30), fill=white)
    tw = font("InterDisplay-Bold", 30).getlength(f"DAY {day['day']}")
    d.text((26 + tw, 29), "of 730", font=font("Inter-Medium", 12), fill=soft)
    d.text((22, 50), f"{dt.strftime('%a %-d %b %Y')}  ·  {day['season']} season", font=font("Inter-Medium", 12), fill=white)
    m = day["moon"]
    illum = (1 - math.cos(2 * math.pi * m)) / 2
    wx = {"clear": "Clear", "cloudy": "Cloudy", "rain": "Rain", "storm": "Squall", "cyclone": "CYCLONE"}[day["weather"]]
    d.text((22, 66), f"{wx}, wind {day['wind_kmh']} km/h  ·  moon {int(illum * 100)}%", font=font("Inter-Regular", 11),
           fill=(255, 140, 120, 255) if day["weather"] == "cyclone" else soft)
    # stats panel
    f = day["food"]
    pr = day["projects"]
    built = sum(1 for k in pr if pr[k]["done"])
    total = len(meta["projects"])
    tasks = {}
    for p in day["people"]:
        tasks[p["task"]] = tasks.get(p["task"], 0) + 1
    d.rounded_rectangle([10, 90, 262, 188], 10, fill=panel)
    fs = font("Inter-Regular", 10.5)
    fb = font("Inter-SemiBold", 10.5)
    y = 96
    rows = [
        ("Food store", (f"{f['store_days']:.1f} days" if f['store_days'] < 60 else "60+ days") + f"   ·   ate {f['eaten_pct']}% of need"),
        ("Today", f"{f['fish_kg']:.0f} kg fish · {f['coconuts']} coconuts · {f['fruit_kg'] + f['roots_kg'] + f['garden_kg']:.0f} kg fruit/veg"),
        ("Timber", f"{day['wood']['logs']} logs · {day['wood']['felled_total']} trees cut · {day['wood']['planted_total']} planted"),
        ("Built", f"{built} of {total} projects"),
    ]
    for label, val in rows:
        d.text((20, y), label, font=fb, fill=accent)
        d.text((86, y), val, font=fs, fill=white)
        y += 15
    cur = [(k, v) for k, v in pr.items() if not v["done"] and v["p"] > 0]
    if cur:
        k, v = max(cur, key=lambda kv: kv[1]["p"])
        name = meta["projects"][k]["name"].split(" (")[0]
        txt = f"{name} {int(v['p'] * 100)}%"
        while fs.getlength(txt) > 160:
            name = name[:-2]
            txt = f"{name}… {int(v['p'] * 100)}%"
        d.text((20, y), "Building", font=fb, fill=accent)
        d.text((86, y), txt, font=fs, fill=white)
        bx = 86 + fs.getlength(txt) + 6
        if bx < 250:
            d.rounded_rectangle([bx, y + 4, 252, y + 9], 2, fill=(255, 255, 255, 50))
            d.rounded_rectangle([bx, y + 4, bx + (252 - bx) * v["p"], y + 9], 2, fill=accent)
    y += 15
    order = ["fish", "forage", "garden", "build", "wood", "scout", "cook", "fire", "water", "nurse", "rest", "shelter", "sick", "injured"]
    parts = [f"{tasks[k]} {TASK_LABEL[k]}" for k in order if k in tasks]
    crew = " · ".join(parts)
    crew = "Crew: " + crew
    fsz = 9.5
    while font("Inter-Regular", fsz).getlength(crew) > 236 and fsz > 7.5:
        fsz -= 0.5
    while font("Inter-Regular", fsz).getlength(crew) > 236:
        crew = crew.rsplit(" · ", 1)[0]
    lines = (crew, fsz)
    # map
    mp = draw_map(day, st)
    hud.alpha_composite(mp, (W - MAP_W - 10, 10))
    # bottom panel
    d.rectangle([0, 432, W, H], fill=(6, 10, 18, 190))
    head = day["headline"]
    hf = font("Inter-SemiBold", 14)
    hl = wrap(head, hf, 595)
    if len(hl) > 2:
        hf = font("Inter-SemiBold", 12.5)
        hl = wrap(head, hf, 595)[:2]
    yy = 438 if len(hl) > 1 else 446
    for ln in hl:
        d.text((14, yy), ln, font=hf, fill=white)
        yy += 17
    # roster
    ppl = {p["id"]: p for p in day["people"]}
    for i, pm in enumerate(meta["people"]):
        p = ppl[pm["id"]]
        cx = 632 + (i % 6) * 37
        cy = 446 + (i // 6) * 20
        hcol = (110, 220, 120) if p["health"] >= 75 else ((240, 200, 80) if p["health"] >= 55 else (240, 90, 80))
        base = tuple(pm["color"])
        if p["status"] != "ok":
            base = tuple(int(c * 0.45 + 60) for c in base)
        d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=base + (255,), outline=hcol + (255,), width=2)
        ini = pm["name"][0]
        tc = (20, 20, 24, 255) if sum(base) > 450 else white
        d.text((cx, cy), ini, font=font("Inter-Bold", 9), fill=tc, anchor="mm")
        if p["status"] != "ok":
            d.ellipse([cx + 3, cy - 10, cx + 11, cy - 2], fill=(220, 60, 60, 255))
            d.text((cx + 7, cy - 6), "+", font=font("Inter-Bold", 8), fill=white, anchor="mm")
        d.text((cx + 12, cy + 1), pm["name"].split()[0][:3], font=font("Inter-Regular", 7.5), fill=soft, anchor="lm")
    # timeline
    d.rectangle([0, H - 3, W, H], fill=(255, 255, 255, 40))
    d.rectangle([0, H - 3, int(W * day["day"] / 730), H], fill=accent)
    for k in (139, 365, 466):
        x = int(W * k / 730)
        d.rectangle([x - 1, H - 6, x + 1, H], fill=(255, 255, 255, 140))
    # crew line in the stats panel
    for i, ln in enumerate(lines[:2]):
        d.text((20, 96 + 15 * 5 + i * 0 - 0), "", font=fs)
    arr = np.asarray(hud).astype(np.float32)
    return Image.fromarray(arr[..., :3].astype(np.uint8)), hud.getchannel("A"), lines


# ------------------------------------------------------------------ people
SKIN = [(198, 134, 98), (232, 190, 160), (160, 104, 70), (120, 80, 56), (236, 200, 170), (180, 120, 90),
        (226, 180, 150), (214, 160, 120), (238, 204, 176), (230, 186, 156), (110, 72, 50), (224, 182, 146)]
HAIR = [(60, 50, 50), (20, 16, 14), (40, 30, 24), (20, 16, 14), (220, 220, 220), (20, 16, 14),
        (60, 40, 30), (120, 70, 40), (140, 100, 50), (90, 60, 40), (20, 16, 14), (20, 16, 14)]
TASK_START = {
    "fish": [(150, 352), (210, 346), (300, 338), (92, 372), (240, 352)],
    "forage": [(850, 340), (845, 360), (360, 336)],
    "wood": [(800, 312), (760, 318), (842, 322)],
    "garden": [(700, 286), (760, 282)],
    "scout": [(450, 300), (470, 290)],
    "water": [(424, 330)],
    "cook": [(486, 386)],
    "fire": [(262, 378)],
    "nurse": [(560, 366)],
    "rest": [(500, 400), (440, 402), (520, 380)],
}


def seats(n=12):
    out = []
    for i in range(n):
        a = math.pi * 0.05 + i / n * 2 * math.pi
        out.append((CAMPFIRE[0] + math.cos(a) * 46, CAMPFIRE[1] + math.sin(a) * 15))
    return out


def plan_people(day, rng):
    """Return per-person (start, end, depart, arrive, sitting, visible)."""
    plans = []
    st_seats = seats()
    counters = {}
    weather = day["weather"]
    pr = day["projects"]
    active_build = [k for k, v in pr.items() if not v["done"] and v["p"] > 0]
    build_spot = {"hut1": (632, 360), "hut2": (704, 362), "hut3": (780, 364), "hut4": (478, 320),
                  "longhouse": (604, 322), "infirmary": (718, 320), "smokehouse": (382, 358), "dock": (330, 340),
                  "outrigger": (420, 356), "canoe": (336, 370), "school": (792, 320), "kiln": (410, 302),
                  "bridge": (466, 270), "aqueduct": (514, 300), "sos": (660, 416), "lookout": (600, 300),
                  "peak_beacon": (560, 300), "leanto": (540, 360), "salt": (100, 410), "chapel": (840, 396)}
    for i, p in enumerate(day["people"]):
        task = p["task"]
        if weather == "cyclone":
            plans.append(None)
            continue
        if p["status"] != "ok":
            if p["status"] == "injured" and rng.random() < 0.6:
                seat = st_seats[i]
                plans.append(dict(start=seat, end=seat, t0=0, t1=0, sit=True, lie=False))
            else:
                plans.append(dict(start=(548 + (i % 3) * 10, 352), end=(548 + (i % 3) * 10, 352), t0=0, t1=0, sit=False, lie=True))
            continue
        if weather == "storm":
            plans.append(None if rng.random() < 0.8 else dict(start=(632, 360), end=(632, 360), t0=0, t1=0, sit=False, lie=False))
            continue
        if task == "build" and active_build:
            k = active_build[i % len(active_build)]
            sx, sy = build_spot.get(k, (600, 340))
            start = (sx + rng.uniform(-16, 16), sy + rng.uniform(-2, 6))
        else:
            opts = TASK_START.get(task, TASK_START["rest"])
            c = counters.get(task, 0)
            counters[task] = c + 1
            bx, by = opts[c % len(opts)]
            start = (bx + rng.uniform(-10, 10), by + rng.uniform(-4, 4))
        end = st_seats[i]
        if task == "fire" and day["day"] >= 42 and day["day"] % 2 == 0:
            end = (SIGNAL[0] + 16, SIGNAL[1] + 4)
        if day["flags"].get("rescue"):
            end = (190 + i * 14 + rng.uniform(-4, 4), shore_y(190 + i * 14) + 6)
        t0 = rng.uniform(0.0, 0.35)
        dist = math.dist(start, end)
        t1 = t0 + dist / 420 + 0.05
        plans.append(dict(start=start, end=end, t0=t0, t1=min(0.92, t1), sit=not day["flags"].get("rescue"), lie=False))
    return plans


def draw_person(d, x, y, col, skin, hair, t, walking, sitting, lying, tint, warm, scale, waving=False):
    def c(rgb):
        return (int(min(255, rgb[0] * tint[0] + warm * 150)), int(min(255, rgb[1] * tint[1] + warm * 80)),
                int(min(255, rgb[2] * tint[2] + warm * 30)))
    s = scale * SS
    X, Y = x * SS, y * SS
    if lying:
        d.rounded_rectangle([X - 10 * s, Y - 4 * s, X + 6 * s, Y], radius=2 * s, fill=c(col))
        d.ellipse([X + 5 * s, Y - 5 * s, X + 10 * s, Y], fill=c(skin))
        return
    if sitting:
        d.line([(X - 2 * s, Y - 2 * s), (X + 4 * s, Y - 2 * s), (X + 5 * s, Y + 2 * s)], fill=c((70, 60, 70)), width=int(2.2 * s))
        d.rounded_rectangle([X - 3.5 * s, Y - 13 * s, X + 2.5 * s, Y - 2 * s], radius=2 * s, fill=c(col))
        d.ellipse([X - 3.4 * s, Y - 19.5 * s, X + 2.4 * s, Y - 13.5 * s], fill=c(skin))
        d.chord([X - 3.6 * s, Y - 20 * s, X + 2.6 * s, Y - 15 * s], 180, 360, fill=c(hair))
        return
    ph = t * 9.0
    sw = math.sin(ph) * 2.6 if walking else 0
    d.line([(X - 1 * s, Y - 9 * s), (X - 1 * s + sw * s, Y)], fill=c((70, 60, 70)), width=int(2.2 * s))
    d.line([(X + 1 * s, Y - 9 * s), (X + 1 * s - sw * s, Y)], fill=c((70, 60, 70)), width=int(2.2 * s))
    d.rounded_rectangle([X - 3.2 * s, Y - 19 * s, X + 3.2 * s, Y - 8.5 * s], radius=2 * s, fill=c(col))
    if waving:
        wv = math.sin(t * 14) * 3
        d.line([(X + 3 * s, Y - 17 * s), (X + (6 + wv) * s, Y - 25 * s)], fill=c(skin), width=int(1.8 * s))
    d.ellipse([X - 2.9 * s, Y - 25.5 * s, X + 2.9 * s, Y - 19.5 * s], fill=c(skin))
    d.chord([X - 3.1 * s, Y - 26 * s, X + 3.1 * s, Y - 21 * s], 180, 360, fill=c(hair))


# ------------------------------------------------------------------ frame
def add_kernel(img, x, y, kern, col, ymax=H):
    r = kern.shape[0] // 2
    y0, y1, x0, x1 = max(0, y - r), min(ymax, y + r + 1), max(0, x - r), min(W, x + r + 1)
    if y0 >= y1 or x0 >= x1:
        return
    kk = kern[y0 - (y - r):y1 - (y - r), x0 - (x - r):x1 - (x - r)]
    img[y0:y1, x0:x1] += kk[..., None] * col


def f32(a):
    return np.asarray(a, np.float32)


class Renderer:
    def __init__(self):
        self.st = Static()
        data = json.loads((ROOT / "data" / "days.json").read_text())
        self.meta = data["meta"]
        self.days = data["days"]

    def prepare(self, n):
        day = self.days[n - 1]
        self.day = day
        self.lay = build_day(day, self.meta, self.st)
        self.hud_rgb, self.hud_a, self.crew_lines = build_hud(day, self.meta, self.st)
        rng = random.Random(n * 977)
        self.plans = plan_people(day, rng)
        self.rng = random.Random(n * 13)
        self.drops = [(self.rng.uniform(0, W), self.rng.uniform(0, H), self.rng.uniform(0.7, 1.3)) for _ in range(260)]
        self.lightning = set()
        if day["weather"] in ("storm", "cyclone"):
            for _ in range(4 if day["weather"] == "storm" else 9):
                f0 = self.rng.randint(5, NF - 6)
                self.lightning.update({f0, f0 + 1})

    def frame(self, f, t=None):
        day, lay, st = self.day, self.lay, self.st
        if t is None:
            t = f / (NF - 1)
        weather = day["weather"]
        cover = lay.cover
        top = f32(keyframes(SKY_TOP, t))
        hzc = f32(keyframes(SKY_HZ, t))
        tint = f32(keyframes(TINT, t))
        grey = f32([120, 128, 140.])
        dull = cover * 0.85
        top = top * (1 - dull) + grey * dull * (top.mean() / 120)
        hzc = hzc * (1 - dull) + grey * dull * (hzc.mean() / 130)
        moon = day["moon"]
        illum = (1 - math.cos(2 * math.pi * moon)) / 2
        E = moon * 360
        s_arc = E - 30 * t
        moon_up = 2 < s_arc < 178
        night = smooth(0.45, 0.95, t)
        if moon_up:
            tint = tint + np.array([0.05, 0.06, 0.10]) * illum * night * (1 - cover)
        tint = tint * (1 - 0.35 * cover)
        if weather == "cyclone":
            tint = tint * 0.55
        flash = f in self.lightning
        if flash:
            tint = f32([0.62, 0.64, 0.74])
            top = f32([120, 122, 150.])
            hzc = f32([150, 150, 172.])
        rows = self.st.rows
        sky = (top[None, :] * (1 - rows) + hzc[None, :] * rows).astype(np.float32)
        img = np.empty((H, W, 3), np.float32)
        img[:HZ] = sky[:, None, :]
        # sun
        sun_y = HZ - 34 + t * 160
        sun_vis = 1 - cover * 0.8
        if sun_y < HZ + 12:
            add_kernel(img, SUN_X, int(sun_y), st.sunglow,
                       np.array([255, 150, 70.], np.float32) * 0.75 * sun_vis * (1 - smooth(0.1, 0.35, t)), HZ)
            if sun_y < HZ:
                yy, xx = np.mgrid[max(0, int(sun_y) - 14):min(HZ, int(sun_y) + 15), SUN_X - 14:SUN_X + 15]
                mask = ((xx - SUN_X) ** 2 + (yy - sun_y) ** 2) < 13 ** 2
                col = np.array([255, 236, 190.]) * (1 - 0.35 * t / 0.2) if t < 0.2 else np.array([255, 170, 100.])
                sub = img[yy.min():yy.max() + 1, xx.min():xx.max() + 1]
                sub[mask] = sub[mask] * (1 - sun_vis) + col * sun_vis
        # stars
        if night > 0:
            img[:HZ] += st.stars[..., None] * np.float32(night * (1 - min(1, cover * 1.1)))
        # moon
        if moon_up:
            mx = int(SUN_X - 30 + s_arc / 180 * (W - SUN_X + 40))
            my = int(HZ - 8 - math.sin(math.radians(s_arc)) * (HZ - 30))
            if 8 <= my < HZ - 6 and 8 <= mx < W - 8:
                yy, xx = np.mgrid[my - 8:my + 9, mx - 8:mx + 9]
                d2 = (xx - mx) ** 2 + (yy - my) ** 2
                disk = d2 < 7.5 ** 2
                # lit side faces the sun (west = left) when waxing
                k = math.cos(2 * math.pi * moon)          # +1 new, -1 full
                term = mx + (xx - mx) * 0
                lit = ((xx - mx) < (-k * np.sqrt(np.maximum(0, 56 - (yy - my) ** 2)))) if moon < 0.5 else ((xx - mx) > (k * np.sqrt(np.maximum(0, 56 - (yy - my) ** 2))))
                sub = img[my - 8:my + 9, mx - 8:mx + 9]
                mv = (0.35 + 0.65 * smooth(0.2, 0.7, t)) * (1 - min(1, cover))
                sub[disk & lit] = sub[disk & lit] * (1 - mv) + np.array([240, 238, 222.]) * mv
                sub[disk & ~lit] = sub[disk & ~lit] * (1 - mv * 0.12) + np.array([60, 66, 90.]) * mv * 0.12
                add_kernel(img, mx, my, st.glow24, np.array([120, 130, 160.], np.float32) * 0.25 * mv, HZ)
        # clouds
        cloud_col = hzc * 0.55 + top * 0.25 + 30 * (1 - t)
        if t < 0.45:
            cloud_col = cloud_col * (1 - cover * 0.5) + np.array([255, 150, 110.]) * (0.45 - t) * (1 - cover)
        img[:HZ] = img[:HZ] * lay.cloud_inv + lay.cloud * f32(cloud_col)
        # sea
        srows = self.st.srows
        deep = np.array([30, 100, 120.]) * tint
        refl = hzc * 0.7
        sea = refl[None, :] * (1 - srows) * 0.75 + deep[None, :] * (0.4 + srows * 0.6)
        img[HZ:] = sea[:, None, :].astype(np.float32)
        if sun_y < HZ + 10:
            sk = max(0, 1 - t / 0.3) * max(0.0, 1 - cover * 1.15)
            gl = np.roll(st.glitter, f % (H - HZ), axis=0)[:, :, None]
            img[HZ:, SUN_X - 40:SUN_X + 40] += gl * self.st.glitter_fade * f32([255, 200, 140.]) * np.float32(1.1 * sk)
            img[HZ:HZ + 4, SUN_X - 30:SUN_X + 30] += np.array([255, 170, 90.]) * 0.5 * sk
        if moon_up and night > 0.2:
            mx = int(SUN_X - 30 + s_arc / 180 * (W - SUN_X + 40))
            if 20 <= mx < W - 20:
                gl = np.roll(st.glitter, (f * 2) % (H - HZ), axis=0)[:, :40, None]
                img[HZ:, mx - 20:mx + 20] += gl * np.array([200, 210, 230.]) * illum * night * (1 - cover)
        # land
        img *= lay.inv
        img += lay.landA * tint
        dark = 1 - min(1.0, float(tint.mean()) / 0.8)
        dark = max(0.0, dark) ** 1.3
        flick = 0.82 + 0.18 * math.sin(f * 1.7) * math.sin(f * 0.63 + 1)
        img += lay.fire_em * np.float32((0.25 + 0.95 * dark) * flick)
        if dark > 0.02:
            img += lay.lamp_em * np.float32(dark * 1.1)
        if flash:
            img *= 1.0
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        self.dynamic(im, f, t, tint, dark)
        im.paste(self.hud_rgb, (0, 0), self.hud_a)
        self.overlay_text(im, t)
        return im

    def dynamic(self, im, f, t, tint, dark):
        day = self.day
        weather = day["weather"]
        top_y = 120
        layer = Image.new("RGBA", (W * SS, (H - top_y) * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        def Q(x, y):
            return (x * SS, (y - top_y) * SS)

        tcol = lambda rgb, a=255: (int(rgb[0] * tint[0]), int(rgb[1] * tint[1]), int(rgb[2] * tint[2]), a)
        # surf on the reef and shore
        amp = {"clear": 1, "cloudy": 1.2, "rain": 1.6, "storm": 2.6, "cyclone": 4.2}[weather]
        for k in range(3):
            pts = []
            for x in range(0, 380, 8):
                y = 242 + math.sin(x * 0.05 + f * 0.25 + k) * 1.4 * amp + k * 3 + (x / 380) ** 2 * 6
                pts.append(Q(x, y))
            d.line(pts, fill=tcol((240, 248, 250), int(150 / (k + 1))), width=SS * (2 if k == 0 else 1))
        ph = math.sin(f * 0.18) * 3 * amp
        shore = [Q(x, shore_y(x) - 2 + ph * 0.5) for x in range(0, 430, 10)]
        d.line(shore, fill=tcol((250, 252, 252), 140), width=SS * 2)
        if weather == "cyclone":
            for i in range(14):
                x = (i * 61 + f * 9) % 420
                y = 250 + (i % 5) * 20
                d.arc([Q(x - 20, y - 6)[0], Q(x - 20, y - 6)[1], Q(x + 20, y + 6)[0], Q(x + 20, y + 6)[1]], 180, 360, fill=tcol((240, 248, 250), 200), width=SS * 2)
        # waterfall foam
        for i in range(6):
            yy = 146 + ((f * 3 + i * 7) % 12)
            d.ellipse([Q(544 + (i % 3) * 2, yy)[0], Q(544, yy)[1], Q(550 + (i % 3), yy + 2)[0], Q(550, yy + 2)[1]], fill=tcol((240, 250, 255), 200))
        # smoke from smokehouse / kiln / fire
        pr = day["projects"]
        smokes = []
        if pr.get("smokehouse", {}).get("p", 0) >= 1:
            smokes.append((386, 322))
        if pr.get("kiln", {}).get("p", 0) >= 1:
            smokes.append((410, 280))
        if weather != "cyclone":
            smokes.append((CAMPFIRE[0], CAMPFIRE[1] - 12))
            if weather != "storm":
                smokes.append((SIGNAL[0], SIGNAL[1] - 30))
        drift = 0.6 if weather in ("clear", "cloudy") else 2.5
        for sx, sy in smokes:
            for j in range(6):
                age = ((f * 0.04 + j / 6) % 1.0)
                x = sx + age * 26 * drift + math.sin(age * 6 + j) * 3
                y = sy - age * 60
                r = 3 + age * 9
                a = int(110 * (1 - age))
                c = (150 + 40 * dark, 150 + 20 * dark, 150) if dark < 0.5 else (90, 86, 84)
                d.ellipse([Q(x - r, y - r)[0], Q(x - r, y - r)[1], Q(x + r, y + r)[0], Q(x + r, y + r)[1]], fill=tcol(c, a))
        # fire flames
        for fx, fy, scale in self.lay.fires:
            for j in range(4):
                h = (9 + 5 * math.sin(f * 1.3 + j * 2.1)) * scale
                w = 4 * scale
                xo = (j - 1.5) * 3 * scale
                d.polygon([Q(fx + xo - w, fy - 2), Q(fx + xo + math.sin(f * 0.9 + j) * 2, fy - 2 - h), Q(fx + xo + w, fy - 2)],
                          fill=(255, 140 + 40 * (j % 2), 40, 230))
            d.polygon([Q(fx - 2 * scale, fy - 2), Q(fx, fy - 7 * scale), Q(fx + 2 * scale, fy - 2)], fill=(255, 236, 160, 240))
        # people
        items = []
        for i, (pl, pm) in enumerate(zip(self.plans, self.meta["people"])):
            if pl is None:
                continue
            if t <= pl["t0"]:
                x, y = pl["start"]; walking = False
            elif t >= pl["t1"]:
                x, y = pl["end"]; walking = False
            else:
                u = (t - pl["t0"]) / max(1e-6, pl["t1"] - pl["t0"])
                u = u * u * (3 - 2 * u)
                x = lerp(pl["start"][0], pl["end"][0], u)
                y = lerp(pl["start"][1], pl["end"][1], u)
                walking = True
            sitting = pl["sit"] and t >= pl["t1"] and pl["t1"] > 0 and not walking
            if pl["t1"] == 0 and pl["sit"]:
                sitting = True
            items.append((y, i, x, walking, sitting, pl["lie"]))
        items.sort()
        rescue = day["flags"].get("rescue")
        for y, i, x, walking, sitting, lying in items:
            pm = self.meta["people"][i]
            dist = math.dist((x, y), CAMPFIRE)
            warm = dark * max(0, 1 - dist / 90) * 0.55 * (1 if weather != "storm" else 0.3)
            scale = 0.62 + (y - 280) / 160 * 0.3
            draw_person(d, x, y - top_y, pm["color"], SKIN[i], HAIR[i], f / FPS + i, walking, sitting, lying,
                        tint * 1.15 + 0.03, warm, scale, waving=bool(rescue) and not walking)
        # rescue launch with searchlight
        if rescue:
            u = min(1, t / 0.9)
            bx, by = lerp(230, 250, u), lerp(232, 330, u)
            d.polygon([Q(bx - 9, by), Q(bx + 9, by), Q(bx + 7, by + 4), Q(bx - 7, by + 4)], fill=(200, 200, 205, 255))
            if dark > 0.2:
                d.polygon([Q(bx, by - 2), Q(bx - 50, by + 70), Q(bx + 40, by + 74)], fill=(255, 255, 220, int(40 * dark)))
            # flares
            for j in range(2):
                ft = (t * 1.6 + j * 0.45) % 1.0
                fx, fy = 210 + j * 60, 200 - ft * 70
                d.ellipse([Q(fx - 3, fy - 3)[0], Q(fx - 3, fy - 3)[1], Q(fx + 3, fy + 3)[0], Q(fx + 3, fy + 3)[1]], fill=(255, 80, 60, int(255 * (1 - ft))))
        # missed ship lights blink
        if day["flags"].get("ship") == "missed" and t > 0.5:
            if (f // 6) % 2:
                d.ellipse([Q(38, 218)[0], Q(38, 218)[1], Q(42, 222)[0], Q(42, 222)[1]], fill=(255, 250, 220, 255))
        # radio crate blink
        if day["day"] >= 729 and (f // 4) % 2:
            d.ellipse([Q(512, 372)[0], Q(512, 372)[1], Q(516, 376)[0], Q(516, 376)[1]], fill=(80, 255, 120, 255))
        small = layer.reduce(SS)
        im.paste(small, (0, top_y), small)
        # rain (full frame, 1x)
        if weather in ("rain", "storm", "cyclone"):
            dr = ImageDraw.Draw(im, "RGBA")
            n = {"rain": 140, "storm": 220, "cyclone": 260}[weather]
            slant = {"rain": 3, "storm": 7, "cyclone": 14}[weather]
            ln = {"rain": 9, "storm": 12, "cyclone": 16}[weather]
            for x0, y0, sp in self.drops[:n]:
                y = (y0 + f * 26 * sp) % H
                x = (x0 + f * slant * sp * 1.5) % W
                dr.line([(x, y), (x + slant, y + ln)], fill=(200, 210, 230, 70), width=1)

    def overlay_text(self, im, t):
        d = ImageDraw.Draw(im, "RGBA")
        ss = self.day["sunset"]
        clock = ss - 0.15 + t * 2.0
        hh = int(clock)
        mm = int((clock - hh) * 60)
        txt = f"{hh:02d}:{mm:02d}"
        d.rounded_rectangle([392, 10, 462, 32], 10, fill=(8, 14, 24, 150))
        d.text((427, 21), txt, font=font("Inter-SemiBold", 13), fill=(244, 246, 248, 255), anchor="mm")
        if t < 0.04:
            pass
        # crew line (static but drawn here so it can sit inside the stats panel)
        txt, fsz = self.crew_lines
        d.text((20, 173), txt, font=font("Inter-Regular", fsz), fill=(200, 212, 222, 255))


# ------------------------------------------------------------------ encoding
def ffmpeg_proc(out, fps=FPS, crf=30):
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-tune", "animation",
           "-crf", str(crf), "-pix_fmt", "yuv420p", "-g", str(fps * 15), "-threads", "1",
           "-movflags", "+faststart", str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def render_days(r: Renderer, d0, d1, out):
    proc = ffmpeg_proc(out)
    for n in range(d0, d1 + 1):
        r.prepare(n)
        for f in range(NF):
            im = r.frame(f)
            if f < 4:      # brief fade-in from the previous night
                im = Image.blend(Image.new("RGB", (W, H)), im, (f + 1) / 5)
            proc.stdin.write(im.tobytes())
    proc.stdin.close()
    proc.wait()


def render_timelapse(r: Renderer, out, per_day=4, fps=24):
    proc = ffmpeg_proc(out, fps=fps, crf=28)
    for n in range(1, len(r.days) + 1):
        r.prepare(n)
        for j in range(per_day):
            f = int((0.40 + j * 0.02) * (NF - 1))
            proc.stdin.write(r.frame(f).tobytes())
    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", help="range like 1-30")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timelapse", action="store_true")
    ap.add_argument("--still", nargs=2, metavar=("DAY", "T"))
    a = ap.parse_args()
    r = Renderer()
    if a.still:
        r.prepare(int(a.still[0]))
        t = float(a.still[1])
        r.frame(int(t * (NF - 1)), t).save(a.out)
    elif a.timelapse:
        render_timelapse(r, Path(a.out))
    else:
        d0, d1 = map(int, a.days.split("-"))
        render_days(r, d0, d1, Path(a.out))
