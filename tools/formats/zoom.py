"""
Wednesday: "Swipe to zoom in". Slide one says "You're THIS close to..." over a
pinching hand with a speck of text between the fingertips. Each swipe zooms
closer until the speck is a verse you can read, framed by the two fingers.

Every slide is drawn fresh at its own zoom, so the type is real type at every
size (never an enlarged picture of letters) and the verse stays word-perfect.
"""

import json
import os

from PIL import Image, ImageDraw

from . import common as c

ZOOMS = (1.0, 1.6, 2.45, 3.6, 5.2)
HAND_SCALE = 0.62                 # slide-one pixels per hand-art pixel
HAND_AT = (130, 330)              # where the art's top-left corner sits on slide one


def _load_hand():
    art = os.path.join(c.ART_DIR, "hand-pinch.png")
    meta = json.load(open(os.path.join(c.ART_DIR, "hand-pinch.json")))
    return Image.open(art).convert("RGBA"), meta["gap"]


def _view(hand, center, z):
    """The hand as seen in a 1080 x 1350 window centred on `center` (slide-one
    coordinates) at zoom z: one affine resample straight from the art."""
    cx, cy = center
    s = HAND_SCALE
    a = 1 / (z * s)
    ox = (cx - c.W / 2 / z - HAND_AT[0]) / s
    oy = (cy - c.H / 2 / z - HAND_AT[1]) / s
    return hand.transform((c.W, c.H), Image.AFFINE, (a, 0, ox, 0, a, oy), resample=Image.BICUBIC)


def render(out_dir, verse, ref, lead="...your harvest.", hook=("You're THIS", "close to..."),
           cue="swipe to zoom in  >>>"):
    hand, gap = _load_hand()
    gx0, gy0, gx1, gy1 = gap
    # the gap in slide-one coordinates, and the zoom that makes it fill the frame
    g0 = (HAND_AT[0] + gx0 * HAND_SCALE, HAND_AT[1] + gy0 * HAND_SCALE)
    g1 = (HAND_AT[0] + gx1 * HAND_SCALE, HAND_AT[1] + gy1 * HAND_SCALE)
    gc = ((g0[0] + g1[0]) / 2, (g0[1] + g1[1]) / 2)
    zf = ZOOMS[-1]

    # Lay the payoff out once, at the final zoom, in output pixels: a lead-in in
    # Caveat, the verse, the reference. Then scale it to every other zoom.
    gap_w = (g1[0] - g0[0]) * zf * 0.9
    gap_h = (g1[1] - g0[1]) * zf
    lead_size, ref_size = 46, 25
    size, lines = c.fit(verse, "serif-md", gap_w, gap_h - 150, 50, 30, leading=1.3)
    pitch = size * 1.3
    block_h = lead_size * 1.25 + len(lines) * pitch + ref_size * 2.4
    top_final = c.H / 2 - block_h / 2           # the block sits centred in the last frame

    paths = []
    for k, z in enumerate(ZOOMS):
        t = ((z - 1) / (zf - 1)) ** 0.9
        center = (c.W / 2 + (gc[0] - c.W / 2) * t, c.H / 2 + (gc[1] - c.H / 2) * t)
        im = c.paper(seed=50 + k)
        d = ImageDraw.Draw(im)

        def to_out(x, y):
            return ((x - center[0]) * z + c.W / 2, (y - center[1]) * z + c.H / 2)

        # the hook, in slide-one coordinates, grows off the frame as we zoom
        hf = c.font("serif-b", 116 * z)
        for i, line in enumerate(hook):
            bx, by = to_out(78, 218 + i * 132)
            if i == 0:
                pre, word = line.split(" ", 1)[0] + " ", line.split(" ", 1)[1]
                wx = bx + hf.getlength(pre)
                ww = hf.getlength(word)
                d.rounded_rectangle((wx - 14 * z, by - 96 * z, wx + ww + 14 * z, by + 26 * z), radius=14 * z,
                                    fill=c.WASH["amber"][0])
            d.text((bx, by), line, font=hf, fill=c.INK, anchor="ls")

        im.alpha_composite(_view(hand, center, z))

        # the speck between the fingertips: the payoff, scaled from its final layout
        k_scale = z / zf
        fx, fy = to_out(gc[0], gc[1])
        y = fy + (top_final - c.H / 2) * k_scale
        lf = c.font("hand-b", max(1, lead_size * k_scale))
        d.text((fx, y + lead_size * 1.0 * k_scale), lead, font=lf, fill=c.GOLD, anchor="ms")
        y += lead_size * 1.25 * k_scale
        vf = c.font("serif-md", max(1, size * k_scale))
        c.text_block(d, lines, vf, fx, y, pitch * k_scale, c.INK)
        y += len(lines) * pitch * k_scale
        rf = c.font("sans-sb", max(1, ref_size * k_scale))
        c.draw_tracked(d, (fx, y + ref_size * 1.7 * k_scale), ref.upper(), rf, c.GOLD, 2.4 * k_scale, anchor="ms")

        # fixed notes that are not part of the zoomed world
        if k == 0:
            d.text((84, c.H - 84), cue, font=c.font("hand-b", 56), fill=c.GOLD, anchor="ls")
            wm = c.wordmark("black", 150, 0.34)
            im.alpha_composite(wm, (c.W - 84 - wm.width, 70))
        paths.append(c.save(im, os.path.join(out_dir, f"{k + 1}.jpg")))
    return paths
