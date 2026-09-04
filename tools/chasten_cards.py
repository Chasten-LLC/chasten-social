#!/usr/bin/env python3
"""
Chasten verse share cards, rendered standalone with Pillow.

Matches the app's share card (src/features/reader/share-card-geometry.ts):
a fixed 1080 x 1350 frame, reference | translation over a 2px rule, the verse
flush left on a double (2em) baseline with one rounded wash block per line and
a deeper block behind the verse number, the wordmark bottom left at reduced
opacity and the domain bottom right on the wordmark's baseline.

Three surfaces:
  paper  - light card, wash + number block in one of six inks
  night  - dark card, bold wash with flipped ink, number block one step down
  photo  - a photograph fills the frame; NO wash and NO number block, the
           verse number sits bare; a scrim keeps the text legible

Usage:
  python3 chasten_cards.py render --style paper --ink amber \
      --ref "Psalm 23" --verse 1 --translation BSB \
      --text "The LORD is my shepherd; I shall not want." --out card.png

  python3 chasten_cards.py render --style photo --photo bg.jpg \
      --photo-ink "#FFF9F1" --scrim dark ...

  python3 chasten_cards.py batch spec.json
      spec: {"cards":[{...same keys as render...,"out":"a.png"}, ...]}

Fonts are looked up in --fonts-dir (default ./assets/fonts): Literata 400
for the verse, Inter 600 for the reference, translation, digits and domain
(the app uses the platform sans; Inter is the closest free match).
Wordmarks are looked up in --img-dir (default ./assets/img).
"""

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- geometry
CARD_W, CARD_H = 1080, 1350
PAD_TOP, PAD_SIDE, PAD_BOTTOM = 92, 84, 78

REF_SIZE, REF_TRACKING_EM = 38, -0.01
TRANSLATION_SIZE, TRANSLATION_TRACKING_EM = 32, 0.10
HEADER_GAP, DIVIDER_W, DIVIDER_H, HEADER_RULE = 26, 2, 34, 2

VERSE_BAND_INSET = 30
VERSE_LINE_HEIGHT_EM = 2.0
WASH_BOX_EM = 1.8
WASH_GAP_EM = VERSE_LINE_HEIGHT_EM - WASH_BOX_EM
WASH_PAD_X_EM = 0.24
WASH_RADIUS, NUMBER_RADIUS = 10, 6
NUMBER_MIN_CONTENT_EM, NUMBER_PAD_X_EM, NUMBER_GAP_EM, DIGIT_EM = 0.62, 0.17, 0.20, 0.40

WORDMARK_WIDTH = 250
WORDMARK_ASPECT = 3162 / 988
DOMAIN_TEXT, DOMAIN_SIZE, DOMAIN_TRACKING_EM = "chasten.ai", 30, 0.04

RAMP = [(60, 96), (120, 78), (200, 64), (300, 52), (430, 44)]
VERSE_MIN_SIZE = 38


def verse_font_size(char_count):
    for max_chars, size in RAMP:
        if char_count <= max_chars:
            return size
    return VERSE_MIN_SIZE


# ------------------------------------------------------------------ colour
LIGHT = {"bg": "#FAF6EE", "ink": "#2B241C", "sub": "#8F8371"}
DARK = {"bg": "#000000", "ink": "#ECECEE", "sub": "#9A9AA0", "onAccent": "#17171A"}

HIGHLIGHT = {
    "amber":    {"lightFill": "#F1DFA8", "dot": "#DFB65C", "darkFill": "#594311", "darkFillBold": "#E1A219"},
    "apricot":  {"lightFill": "#F7DFC2", "dot": "#E0A468", "darkFill": "#653C13", "darkFillBold": "#EB9C4C"},
    "rose":     {"lightFill": "#F2DAD2", "dot": "#DCA391", "darkFill": "#792F17", "darkFillBold": "#F0977B"},
    "sky":      {"lightFill": "#D6E4EA", "dot": "#92B7C8", "darkFill": "#134B65", "darkFillBold": "#4AB8EB"},
    "sage":     {"lightFill": "#DEE7C8", "dot": "#A9BD7F", "darkFill": "#384C0F", "darkFillBold": "#8EBC2F"},
    "lavender": {"lightFill": "#E3DCEF", "dot": "#AFA1D2", "darkFill": "#411D9A", "darkFillBold": "#B8A0F4"},
}
NUMBER_ALPHA = {"amber": 0.62, "apricot": 0.55, "rose": 0.55, "sky": 0.5, "sage": 0.5, "lavender": 0.45}
INKS = list(HIGHLIGHT.keys())

PALETTE = {
    "paper": {
        "bg": LIGHT["bg"], "ink": LIGHT["ink"], "muted": LIGHT["sub"],
        "rule": (43, 36, 28, 41), "divider": (43, 36, 28, 56),
        "digit": "#5E4B24", "wordmark": "black",
        "wordmarkOpacity": 0.30, "domainOpacity": 0.36,
    },
    "night": {
        "bg": DARK["bg"], "ink": DARK["ink"], "muted": DARK["sub"],
        "rule": (236, 236, 238, 46), "divider": (236, 236, 238, 46),
        "digit": DARK["ink"], "wordmark": "white",
        "wordmarkOpacity": 0.42, "domainOpacity": 0.45,
    },
}


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(color, alpha=1.0):
    if isinstance(color, tuple):
        if len(color) == 4:
            return color
        return color + (int(round(255 * alpha)),)
    return hex_rgb(color) + (int(round(255 * alpha)),)


def ink_fills(ink, mode):
    """The wash, the number block, and (Night only) the flipped verse ink."""
    if ink == "none" or ink is None:
        return {"wash": None, "block": None, "ink": None}
    tone = HIGHLIGHT[ink]
    if mode == "night":
        return {"wash": rgba(tone["darkFillBold"]), "block": rgba(tone["darkFill"]), "ink": DARK["onAccent"]}
    return {"wash": rgba(tone["lightFill"]), "block": rgba(tone["dot"], NUMBER_ALPHA[ink]), "ink": None}


# ------------------------------------------------------------------- fonts
class Fonts:
    def __init__(self, fonts_dir):
        self.dir = fonts_dir
        self._cache = {}

    def _path(self, name):
        p = os.path.join(self.dir, name)
        if not os.path.exists(p):
            raise SystemExit(f"missing font {p}")
        return p

    def serif(self, size):
        return self._get("Literata_400Regular.ttf", size)

    def sans(self, size):
        return self._get("Inter_600SemiBold.ttf", size)

    def _get(self, name, size):
        key = (name, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(self._path(name), size)
        return self._cache[key]


def text_width(font, text, tracking_px=0.0):
    if not text:
        return 0.0
    return font.getlength(text) + tracking_px * (len(text) - 1)


def draw_tracked(draw, xy, text, font, fill, tracking_px=0.0):
    """Draw text with letter spacing (Pillow has none), anchored at baseline-left."""
    x, y = xy
    if abs(tracking_px) < 0.01:
        draw.text((x, y), text, font=font, fill=fill, anchor="ls")
        return
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + tracking_px


def wrap_lines(font, text, max_width, first_line_indent):
    """Greedy word wrap. Returns [(line_text, x_offset, width)]."""
    words = text.split()
    lines, cur, indent = [], [], first_line_indent
    for w in words:
        trial = " ".join(cur + [w])
        if cur and font.getlength(trial) + indent > max_width:
            lines.append((" ".join(cur), indent, font.getlength(" ".join(cur))))
            cur, indent = [w], 0
        else:
            cur.append(w)
    if cur:
        lines.append((" ".join(cur), indent, font.getlength(" ".join(cur))))
    return lines


# ------------------------------------------------------------------ photo
def cover_crop(im, w, h, focus=(0.5, 0.45)):
    """Scale-to-cover then crop to w x h, keeping the focus point in frame."""
    im = im.convert("RGB")
    sw, sh = im.size
    scale = max(w / sw, h / sh)
    nw, nh = int(round(sw * scale)), int(round(sh * scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    fx, fy = focus
    left = int(round(min(max(fx * nw - w / 2, 0), nw - w)))
    top = int(round(min(max(fy * nh - h / 2, 0), nh - h)))
    return im.crop((left, top, left + w, top + h))


def vertical_gradient(w, h, stops):
    """stops: [(pos 0..1, (r,g,b,a)), ...] top to bottom."""
    grad = Image.new("RGBA", (1, h))
    px = grad.load()
    stops = sorted(stops)
    for y in range(h):
        t = y / max(h - 1, 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                u = 0 if p1 == p0 else (t - p0) / (p1 - p0)
                px[0, y] = tuple(int(round(c0[k] + (c1[k] - c0[k]) * u)) for k in range(4))
                break
        else:
            px[0, y] = stops[0][1] if t < stops[0][0] else stops[-1][1]
    return grad.resize((w, h))


def radial_pool(w, h, center, radius, color, opacity):
    """A soft elliptical pool of colour behind the verse band."""
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    cx, cy = center
    rx, ry = radius
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=int(255 * opacity))
    mask = mask.filter(ImageFilter.GaussianBlur(min(rx, ry) * 0.45))
    layer = Image.new("RGBA", (w, h), hex_rgb(color) + (0,))
    layer.putalpha(mask)
    return layer


def band_luminance(photo, verse_center_y):
    """Mean luminance (0-255) of the photo where the verse will sit."""
    band = photo.convert("L").crop((PAD_SIDE, max(verse_center_y - 380, 0), CARD_W - PAD_SIDE, min(verse_center_y + 380, CARD_H)))
    band = band.resize((32, 32))
    return sum(band.getdata()) / (32 * 32)


def dress_photo(photo, scrim, dim, verse_center_y):
    """Apply the app's scrim family (photo-card-geometry.ts scrimSet) plus an
    optional extra dim, tuned a little stronger because this card sets the
    verse flush left over the photo rather than centred in a pool.

    The scrim's strength adapts to the photo: a photo that is already dark
    (a rose against shadow, wheat at dusk) needs far less veil than a bright
    meadow, and the full veil turns it to mud."""
    base = photo.convert("RGBA")
    lum = band_luminance(photo, verse_center_y)
    if scrim == "dark":
        k = max(0.35, min(1.0, (lum - 30) / 110))
        top = vertical_gradient(CARD_W, CARD_H, [(0, (8, 6, 3, int(82 * k))), (0.2, (8, 6, 3, 0)), (1, (8, 6, 3, 0))])
        bottom = vertical_gradient(CARD_W, CARD_H, [(0, (8, 6, 3, 0)), (0.38, (8, 6, 3, 0)), (0.6, (8, 6, 3, int(41 * k))), (1, (8, 6, 3, int(128 * k)))])
        base.alpha_composite(top)
        base.alpha_composite(bottom)
        base.alpha_composite(radial_pool(CARD_W, CARD_H, (CARD_W // 2, verse_center_y), (760, 520), "#180E04", 0.38 * k))
        dim_color = (8, 6, 3)
    elif scrim == "light":
        k = max(0.4, min(1.0, (225 - lum) / 110))
        veil = vertical_gradient(CARD_W, CARD_H, [(0, (255, 252, 249, int(26 * k))), (0.4, (255, 251, 248, int(77 * k))), (1, (255, 251, 248, int(31 * k)))])
        base.alpha_composite(veil)
        base.alpha_composite(radial_pool(CARD_W, CARD_H, (CARD_W // 2, verse_center_y), (760, 520), "#FFFCF9", 0.42 * k))
        dim_color = (255, 252, 249)
    else:
        dim_color = (8, 6, 3)
    if dim > 0:
        base.alpha_composite(Image.new("RGBA", (CARD_W, CARD_H), dim_color + (int(255 * dim),)))
    return base


def shadowed_text_layer(size, draw_fn, shadow_color, radius, passes=2):
    """Render text via draw_fn onto a transparent layer; return (shadow, text)."""
    text = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(text), None)
    alpha = text.split()[3]
    shadow = Image.new("RGBA", size, shadow_color[:3] + (0,))
    sh_alpha = alpha.filter(ImageFilter.GaussianBlur(radius))
    # thicken: blur twice and scale alpha up so the glow reads at feed size
    for _ in range(passes - 1):
        sh_alpha = Image.eval(sh_alpha.filter(ImageFilter.GaussianBlur(radius)), lambda v: min(255, int(v * 1.6)))
    sh_alpha = Image.eval(sh_alpha, lambda v: int(v * shadow_color[3] / 255))
    shadow.putalpha(sh_alpha)
    return shadow, text


# ----------------------------------------------------------------- render
def render_cta(spec, fonts, img_dir):
    """Closing call to action. Same ground, ink, fonts and footer as the verse cards,
    minus the header and number block, so it reads as slide four rather than an advert."""
    style = spec.get("style", "paper")
    ink = spec.get("ink", "amber")
    text = " ".join(spec["text"].split())
    pal = PALETTE[style]
    fills = ink_fills(ink, style)
    body_ink = fills["ink"] or pal["ink"]

    base = Image.new("RGBA", (CARD_W, CARD_H), rgba(pal["bg"]))
    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    font_size = verse_font_size(len(text) + 60)   # a notch calmer than a full verse
    pitch = VERSE_LINE_HEIGHT_EM * font_size
    serif = fonts.serif(font_size)
    dom_font = fonts.sans(DOMAIN_SIZE)
    content_w_px = CARD_W - 2 * PAD_SIDE
    lines = wrap_lines(serif, text, content_w_px, 0)

    footer_h = int(round(WORDMARK_WIDTH / WORDMARK_ASPECT))
    band_top, band_bottom = PAD_TOP, CARD_H - PAD_BOTTOM - footer_h
    text_top = band_top + (band_bottom - band_top - len(lines) * pitch) / 2
    # The wash blocks are what make the verse ink legible on a night ground, so the
    # call to action carries them too and reads as the same kind of card.
    ascent, descent = serif.getmetrics()
    wash_fill = fills["wash"]
    pad_x = WASH_PAD_X_EM * font_size
    box_h = pitch - WASH_GAP_EM * font_size
    for i, (ltxt, lx, lw) in enumerate(lines):
        line_top = text_top + i * pitch
        if wash_fill is not None:
            wx0 = PAD_SIDE + lx - pad_x
            wy0 = line_top + pitch / 2 - box_h / 2
            od.rounded_rectangle((wx0, wy0, wx0 + lw + pad_x * 2, wy0 + box_h),
                                 radius=WASH_RADIUS, fill=wash_fill)
    for i, (ltxt, lx, lw) in enumerate(lines):
        baseline = text_top + i * pitch + pitch / 2 + (ascent - descent) / 2
        od.text((PAD_SIDE + lx, baseline), ltxt, font=serif, fill=rgba(body_ink), anchor="ls")

    wm = Image.open(os.path.join(img_dir, f"wordmark-{pal['wordmark']}.png")).convert("RGBA")
    wm_h = int(round(WORDMARK_WIDTH / WORDMARK_ASPECT))
    wm = wm.resize((WORDMARK_WIDTH, wm_h), Image.LANCZOS)
    wm.putalpha(Image.eval(wm.split()[3], lambda v: int(v * pal["wordmarkOpacity"])))
    wm_y = CARD_H - PAD_BOTTOM - wm_h
    overlay.alpha_composite(wm, (PAD_SIDE, wm_y))

    ink_bbox = wm.split()[3].point(lambda v: 255 if v > 110 else 0).getbbox()
    last_ink_y = wm_y + (ink_bbox[3] if ink_bbox else wm_h)
    dom_tracking = DOMAIN_TRACKING_EM * DOMAIN_SIZE
    dom_w = text_width(dom_font, DOMAIN_TEXT, dom_tracking)
    dom_layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    draw_tracked(ImageDraw.Draw(dom_layer), (CARD_W - PAD_SIDE - dom_w, last_ink_y),
                 DOMAIN_TEXT, dom_font, rgba(pal["ink"]), dom_tracking)
    dom_layer.putalpha(Image.eval(dom_layer.split()[3], lambda v: int(v * pal["domainOpacity"])))
    overlay.alpha_composite(dom_layer)

    out = base.copy()
    out.alpha_composite(overlay)
    return out.convert("RGB")


def render_card(spec, fonts, img_dir):
    if spec.get("style") == "cta":
        return render_cta(dict(spec, style=spec.get("ground", "paper")), fonts, img_dir)
    style = spec.get("style", "paper")
    reference = spec["ref"]
    translation = spec.get("translation", "BSB")
    verse_number = int(spec["verse"])
    verse_text = " ".join(spec["text"].split())
    ink = spec.get("ink", "amber")

    if style == "photo":
        photo_path = spec["photo"]
        photo_ink = spec.get("photo_ink", "#FDFCF9")
        scrim = spec.get("scrim", "dark")
        dim = float(spec.get("dim", 0.0))
        light_ink = spec.get("light_ink")
        if light_ink is None:
            r, g, b = hex_rgb(photo_ink)
            light_ink = (0.299 * r + 0.587 * g + 0.114 * b) > 140
        pal = {
            "ink": photo_ink,
            "muted": rgba(photo_ink, 0.78),
            "rule": rgba(photo_ink, 0.32),
            "divider": rgba(photo_ink, 0.32),
            "digit": photo_ink,
            "wordmark": "white" if light_ink else "black",
            "wordmarkOpacity": 0.72 if light_ink else 0.55,
            "domainOpacity": 0.80 if light_ink else 0.62,
        }
        fills = {"wash": None, "block": None, "ink": None}
        wash_fill = None
    else:
        pal = PALETTE[style]
        fills = ink_fills(ink, style)
        wash_fill = fills["wash"]
        light_ink = style == "night"

    verse_ink = fills["ink"] or pal["ink"]
    font_size = verse_font_size(len(verse_text))
    pitch = VERSE_LINE_HEIGHT_EM * font_size
    serif = fonts.serif(font_size)
    digit_font = fonts.sans(int(round(DIGIT_EM * font_size)))
    ref_font = fonts.sans(REF_SIZE)
    tr_font = fonts.sans(TRANSLATION_SIZE)
    dom_font = fonts.sans(DOMAIN_SIZE)

    # number block width: min-width on content box + padding
    digits = str(verse_number)
    content_w = max(NUMBER_MIN_CONTENT_EM * font_size, digit_font.getlength(digits))
    block_w = content_w + 2 * NUMBER_PAD_X_EM * font_size
    advance = block_w + (NUMBER_GAP_EM - WASH_PAD_X_EM) * font_size
    pad_x = WASH_PAD_X_EM * font_size

    content_w_px = CARD_W - 2 * PAD_SIDE
    lines = wrap_lines(serif, verse_text, content_w_px, advance)

    # header height as RN lays it out: sans text box (~1.21em) + gap + rule
    ref_line_h = int(round(REF_SIZE * 1.21))
    header_h = ref_line_h + HEADER_GAP + HEADER_RULE
    footer_h = int(round(WORDMARK_WIDTH / WORDMARK_ASPECT))
    band_top = PAD_TOP + header_h + VERSE_BAND_INSET
    band_bottom = CARD_H - PAD_BOTTOM - footer_h - VERSE_BAND_INSET
    block_h_total = len(lines) * pitch
    text_top = band_top + (band_bottom - band_top - block_h_total) / 2
    verse_center_y = int((band_top + band_bottom) / 2)

    # ---- ground
    if style == "photo":
        photo = cover_crop(Image.open(photo_path), CARD_W, CARD_H, tuple(spec.get("focus", (0.5, 0.45))))
        base = dress_photo(photo, scrim, dim, verse_center_y)
    else:
        base = Image.new("RGBA", (CARD_W, CARD_H), rgba(pal["bg"]))

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # ---- header
    ref_tracking = REF_TRACKING_EM * REF_SIZE
    ref_baseline = PAD_TOP + int(round(ref_line_h * 0.5 + REF_SIZE * 0.36))
    x = PAD_SIDE
    max_ref_w = content_w_px - (HEADER_GAP * 2 + DIVIDER_W) - text_width(tr_font, translation, TRANSLATION_TRACKING_EM * TRANSLATION_SIZE)
    ref_text = reference
    while text_width(ref_font, ref_text, ref_tracking) > max_ref_w and len(ref_text) > 3:
        ref_text = ref_text[:-2].rstrip() + "…"
    header_items = []  # deferred so photo cards can shadow them

    def draw_header(d, _):
        d_x = PAD_SIDE
        draw_tracked(d, (d_x, ref_baseline), ref_text, ref_font, rgba(pal["ink"]), ref_tracking)
        d_x += text_width(ref_font, ref_text, ref_tracking) + HEADER_GAP
        cy = PAD_TOP + ref_line_h / 2
        d.rectangle((d_x, cy - DIVIDER_H / 2, d_x + DIVIDER_W, cy + DIVIDER_H / 2), fill=pal["divider"])
        d_x += DIVIDER_W + HEADER_GAP
        tr_baseline = PAD_TOP + int(round(ref_line_h * 0.5 + TRANSLATION_SIZE * 0.36))
        draw_tracked(d, (d_x, tr_baseline), translation, tr_font, rgba(pal["muted"]) if not isinstance(pal["muted"], tuple) else pal["muted"], TRANSLATION_TRACKING_EM * TRANSLATION_SIZE)

    rule_y = PAD_TOP + ref_line_h + HEADER_GAP
    od.rectangle((PAD_SIDE, rule_y, CARD_W - PAD_SIDE, rule_y + HEADER_RULE), fill=pal["rule"])

    # ---- wash blocks + number block (paper / night only)
    ascent, descent = serif.getmetrics()
    box_h = pitch - WASH_GAP_EM * font_size
    for i, (ltxt, lx, lw) in enumerate(lines):
        line_top = text_top + i * pitch
        if wash_fill is not None:
            wx0 = PAD_SIDE + lx - pad_x
            wy0 = line_top + pitch / 2 - box_h / 2
            od.rounded_rectangle((wx0, wy0, wx0 + lw + pad_x * 2, wy0 + box_h), radius=WASH_RADIUS, fill=wash_fill)
    if fills["block"] is not None:
        bx0 = PAD_SIDE - pad_x
        by0 = text_top + pitch / 2 - box_h / 2
        od.rounded_rectangle((bx0, by0, bx0 + block_w, by0 + box_h), radius=NUMBER_RADIUS, fill=fills["block"])

    # ---- verse text + digits (+ header, footer domain), shadowed on photo
    def draw_text(d, _):
        draw_header(d, None)
        # digits centred in the block (bare when there is no block)
        bx0 = PAD_SIDE - pad_x
        by0 = text_top + pitch / 2 - box_h / 2
        d.text((bx0 + block_w / 2, by0 + box_h / 2), digits, font=digit_font, fill=rgba(pal["digit"]), anchor="mm")
        for i, (ltxt, lx, lw) in enumerate(lines):
            line_top = text_top + i * pitch
            baseline = line_top + pitch / 2 + (ascent - descent) / 2
            d.text((PAD_SIDE + lx, baseline), ltxt, font=serif, fill=rgba(verse_ink), anchor="ls")

    if style == "photo":
        shadow_color = (20, 12, 4, 150) if light_ink else (255, 252, 250, 170)
        shadow, text_layer = shadowed_text_layer((CARD_W, CARD_H), draw_text, shadow_color, 14 if light_ink else 10)
        overlay.alpha_composite(shadow)
        overlay.alpha_composite(text_layer)
    else:
        draw_text(od, None)

    # ---- footer
    wm = Image.open(os.path.join(img_dir, f"wordmark-{pal['wordmark']}.png")).convert("RGBA")
    wm_h = int(round(WORDMARK_WIDTH / WORDMARK_ASPECT))
    wm = wm.resize((WORDMARK_WIDTH, wm_h), Image.LANCZOS)
    a = wm.split()[3]
    a = Image.eval(a, lambda v: int(v * pal["wordmarkOpacity"]))
    wm.putalpha(a)
    wm_y = CARD_H - PAD_BOTTOM - wm_h
    overlay.alpha_composite(wm, (PAD_SIDE, wm_y))
    # the domain's baseline meets the wordmark's last ink
    ink_bbox = wm.split()[3].point(lambda v: 255 if v > 110 else 0).getbbox()
    last_ink_y = wm_y + (ink_bbox[3] if ink_bbox else wm_h)
    dom_tracking = DOMAIN_TRACKING_EM * DOMAIN_SIZE
    dom_w = text_width(dom_font, DOMAIN_TEXT, dom_tracking)
    dom_layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dom_layer)
    draw_tracked(dd, (CARD_W - PAD_SIDE - dom_w, last_ink_y), DOMAIN_TEXT, dom_font, rgba(pal["ink"]), dom_tracking)
    da = Image.eval(dom_layer.split()[3], lambda v: int(v * pal["domainOpacity"]))
    dom_layer.putalpha(da)
    if style == "photo":
        sh, _ = shadowed_text_layer((CARD_W, CARD_H), lambda d, _: draw_tracked(d, (CARD_W - PAD_SIDE - dom_w, last_ink_y), DOMAIN_TEXT, dom_font, (0, 0, 0, 255), dom_tracking), (20, 12, 4, 110) if light_ink else (255, 252, 250, 120), 8)
        overlay.alpha_composite(sh)
    overlay.alpha_composite(dom_layer)

    out = base.copy()
    out.alpha_composite(overlay)
    return out.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--style", default="paper", choices=["paper", "night", "photo", "cta"])
    r.add_argument("--ink", default="amber")
    r.add_argument("--ref", required=True)
    r.add_argument("--verse", required=True, type=int)
    r.add_argument("--translation", default="BSB")
    r.add_argument("--text", required=True)
    r.add_argument("--photo")
    r.add_argument("--photo-ink", default="#FDFCF9")
    r.add_argument("--scrim", default="dark", choices=["dark", "light", "none"])
    r.add_argument("--dim", type=float, default=0.0)
    r.add_argument("--out", required=True)
    b = sub.add_parser("batch")
    b.add_argument("spec")
    for p in (r, b):
        p.add_argument("--fonts-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts"))
        p.add_argument("--img-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "img"))
    args = ap.parse_args()
    fonts = Fonts(args.fonts_dir)
    if args.cmd == "render":
        spec = {"style": args.style, "ink": args.ink, "ref": args.ref, "verse": args.verse, "translation": args.translation,
                "text": args.text, "photo": args.photo, "photo_ink": args.photo_ink, "scrim": args.scrim, "dim": args.dim}
        render_card(spec, fonts, args.img_dir).save(args.out, quality=95)
        print(args.out)
    else:
        spec = json.load(open(args.spec))
        for card in spec["cards"]:
            im = render_card(card, fonts, args.img_dir)
            im.save(card["out"], quality=95)
            print(card["out"])


if __name__ == "__main__":
    main()
