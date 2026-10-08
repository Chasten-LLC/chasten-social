"""
Shared drawing for the 7 AM interactive formats and the reel.

Everything here is drawn in code so Scripture is set in real type, word for
word, never painted by an image model. Colours are the app's tokens
(design/tokens/tokens.json in chasten-bible-app); type is Literata for
Scripture and headlines, Caveat for the handwritten notes, Inter for labels.
"""

import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLS)
FONT_DIR = os.path.join(TOOLS, "assets", "fonts")
IMG_DIR = os.path.join(TOOLS, "assets", "img")
ART_DIR = os.path.join(TOOLS, "assets", "art")
BG_DIR = os.path.join(ROOT, "studio", "bg")

W, H = 1080, 1350          # Instagram portrait post
RW, RH = 1080, 1920        # Reel

# ---------------------------------------------------------------- colour
PAPER = (250, 246, 238)    # color.light.bg
SHEET = (253, 250, 243)    # color.light.sheet
INK = (43, 36, 28)         # color.light.ink
SUB = (143, 131, 113)      # color.light.sub
FAINT = (188, 176, 154)    # color.light.faint
GOLD = (198, 138, 46)      # color.light.accent
GOLD_DARK = (220, 168, 78)  # color.dark.accent
HEART = (190, 75, 51)      # color.light.heart

# The app's manuscript hues (color.light.cat*): rich, warm, never neon.
HUES = {
    "gold": (198, 138, 46),
    "clay": (176, 101, 65),
    "heart": (190, 75, 51),
    "plum": (138, 107, 166),
    "teal": (78, 141, 133),
    "blue": (91, 128, 172),
    "green": (122, 145, 80),
}

# Highlight washes (color.highlight.*.lightFill / dot)
WASH = {
    "amber": ((241, 223, 168), (223, 182, 92)),
    "apricot": ((247, 223, 194), (224, 164, 104)),
    "rose": ((242, 218, 210), (220, 163, 145)),
    "sky": ((214, 228, 234), (146, 183, 200)),
    "sage": ((222, 231, 200), (169, 189, 127)),
    "lavender": ((227, 220, 239), (175, 161, 210)),
    "blush": ((246, 217, 224), (223, 160, 180)),
    "teal": ((210, 230, 225), (133, 188, 175)),
}


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def with_alpha(rgb, a):
    return tuple(rgb[:3]) + (int(round(255 * a)),)


# ------------------------------------------------------------------ fonts
FACES = {
    "serif": "Literata_400Regular.ttf",
    "serif-i": "Literata_400Regular_Italic.ttf",
    "serif-md": "Literata_500Medium.ttf",
    "serif-md-i": "Literata_500Medium_Italic.ttf",
    "serif-sb": "Literata_600SemiBold.ttf",
    "serif-sb-i": "Literata_600SemiBold_Italic.ttf",
    "serif-b": "Literata_700Bold.ttf",
    "hand": "Caveat_600SemiBold.ttf",
    "hand-b": "Caveat_700Bold.ttf",
    "sans": "Inter_400Regular.ttf",
    "sans-md": "Inter_500Medium.ttf",
    "sans-sb": "Inter_600SemiBold.ttf",
    "sans-b": "Inter_700Bold.ttf",
}
_fonts = {}


def font(face, size):
    key = (face, int(round(size)))
    if key not in _fonts:
        path = os.path.join(FONT_DIR, FACES[face])
        if not os.path.exists(path):
            raise SystemExit(f"missing font {path}")
        _fonts[key] = ImageFont.truetype(path, key[1])
    return _fonts[key]


def width(f, text, tracking=0.0):
    if not text:
        return 0.0
    return f.getlength(text) + tracking * (len(text) - 1)


def wrap(f, text, max_w):
    """Greedy wrap, then rebalance to the narrowest width that keeps the same
    line count, so a verse never ends on one stranded word."""
    words = text.split()

    def greedy(limit):
        lines, cur = [], []
        for w in words:
            trial = " ".join(cur + [w])
            if cur and f.getlength(trial) > limit:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            lines.append(" ".join(cur))
        return lines

    base = greedy(max_w)
    if len(base) <= 1:
        return base
    lo, hi = max(f.getlength(w) for w in words), max_w
    while hi - lo > 2:
        mid = (lo + hi) / 2
        if len(greedy(mid)) <= len(base):
            hi = mid
        else:
            lo = mid
    return greedy(hi)


def fit(text, face, max_w, max_h, start, floor, leading=1.32):
    """Largest size (stepping down from start) whose wrapped block fits."""
    size = start
    while size >= floor:
        f = font(face, size)
        lines = wrap(f, text, max_w)
        if len(lines) * size * leading <= max_h:
            return size, lines
        size -= 2
    f = font(face, floor)
    return floor, wrap(f, text, max_w)


def draw_tracked(d, xy, text, f, fill, tracking=0.0, anchor="ls"):
    x, y = xy
    if abs(tracking) < 0.01:
        d.text((x, y), text, font=f, fill=fill, anchor=anchor)
        return
    if anchor[0] == "m":
        x -= width(f, text, tracking) / 2
    elif anchor[0] == "r":
        x -= width(f, text, tracking)
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill, anchor="l" + anchor[1])
        x += f.getlength(ch) + tracking


def text_block(d, lines, f, x, y_top, pitch, fill, align="center", box_w=None):
    """Draw wrapped lines from y_top (top of first line box). Returns bottom y."""
    ascent, descent = f.getmetrics()
    for i, line in enumerate(lines):
        base = y_top + i * pitch + pitch / 2 + (ascent - descent) / 2
        if align == "center":
            d.text((x, base), line, font=f, fill=fill, anchor="ms")
        elif align == "left":
            d.text((x, base), line, font=f, fill=fill, anchor="ls")
        else:
            d.text((x, base), line, font=f, fill=fill, anchor="rs")
    return y_top + len(lines) * pitch


def shadow_layer(layer, radius=18, strength=0.55, color=(8, 6, 3)):
    """A soft shadow from a text layer's alpha, for type set on photographs."""
    a = layer.split()[3].filter(ImageFilter.GaussianBlur(radius))
    a = a.point(lambda v: int(min(255, v * strength * 1.8)))
    sh = Image.new("RGBA", layer.size, color + (0,))
    sh.putalpha(a)
    return sh


# ----------------------------------------------------------------- grounds
def grain(size, amount=6.0, seed=7):
    """Monochrome film grain as an RGBA layer centred on mid grey."""
    rng = np.random.default_rng(seed)
    w, h = size
    n = rng.normal(0, amount, (h, w)).clip(-40, 40)
    layer = np.zeros((h, w, 4), dtype=np.uint8)
    layer[..., 0:3] = np.where(n[..., None] > 0, 255, 0)
    layer[..., 3] = np.abs(n).astype(np.uint8)
    return Image.fromarray(layer, "RGBA")


def paper(size=(W, H), tone=PAPER, seed=7, vignette=0.06):
    """Warm paper: the app's ground, a little grain and a faint vignette."""
    w, h = size
    im = Image.new("RGBA", size, tone + (255,))
    if vignette:
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        v = (np.clip(r - 0.55, 0, None) * vignette * 255).astype(np.uint8)
        vl = np.zeros((h, w, 4), dtype=np.uint8)
        vl[..., 0:3] = (80, 60, 30)
        vl[..., 3] = v
        im.alpha_composite(Image.fromarray(vl, "RGBA"))
    im.alpha_composite(grain(size, 4.5, seed))
    return im


def cover(im, w, h, focus=(0.5, 0.5)):
    im = im.convert("RGB")
    sw, sh = im.size
    s = max(w / sw, h / sh)
    nw, nh = int(math.ceil(sw * s)), int(math.ceil(sh * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = int(round(min(max(focus[0] * nw - w / 2, 0), nw - w)))
    top = int(round(min(max(focus[1] * nh - h / 2, 0), nh - h)))
    return im.crop((left, top, left + w, top + h))


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def drop_shadow(size, box, radius, blur=28, alpha=0.22, offset=(0, 14)):
    """Soft shadow under a rounded panel, as an RGBA layer of `size`."""
    layer = Image.new("RGBA", size, (40, 28, 12, 0))
    m = Image.new("L", size, 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(m).rounded_rectangle((x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]),
                                        radius=radius, fill=int(255 * alpha))
    layer.putalpha(m.filter(ImageFilter.GaussianBlur(blur)))
    return layer


# ---------------------------------------------------------------- marks
def wordmark(variant="black", width_px=200, opacity=0.4):
    wm = Image.open(os.path.join(IMG_DIR, f"wordmark-{variant}.png")).convert("RGBA")
    h = int(round(width_px * wm.height / wm.width))
    wm = wm.resize((width_px, h), Image.LANCZOS)
    wm.putalpha(wm.split()[3].point(lambda v: int(v * opacity)))
    return wm


def footer(im, dark=False, pad_x=84, pad_bottom=70, opacity=None, domain=True):
    """Wordmark bottom left, chasten.ai bottom right on its baseline (the share
    card's footer, a touch smaller so it never competes with the format)."""
    wm = wordmark("white" if dark else "black", 210, opacity or (0.55 if dark else 0.36))
    y = im.height - pad_bottom - wm.height
    im.alpha_composite(wm, (pad_x, y))
    if domain:
        bbox = wm.split()[3].point(lambda v: 255 if v > 90 else 0).getbbox()
        base = y + (bbox[3] if bbox else wm.height)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        f = font("sans-sb", 28)
        col = (255, 255, 255) if dark else INK
        draw_tracked(ImageDraw.Draw(layer), (im.width - pad_x, base), "chasten.ai", f,
                     with_alpha(col, 0.62 if dark else 0.4), 1.1, anchor="rs")
        im.alpha_composite(layer)
    return im


def arrow(d, start, end, color, width=7, bend=0.25, head=26):
    """A hand-drawn style arrow: a gently bowed stroke and an open head."""
    (x0, y0), (x1, y1) = start, end
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), (x1 - x0)
    cx, cy = mx + nx * bend, my + ny * bend
    pts = []
    for i in range(41):
        t = i / 40
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1
        pts.append((x, y))
    d.line(pts, fill=color, width=width, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - width / 2, p[1] - width / 2, p[0] + width / 2, p[1] + width / 2), fill=color)
    tx, ty = pts[-1][0] - pts[-4][0], pts[-1][1] - pts[-4][1]
    ang = math.atan2(ty, tx)
    for side in (-1, 1):
        a = ang + math.pi - side * 0.55
        hx, hy = x1 + head * math.cos(a), y1 + head * math.sin(a)
        d.line([(x1, y1), (hx, hy)], fill=color, width=width)
        d.ellipse((hx - width / 2, hy - width / 2, hx + width / 2, hy + width / 2), fill=color)


def save(im, path, quality=93):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.convert("RGB").save(path, "JPEG", quality=quality, subsampling=0, optimize=True)
    return path


def seeded(seed):
    return random.Random(seed)
