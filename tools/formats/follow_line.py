"""
Tuesday: "Follow the line". Slide one asks how your morning feels and offers
four answers; a coloured line leaves each one, tangles across the next slides
like a subway map, and lands on a number. The four slides after that hold one
verse each, so whoever follows their line finds the verse for how they feel.
Nobody's verse is chosen for them: they pick the feeling, Scripture answers it.
"""

import os

from PIL import Image, ImageDraw

from . import common as c

SLIDES = 4                      # slides the lines run across
LANES = [300, 410, 520, 630, 740, 850, 960, 1070, 1180]
ROWS = [520, 740, 960, 1180]    # where the four answers sit, and where the numbers wait
FREE = [y for y in LANES if y not in ROWS]
ZONES = [1350, 1800, 2400, 2760, 3110]   # where lines change lanes; clear of every seam
SPREAD = 70                     # each line turns at its own x inside a zone
START_X = 870                   # centre of the answer badges on slide one
END_X = 3 * c.W + 890           # centre of the number badges on the last line slide
BADGE_R = 56
STROKE, HALO, CORNER = 16, 32, 44
SS = 2                          # supersampling for smooth strokes


def route(rng, starts, ends):
    """Orthogonal paths, one per line, that change lanes inside the zones and
    never share a lane or a vertical with another line, so lines only ever cross."""
    n = len(starts)
    cur = list(starts)
    paths = [[(START_X, starts[i])] for i in range(n)]
    for zi, zx in enumerate(ZONES):
        last = zi == len(ZONES) - 1
        order = rng.sample(range(n), n)
        for k, i in enumerate(order):
            x = zx + (k - (n - 1) / 2) * SPREAD
            if last:
                target = ends[i]
            else:
                others = {cur[j] for j in range(n) if j != i}
                choices = [y for y in FREE if y not in others and y != cur[i]]
                far = [y for y in choices if abs(y - cur[i]) >= 220] or choices
                target = rng.choice(far)
            paths[i] += [(x, cur[i]), (x, target)]
            cur[i] = target
    for i in range(n):
        paths[i].append((END_X, ends[i]))
    return paths


def rounded(points, radius):
    """Polyline with each corner replaced by a quarter arc (radius clipped to
    half of the shorter neighbouring segment)."""
    import math
    pts = [points[0]]
    for j in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[j - 1], points[j], points[j + 1]
        l1 = math.hypot(x1 - x0, y1 - y0)
        l2 = math.hypot(x2 - x1, y2 - y1)
        if l1 < 1 or l2 < 1:
            continue
        r = min(radius, l1 / 2, l2 / 2)
        ax, ay = x1 - (x1 - x0) / l1 * r, y1 - (y1 - y0) / l1 * r
        bx, by = x1 + (x2 - x1) / l2 * r, y1 + (y2 - y1) / l2 * r
        for s in range(13):
            t = s / 12
            px = (1 - t) ** 2 * ax + 2 * (1 - t) * t * x1 + t ** 2 * bx
            py = (1 - t) ** 2 * ay + 2 * (1 - t) * t * y1 + t ** 2 * by
            pts.append((px, py))
    pts.append(points[-1])
    return pts


def _badge(size, color, icon=None, label=None):
    d = size * SS
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.ellipse((0, 0, d - 1, d - 1), fill=color + (255,))
    if icon:
        ic = Image.open(os.path.join(c.TOOLS, "assets", "icons", f"{icon}.png")).convert("RGBA")
        k = int(d * 0.56)
        ic = ic.resize((k, k), Image.LANCZOS)
        im.alpha_composite(ic, ((d - k) // 2, (d - k) // 2))
    if label:
        f = c.font("serif-b", int(d * 0.5))
        dr.text((d / 2, d / 2 + d * 0.02), label, font=f, fill=(255, 255, 255, 255), anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


def render(out_dir, answers, verses, seed=1,
           title=("How does your", "morning feel?"), prompt="pick one, then follow its line",
           notes=("keep following...", "almost there..."),
           end_title=("Your verse is on", "the slide with", "your number"), end_note="keep swiping"):
    """answers: [{"label", "icon", "color"}] x4 in slide-one order.
    verses: {label: {"text", "ref", "for"}}. Returns the slide paths."""
    rng = c.seeded(seed)
    n = len(answers)
    numbers = rng.sample(range(n), n)              # numbers[i] = index of the end row line i reaches
    starts = ROWS[:n]
    ends = [ROWS[numbers[i]] for i in range(n)]
    paths = route(rng, starts, ends)

    cw, ch = SLIDES * c.W, c.H
    ground = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for s in range(SLIDES):
        ground.alpha_composite(c.paper(seed=11 + s), (s * c.W, 0))
    lines = Image.new("RGBA", (cw * SS, ch * SS), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    for i, p in enumerate(paths):
        pts = [(x * SS, y * SS) for x, y in rounded(p, CORNER)]
        ld.line(pts, fill=c.PAPER + (255,), width=HALO * SS, joint="curve")
        ld.line(pts, fill=answers[i]["color"] + (255,), width=STROKE * SS, joint="curve")
    ground.alpha_composite(lines.resize((cw, ch), Image.LANCZOS))

    d = ImageDraw.Draw(ground)
    # slide one: the question and the answers
    tf = c.font("serif-b", 88)
    for k, t in enumerate(title):
        d.text((78, 196 + k * 104), t, font=tf, fill=c.INK, anchor="ls")
    pf = c.font("hand-b", 56)
    d.text((84, 396), prompt, font=pf, fill=c.GOLD, anchor="ls")
    lf = c.font("serif-sb-i", 58)
    for i, a in enumerate(answers):
        y = starts[i]
        b = _badge(BADGE_R * 2, a["color"], icon=a["icon"])
        ground.alpha_composite(b, (START_X - BADGE_R, y - BADGE_R))
        d.text((START_X - BADGE_R - 30, y + 18), a["label"], font=lf, fill=c.INK, anchor="rs")
    # the middle slides: a note each
    nf = c.font("hand-b", 58)
    for s, note in enumerate(notes, start=1):
        d.text((s * c.W + 84, 196), note, font=nf, fill=c.SUB, anchor="ls")
    # the last line slide: numbers
    ef = c.font("serif-b", 70)
    x0 = (SLIDES - 1) * c.W
    for k, t in enumerate(end_title):
        d.text((x0 + 78, 150 + k * 84), t, font=ef, fill=c.INK, anchor="ls")
    for i in range(n):
        num = numbers[i] + 1
        b = _badge(BADGE_R * 2, answers[i]["color"], label=str(num))
        ground.alpha_composite(b, (END_X - BADGE_R, ends[i] - BADGE_R))
    enf = c.font("hand-b", 52)
    d.text((x0 + c.W - 84, c.H - 70), end_note + "  >>>", font=enf, fill=c.GOLD, anchor="rs")
    wm = c.wordmark("black", 150, 0.34)
    for s in range(SLIDES):
        if s in (0, SLIDES - 1):
            continue
        ground.alpha_composite(wm, (s * c.W + c.W - 84 - wm.width, 196 - int(wm.height * 0.78)))
    ground.alpha_composite(wm, (c.W - 84 - wm.width, 70))

    paths_out = []
    for s in range(SLIDES):
        tile = ground.crop((s * c.W, 0, (s + 1) * c.W, c.H))
        paths_out.append(c.save(tile, os.path.join(out_dir, f"{s + 1}.jpg")))

    # the verse slides, in number order
    by_number = sorted(range(n), key=lambda i: numbers[i])
    for k, i in enumerate(by_number):
        a = answers[i]
        v = verses[a["label"]]
        im = c.paper(seed=31 + k)
        dr = ImageDraw.Draw(im)
        # the line arrives from the left edge into the number
        lay = Image.new("RGBA", (c.W * SS, c.H * SS), (0, 0, 0, 0))
        ImageDraw.Draw(lay).line([(0, 230 * SS), (150 * SS, 230 * SS)], fill=a["color"] + (255,), width=STROKE * SS)
        im.alpha_composite(lay.resize((c.W, c.H), Image.LANCZOS))
        im.alpha_composite(_badge(BADGE_R * 2, a["color"], label=str(k + 1)), (150, 230 - BADGE_R))
        dr.text((150 + BADGE_R * 2 + 30, 250), v["for"], font=c.font("hand-b", 58), fill=a["color"], anchor="ls")
        size, vl = c.fit(v["text"], "serif-md", c.W - 2 * 96, 660, 88, 44, leading=1.34)
        f = c.font("serif-md", size)
        pitch = size * 1.34
        top = 330 + (720 - len(vl) * pitch) / 2
        bottom = c.text_block(dr, vl, f, 96, top, pitch, c.INK, align="left")
        c.draw_tracked(dr, (98, bottom + 64), v["ref"].upper(), c.font("sans-sb", 32), a["color"], 3.0)
        c.footer(im)
        paths_out.append(c.save(im, os.path.join(out_dir, f"{SLIDES + k + 1}.jpg")))
    return paths_out
