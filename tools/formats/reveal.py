"""
Monday: "Swipe to reveal". A photo starts as a coarse mosaic and sharpens
slide by slide; holding Instagram's dots and sliding plays the reveal like a
flipbook. The frame around the photo (title, note, instruction) stays crisp on
every slide, so only the picture changes, and the verse arrives on the last.

Layouts:
  center   the verse in the middle of a landscape or flower photo
  left     a person on the right: the verse in the open left side, sideways veil
  right    the mirror of left
  top      a group lower in the frame: the verse in the open sky above them
  bottom   a close-up of faces: the verse in a band low in the picture, over
           clothes and hands, under a veil that rises from the bottom edge
  caption  a close-up of faces: the photo stays clean and the verse is set on
           the paper beneath it, so no face is ever covered
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

from . import common as c

LEVELS = (90, 68, 52, 40, 31, 24, 17)  # mosaic block sizes, coarse to fine; then sharp.
# Even the finest stays too coarse to read Literata at verse size, so the words
# only arrive on the last slide.
PANEL = (60, 236, 1020, 1136)          # x0, y0, x1, y1
CAPTION_PANEL = (60, 236, 1020, 1000)  # shorter, so the verse fits on the paper below
RADIUS = 34


def _photo(photo_path, box, focus, crop=None):
    """The photo cut to the panel. crop is an optional (x0, y0, x1, y1) in fractions
    of the source, taken first: trim an edge the frame should not show."""
    pw, ph = box[2] - box[0], box[3] - box[1]
    src = Image.open(photo_path).convert("RGB")
    if crop:
        w, h = src.size
        src = src.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    return c.cover(src, pw, ph, focus).convert("RGBA")


def _panel(verse, ref, photo_path, box, focus=(0.5, 0.5), dim=0.0, layout="center", text_at=0.46, col=0.42, crop=None):
    pw, ph = box[2] - box[0], box[3] - box[1]
    photo = _photo(photo_path, box, focus, crop)
    if layout == "caption":
        return photo
    if layout == "center":
        # A veil deep enough for white type on any photo in the library, heavier
        # behind the words than at the edges so the colour still reads.
        photo.alpha_composite(Image.new("RGBA", (pw, ph), (12, 8, 4, int(255 * (0.30 + dim)))))
        pool = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(pool).ellipse((pw * 0.02, ph * 0.18, pw * 0.98, ph * 0.82), fill=110)
        pool = pool.filter(ImageFilter.GaussianBlur(120))
    elif layout == "bottom":
        photo.alpha_composite(Image.new("RGBA", (pw, ph), (12, 8, 4, int(255 * (0.04 + dim)))))
        ramp = Image.linear_gradient("L").resize((pw, ph))
        pool = ramp.point(lambda v: int(190 * max(0.0, min(1.0, (v / 255 - 0.52) / 0.42)) ** 1.25))
    elif layout == "top":
        photo.alpha_composite(Image.new("RGBA", (pw, ph), (12, 8, 4, int(255 * (0.06 + dim)))))
        ramp = Image.linear_gradient("L").rotate(180).resize((pw, ph))
        pool = ramp.point(lambda v: int(165 * max(0.0, min(1.0, (v / 255 - 0.42) / 0.5)) ** 1.3))
    else:
        photo.alpha_composite(Image.new("RGBA", (pw, ph), (12, 8, 4, int(255 * (0.06 + dim)))))
        ramp = Image.linear_gradient("L").rotate(90 if layout == "left" else -90, expand=True).resize((pw, ph))
        pool = ramp.point(lambda v: int(150 * max(0.0, min(1.0, (v / 255 - 0.36) / 0.5)) ** 1.4))
    dark = Image.new("RGBA", (pw, ph), (12, 8, 4, 0))
    dark.putalpha(pool)
    photo.alpha_composite(dark)

    text = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(text)
    ref_f = c.font("sans-sb", 30)
    if layout == "bottom":
        size, lines = c.fit(verse, "serif-sb", pw - 150, ph * 0.22, 50, 32, leading=1.22)
        f = c.font("serif-sb", size)
        pitch = size * 1.22
        block_h = len(lines) * pitch + 40 + 30
        top = min(ph - 34 - block_h, ph * text_at - block_h / 2)
        bottom = c.text_block(d, lines, f, pw / 2, top, pitch, (255, 255, 255, 255))
        d.line((pw / 2 - 34, bottom + 18, pw / 2 + 34, bottom + 18), fill=c.with_alpha(c.GOLD_DARK, 0.95), width=3)
        c.draw_tracked(d, (pw / 2, bottom + 66), ref.upper(), ref_f, (255, 255, 255, 235), 3.2, anchor="ms")
    elif layout == "top":
        size, lines = c.fit(verse, "serif-sb", pw - 180, ph * 0.26, 48, 32, leading=1.24)
        f = c.font("serif-sb", size)
        pitch = size * 1.24
        block_h = len(lines) * pitch + 46 + 30
        top = max(30, ph * text_at - block_h / 2)
        bottom = c.text_block(d, lines, f, pw / 2, top, pitch, (255, 255, 255, 255))
        d.line((pw / 2 - 34, bottom + 20, pw / 2 + 34, bottom + 20), fill=c.with_alpha(c.GOLD_DARK, 0.95), width=3)
        c.draw_tracked(d, (pw / 2, bottom + 72), ref.upper(), ref_f, (255, 255, 255, 230), 3.2, anchor="ms")
    elif layout == "center":
        size, lines = c.fit(verse, "serif-sb", pw - 170, ph - 330, 68, 40, leading=1.3)
        f = c.font("serif-sb", size)
        pitch = size * 1.3
        block_h = len(lines) * pitch + 46 + 30
        top = (ph - block_h) / 2 - 6
        bottom = c.text_block(d, lines, f, pw / 2, top, pitch, (255, 255, 255, 255))
        d.line((pw / 2 - 34, bottom + 22, pw / 2 + 34, bottom + 22), fill=c.with_alpha(c.GOLD_DARK, 0.95), width=3)
        c.draw_tracked(d, (pw / 2, bottom + 76), ref.upper(), ref_f, (255, 255, 255, 225), 3.2, anchor="ms")
    else:
        col_w = pw * col
        x = 54 if layout == "left" else pw - 54 - col_w
        size, lines = c.fit(verse, "serif-sb", col_w, ph - 300, 54, 36, leading=1.28)
        f = c.font("serif-sb", size)
        pitch = size * 1.28
        block_h = len(lines) * pitch + 46 + 30
        top = max(40, ph * text_at - block_h / 2)
        bottom = c.text_block(d, lines, f, x, top, pitch, (255, 255, 255, 255), align="left")
        d.line((x + 2, bottom + 22, x + 70, bottom + 22), fill=c.with_alpha(c.GOLD_DARK, 0.95), width=3)
        c.draw_tracked(d, (x + 2, bottom + 76), ref.upper(), ref_f, (255, 255, 255, 230), 3.2)
    photo.alpha_composite(c.shadow_layer(text, 16, 0.55 if layout == "center" else 0.75))
    photo.alpha_composite(text)
    return photo


def _mosaic(panel, block):
    w, h = panel.size
    small = panel.resize((max(1, math.ceil(w / block)), max(1, math.ceil(h / block))), Image.BOX)
    return small.resize((w, h), Image.NEAREST)


def _frame(final, box, verse, ref, title, note_hidden, note_found, cta_hidden, cta_found, caption):
    im = c.paper()
    d = ImageDraw.Draw(im)
    d.text((78, 126), title, font=c.font("serif-sb", 56), fill=c.INK, anchor="ls")
    note = note_found if final else note_hidden
    nf = c.font("hand-b", 50)
    d.text((84, 190), note, font=nf, fill=c.GOLD, anchor="ls")
    nx = 84 + nf.getlength(note) + 18
    c.arrow(d, (nx, 172), (nx + 64, 214), c.GOLD, width=5, bend=-0.35, head=16)
    wm = c.wordmark("black", 150, 0.34)
    im.alpha_composite(wm, (1020 - wm.width, 126 - int(wm.height * 0.78)))

    below_top, below_bottom = box[3], c.H
    if caption and final:
        # the verse on the paper under the photo, ink on paper, never over a face
        area_h = below_bottom - below_top - 96
        size, lines = c.fit(verse, "serif-sb", c.W - 2 * 90, area_h - 70, 50, 32, leading=1.26)
        f = c.font("serif-sb", size)
        pitch = size * 1.26
        block_h = len(lines) * pitch + 58
        top = below_top + (below_bottom - below_top - block_h) / 2 - 10
        bottom = c.text_block(d, lines, f, c.W / 2, top, pitch, c.INK)
        c.draw_tracked(d, (c.W / 2, bottom + 46), ref.upper(), c.font("sans-sb", 29), c.GOLD, 3.2, anchor="ms")
        return im
    cf = c.font("hand-b", 54)
    msg = cta_found if final else cta_hidden
    mid = (below_top + below_bottom) / 2 + (8 if caption else -23)
    d.text((540, mid + 18), msg, font=cf, fill=c.INK, anchor="ms")
    if not final:
        tw = cf.getlength(msg)
        for side in (-1, 1):
            x = 540 + side * (tw / 2 + 56)
            c.arrow(d, (x - side * 14, mid - 28), (x + side * 4, mid + 72), c.INK, width=6, bend=0.32 * side, head=24)
    return im


def render(out_dir, verse, ref, photo_path, focus=(0.5, 0.5), dim=0.0, layout="center", text_at=0.46, col=0.42,
           crop=None, title="Your verse for the week", note_hidden="is hiding in here", note_found="there it is",
           cta_hidden="hold the dots and slide to reveal it", cta_found="save it for the week ahead"):
    caption = layout == "caption"
    box = CAPTION_PANEL if caption else PANEL
    sharp = _panel(verse, ref, photo_path, box, focus, dim, layout, text_at, col, crop)
    vivid = _photo(photo_path, box, focus, crop)
    pw, ph = sharp.size
    mask = c.rounded_mask((pw, ph), RADIUS)
    paths = []
    # The first slide is what the feed shows, so it starts from the photo at full
    # colour and eases into the veiled, lettered version as the blocks shrink.
    n = len(LEVELS)
    frames = [(_mosaic(Image.blend(vivid, sharp, (k / (n - 1)) ** 0.8), b), False) for k, b in enumerate(LEVELS)]
    frames.append((sharp, True))
    for i, (panel, final) in enumerate(frames, 1):
        im = _frame(final, box, verse, ref, title, note_hidden, note_found, cta_hidden, cta_found, caption)
        im.alpha_composite(c.drop_shadow(im.size, box, RADIUS, blur=26, alpha=0.20))
        clipped = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        clipped.paste(panel, (0, 0), mask)
        im.alpha_composite(clipped, (box[0], box[1]))
        paths.append(c.save(im, os.path.join(out_dir, f"{i}.jpg")))
    return paths
