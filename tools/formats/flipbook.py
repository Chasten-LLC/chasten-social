"""
Friday: "Hold the dots and slide". Ten frames of one drawn scene; holding
Instagram's dots and sliding plays them like a flipbook. The first is a
sunrise: night over layered hills, the sun coming up frame by frame, and the
verse arriving in the morning sky (Lamentations 3:22-23, "new every morning").
Everything is drawn in code, so frame ten is exactly frame one plus daylight.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import common as c

FRAMES = 10
SS = 2

# sky keyframes: (t, top, middle, horizon)
SKY = [
    (0.00, (13, 17, 44), (33, 33, 74), (64, 47, 92)),
    (0.30, (29, 39, 86), (104, 62, 120), (214, 110, 108)),
    (0.55, (64, 104, 170), (226, 136, 132), (252, 184, 110)),
    (0.78, (88, 140, 204), (236, 190, 168), (255, 220, 150)),
    (1.00, (84, 150, 216), (168, 206, 236), (250, 236, 206)),
]
# hill layers far to near: (base y, amplitude, night colour, dawn colour, day colour)
HILLS = [
    (860, 46, (44, 46, 86), (150, 104, 140), (156, 186, 204)),
    (930, 58, (34, 36, 70), (112, 80, 118), (122, 160, 160)),
    (1010, 64, (26, 28, 56), (82, 62, 96), (104, 142, 118)),
    (1100, 70, (19, 21, 42), (58, 46, 72), (84, 120, 90)),
    (1210, 60, (12, 14, 30), (38, 32, 50), (60, 94, 64)),
]


def _lerp_keys(keys, t):
    for (t0, *a), (t1, *b) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0)
            return [c.mix(x, y, u) for x, y in zip(a, b)]
    return list(keys[-1][1:])


def _ridge(rng_phases, base, amp, w):
    xs = np.linspace(0, 1, 361)
    y = base + sum(amp * a * np.sin(2 * math.pi * f * xs + p) for a, f, p in rng_phases)
    return [(x * w, yy) for x, yy in zip(xs, y)]


def _scene(t, rng_seed=5):
    w, h = c.W * SS, c.H * SS
    top, mid, hor = _lerp_keys(SKY, t)
    # sky: top to middle to horizon
    ys = np.linspace(0, 1, h)[:, None]
    def band(a, b, u):
        return np.array(a)[None, :] * (1 - u) + np.array(b)[None, :] * u
    sky = np.where(ys < 0.45, band(top, mid, (ys / 0.45)), band(mid, hor, np.clip((ys - 0.45) / 0.25, 0, 1)))
    img = np.repeat(sky[:, None, :], w, axis=1)

    # sun position and glow
    rise = 1 - (1 - t) ** 1.6
    sx, sy = 0.72 * w, (1000 - 380 * rise) * SS
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2) / SS
    glow_col = np.array(c.mix((255, 140, 80), (255, 236, 190), min(1, t * 1.3)), dtype=np.float32)
    glow = np.exp(-(dist / (240 + 180 * t)) ** 2) * (0.25 + 0.45 * min(1, t * 1.6) - 0.22 * max(0, t - 0.6))
    img = img * (1 - glow[..., None]) + glow_col[None, None, :] * glow[..., None]
    sun_r = 92 * SS
    disc = np.clip((sun_r - dist * SS) / (2.5 * SS), 0, 1)
    sun_col = np.array(c.mix((255, 128, 64), (255, 250, 232), min(1, t * 1.25)), dtype=np.float32)
    img = img * (1 - disc[..., None]) + sun_col[None, None, :] * disc[..., None]

    # stars fade as the sky lightens
    rng = np.random.default_rng(rng_seed)
    star_a = max(0.0, 1 - t * 2.4)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if star_a > 0:
        d = ImageDraw.Draw(im)
        for _ in range(140):
            x, y = rng.uniform(0, w), rng.uniform(0, 0.62 * h)
            r = rng.uniform(1.0, 2.6) * SS
            a = int(255 * star_a * rng.uniform(0.35, 1))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 250, 235, a))
    else:
        rng.uniform(0, 1, 140 * 3)

    # hills, far to near, each lit a little more as the sun climbs
    d = ImageDraw.Draw(im)
    prng = np.random.default_rng(rng_seed + 1)
    for i, (base, amp, night, dawn, day) in enumerate(HILLS):
        phases = [(1.0, prng.uniform(0.6, 1.4), prng.uniform(0, 6.3)), (0.5, prng.uniform(1.8, 3.2), prng.uniform(0, 6.3)),
                  (0.22, prng.uniform(4, 7), prng.uniform(0, 6.3))]
        pts = _ridge(phases, base * SS, amp * SS / 1.7, w)
        col = c.mix(night, dawn, min(1, t / 0.5)) if t < 0.5 else c.mix(dawn, day, (t - 0.5) / 0.5)
        d.polygon(pts + [(w, h), (0, h)], fill=col + (255,))
        if i == 0:  # a breath of mist under the farthest ridge at dawn
            mist = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mist).rectangle((0, (base + 40) * SS, w, (base + 120) * SS), fill=int(90 * math.sin(math.pi * min(1, t * 1.2))))
            mist = mist.filter(ImageFilter.GaussianBlur(40 * SS))
            layer = Image.new("RGBA", (w, h), c.mix((255, 220, 210), (255, 255, 255), t) + (0,))
            layer.putalpha(mist)
            im.alpha_composite(layer)
            d = ImageDraw.Draw(im)

    # birds once it is light
    if t >= 0.66:
        bx0 = (0.16 + (t - 0.66) * 0.9) * w
        for k, (dx, dy, s) in enumerate([(0, 0, 1.0), (70, 34, 0.8), (130, -10, 0.7)]):
            x, y, s = bx0 + dx * SS, (770 + dy) * SS, s * 26 * SS
            wing = [(x - s, y - s * 0.35), (x - s * 0.45, y - s * 0.55), (x, y)]
            wing2 = [(x, y), (x + s * 0.45, y - s * 0.55), (x + s, y - s * 0.35)]
            for wpts in (wing, wing2):
                d.line(wpts, fill=(40, 46, 60, 220), width=int(4 * SS), joint="curve")
    im = im.resize((c.W, c.H), Image.LANCZOS)
    im.alpha_composite(c.grain((c.W, c.H), 5.0, seed=rng_seed + 9))
    return im


def render_sunrise(out_dir, verse, ref, title="Good morning", cue="hold the dots and slide to watch the sun come up"):
    paths = []
    for k in range(FRAMES):
        t = k / (FRAMES - 1)
        im = _scene(t)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        title_a = max(0.0, min(1.0, (0.62 - t) / 0.12))
        verse_a = max(0.0, min(1.0, (t - 0.62) / 0.25))
        if title_a > 0:
            d.text((78, 210), title, font=c.font("serif-b", 104), fill=(255, 255, 255, int(255 * title_a)), anchor="ls")
            hf = c.font("hand-b", 60)
            words = c.wrap(hf, cue, 760)
            for i, line in enumerate(words):
                d.text((84, 304 + i * 66), line, font=hf, fill=c.with_alpha((255, 222, 160), title_a), anchor="ls")
        if verse_a > 0:
            size, lines = c.fit(verse, "serif-sb", c.W - 2 * 90, 440, 62, 40, leading=1.3)
            f = c.font("serif-sb", size)
            pitch = size * 1.3
            bottom = c.text_block(d, lines, f, c.W / 2, 84, pitch, (255, 255, 255, int(255 * verse_a)))
            c.draw_tracked(d, (c.W / 2, bottom + 54), ref.upper(), c.font("sans-sb", 30),
                           (255, 255, 255, int(235 * verse_a)), 3.0, anchor="ms")
        im.alpha_composite(c.shadow_layer(layer, 14, 0.8, (16, 22, 48)))
        im.alpha_composite(layer)
        if k < FRAMES - 1:
            ad = ImageDraw.Draw(im)
            for side in (-1, 1):
                x = 540 + side * 420
                c.arrow(ad, (x - side * 10, 1200), (x + side * 2, 1290), (255, 255, 255, 200), width=6, bend=0.3 * side, head=22)
        wm = c.wordmark("white", 170, 0.6)
        im.alpha_composite(wm, ((c.W - wm.width) // 2, c.H - 76 - wm.height))
        paths.append(c.save(im, os.path.join(out_dir, f"{k + 1}.jpg")))
    return paths
