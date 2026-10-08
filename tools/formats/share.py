"""
The 11 AM share days: a photo with a line set over it, then a dark Chasten
verse card. Everything written on a slide is set here in real type; the drawn
photos never carry Scripture.

    photo_slide(...)   the photo, cut to 4:5, with one of three text treatments
    verse_card(...)    the verse on the app's dark ground, a line of ours, a call to share
"""

import os

from PIL import Image, ImageDraw

from . import common as c

DARK_BG = (0, 0, 0)
DARK_INK = (236, 236, 238)       # color.dark.ink
DARK_SUB = (154, 154, 160)       # color.dark.sub


def _cut(photo_path):
    return c.cover(Image.open(photo_path), c.W, c.H, (0.5, 0.45)).convert("RGBA")


def _light(im, box):
    """True when the photo is bright where the words go: then the words are ink
    with a soft paper glow instead of white with a shadow."""
    region = im.convert("L").crop(tuple(int(v) for v in box)).resize((32, 32))
    return sum(region.getdata()) / 1024 > 165


def _scrim(im, place, depth=0.34, strength=0.45):
    """A soft dark gradient from the top (or bottom) edge, so white words stay
    readable on any photo without a box."""
    reach = int(c.H * depth)
    ramp = Image.linear_gradient("L").resize((c.W, reach))  # 0 at the top, 255 at the bottom
    alpha = ramp.point(lambda v: int(255 * strength * (1 - v / 255) ** 1.6))
    if place == "bottom":
        alpha = alpha.transpose(Image.FLIP_TOP_BOTTOM)
    shade = Image.new("RGBA", (c.W, reach), (8, 6, 3, 0))
    shade.putalpha(alpha)
    im.alpha_composite(shade, (0, 0 if place == "top" else c.H - reach))


def _shadowed(im, draw_fn, radius=14, strength=0.7, light=False):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer), c.INK + (255,) if light else (255, 255, 255, 255))
    glow = (250, 246, 238) if light else (8, 6, 3)
    im.alpha_composite(c.shadow_layer(layer, radius, strength, glow))
    im.alpha_composite(layer)


def _band(im, lines, f, pitch, place, radius, strength):
    """Set a short block of lines in the top band (or the bottom band) of the photo."""
    block = len(lines) * pitch
    top = 128 if place == "top" else c.H - 150 - block
    light = _light(im, (80, top - 20, c.W - 80, top + block))
    if not light:
        _scrim(im, place)
    _shadowed(im, lambda d, col: c.text_block(d, lines, f, c.W / 2, top, pitch, col), radius, strength, light)


def photo_slide(photo_path, out_path, kind, text, sub=None, cue=None, place="top"):
    """kind "hook": a caption line, the way people caption a photo they send.
    kind "quote": one line of a conversation, in quotation marks.
    Both sit in the top band, clear of faces, or the bottom band with place="bottom".
    kind "title": a title over a still life, a blessing line beneath it and a small cue."""
    im = _cut(photo_path)
    if kind == "hook":
        f = c.font("sans-sb", 60)
        _band(im, c.wrap(f, text, c.W - 160), f, 74, place, 12, 0.8)
    elif kind == "quote":
        f = c.font("serif-sb-i", 72)
        _band(im, c.wrap(f, "\u201c" + text + "\u201d", c.W - 180), f, 90, place, 16, 0.85)
    elif kind == "title":
        size = 86
        while c.font("serif-b", size).getlength(text) > c.W - 160 and size > 48:
            size -= 2
        tf, sf, rf = c.font("serif-b", size), c.font("serif-i", 42), c.font("sans-sb", 26)
        sub_lines = c.wrap(sf, sub or "", c.W - 240)
        light = _light(im, (80, 110, c.W - 80, 360))
        if not light:
            _scrim(im, "top", 0.4, 0.4)

        def draw(d, col):
            d.text((c.W / 2, 200), text, font=tf, fill=col, anchor="ms")
            end = c.text_block(d, sub_lines, sf, c.W / 2, 236, 56, col)
            if cue:
                c.draw_tracked(d, (c.W / 2, end + 48), cue.upper(), rf, col, 3.0, anchor="ms")
        _shadowed(im, draw, 16, 0.85, light)
    return c.save(im, out_path)


def verse_card(out_path, verse, ref, line=None, cta=None):
    """The verse on the app's dark ground: reference, verse, an optional line of
    ours and the call to share, as one block set a little above the middle."""
    im = Image.new("RGBA", (c.W, c.H), DARK_BG + (255,))
    block = Image.new("RGBA", (c.W, c.H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    c.draw_tracked(d, (90, 170), ref.upper(), c.font("sans-sb", 30), c.GOLD_DARK, 3.4)
    size, lines = c.fit(verse, "serif", c.W - 180, 640, 62, 38, leading=1.42)
    f = c.font("serif", size)
    end = c.text_block(d, lines, f, 90, 220, size * 1.42, DARK_INK, align="left")
    y = end + 40
    if line:
        d.line((90, y, 170, y), fill=(255, 255, 255, 60), width=2)
        lf = c.font("serif-i", 40)
        y = c.text_block(d, c.wrap(lf, line, c.W - 180), lf, 90, y + 30, 56, DARK_SUB, align="left")
    if cta:
        d.text((90, y + 64), cta, font=c.font("sans-sb", 32), fill=c.GOLD_DARK, anchor="ls")
    wm = c.wordmark("white", 190, 0.7)
    floor = c.H - 96 - wm.height
    x0, y0, x1, y1 = block.getbbox()
    top = max(120, int((floor - (y1 - y0)) / 2 - 30))
    im.alpha_composite(block.crop((0, y0, c.W, y1)), (0, top))
    im.alpha_composite(wm, ((c.W - wm.width) // 2, floor))
    return c.save(im, out_path)
