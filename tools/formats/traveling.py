"""
The traveling icon: an animated carousel. A dove sticker flies across the
slides on one continuous path, leaving a dotted trail, and each slide is a
short video: it enters from the left edge, crosses its slide, and leaves by
the right edge into the next one, where the next video picks it up. On the
last slide it lands beside the end of the verse.

Slides are 1080 x 1350 MP4s (Instagram carousels take video items of 3 to 60
seconds). The words are set in real type; only the dove and its trail move.
"""

import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFilter

from . import common as c
from .reel import ffmpeg_bin

FPS = 30
SPEED = 520            # path pixels per second
DOVE_W = 300
EXIT = 190             # how far past a seam the dove travels before a slide's video ends
TRAIL = (198, 138, 46)
SS = 2


def _catmull(points, samples=40):
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(points[-1])
    return out


def _arclen(path):
    acc = [0.0]
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        acc.append(acc[-1] + math.hypot(x1 - x0, y1 - y0))
    return acc


def _at(path, acc, s):
    s = max(0.0, min(s, acc[-1]))
    lo, hi = 0, len(acc) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if acc[mid] <= s:
            lo = mid
        else:
            hi = mid
    seg = acc[hi] - acc[lo] or 1
    u = (s - acc[lo]) / seg
    (x0, y0), (x1, y1) = path[lo], path[hi]
    return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, math.atan2(y1 - y0, x1 - x0)


def _trail(d, path, acc, s0, s1, ox, dash=30, gap=22, width=11):
    """Dashes along the path from arc length s0 to s1, shifted by -ox (slide origin)."""
    s = s0 - (s0 % (dash + gap))
    while s < s1:
        a, b = max(s, s0), min(s + dash, s1)
        if b > a:
            pts = []
            steps = max(2, int((b - a) / 4))
            for i in range(steps + 1):
                x, y, _ = _at(path, acc, a + (b - a) * i / steps)
                pts.append(((x - ox) * SS, y * SS))
            d.line(pts, fill=TRAIL + (255,), width=width * SS, joint="curve")
            for p in (pts[0], pts[-1]):
                r = width * SS / 2
                d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=TRAIL + (255,))
        s += dash + gap


def _dove(sprite, angle, bob):
    deg = max(-24, min(24, -math.degrees(angle)))
    im = sprite.rotate(deg, resample=Image.BICUBIC, expand=True)
    return im, bob


def _paste(base, over, x, y):
    """alpha_composite that tolerates a sprite hanging off any edge."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(base.width, x + over.width), min(base.height, y + over.height)
    if x1 <= x0 or y1 <= y0:
        return
    base.alpha_composite(over.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def _encode(frames_iter, out_mp4):
    os.makedirs(os.path.dirname(os.path.abspath(out_mp4)), exist_ok=True)
    proc = subprocess.Popen([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{c.W}x{c.H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                             "-crf", "17", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                             "-color_trc", "bt709", "-movflags", "+faststart", out_mp4], stdin=subprocess.PIPE)
    for f in frames_iter:
        proc.stdin.write(f.convert("RGB").tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed on " + out_mp4)
    return out_mp4


def render(out_dir, slides_text, path_points, land_hold=1.6, sprite_name="dove-up"):
    """slides_text: one callable per slide, f(draw, image) that sets that slide's words.
    path_points: control points across the whole strip (len(slides_text) * 1080 wide)."""
    n = len(slides_text)
    sprite = Image.open(os.path.join(c.ART_DIR, f"{sprite_name}.png")).convert("RGBA")
    sprite = sprite.resize((DOVE_W, int(DOVE_W * sprite.height / sprite.width)), Image.LANCZOS)
    path = _catmull(path_points)
    acc = _arclen(path)
    total = acc[-1]
    # where the path first crosses each seam
    seams = []
    for k in range(1, n):
        x_seam = k * c.W
        s_cross = next(acc[i] for i in range(1, len(path)) if path[i - 1][0] < x_seam <= path[i][0])
        seams.append(s_cross)
    bounds = [0.0] + seams + [total]
    grounds = []
    for k in range(n):
        g = c.paper(seed=70 + k)
        slides_text[k](ImageDraw.Draw(g), g)
        grounds.append(g)
    outs = []
    for k in range(n):
        s_start = 0.0 if k == 0 else bounds[k] - EXIT
        s_end = total if k == n - 1 else bounds[k + 1] + EXIT
        fly = int(math.ceil((s_end - s_start) / SPEED * FPS))
        hold = int(land_hold * FPS) if k == n - 1 else 0
        frames = max(fly + hold, 3 * FPS + 2)
        ox = k * c.W

        def gen(k=k, s_start=s_start, s_end=s_end, fly=fly, ox=ox, frames=frames):
            for f in range(frames):
                u = min(1.0, f / max(1, fly - 1))
                s = s_start + (s_end - s_start) * u
                im = grounds[k].copy()
                lay = Image.new("RGBA", (c.W * SS, c.H * SS), (0, 0, 0, 0))
                _trail(ImageDraw.Draw(lay), path, acc, max(s_start, 0.0) if k else 0.0, max(0.0, s - DOVE_W * 0.42), ox)
                im.alpha_composite(lay.resize((c.W, c.H), Image.LANCZOS))
                x, y, ang = _at(path, acc, s)
                bob = math.sin(f / FPS * 2 * math.pi * 1.6) * 7
                dv, _ = _dove(sprite, ang if u < 1 else 0.0, bob)
                sh = Image.new("RGBA", dv.size, (40, 28, 12, 0))
                sh.putalpha(dv.split()[3].point(lambda v: int(v * 0.22)).filter(ImageFilter.GaussianBlur(10)))
                px, py = int(x - ox - dv.width / 2), int(y + bob - dv.height / 2)
                _paste(im, sh, px + 8, py + 16)
                _paste(im, dv, px, py)
                yield im

        outs.append(_encode(gen(), os.path.join(out_dir, f"{k + 1}.mp4")))
        # a still of the slide's first frame, for previews
        first = next(gen())
        c.save(first, os.path.join(out_dir, f"{k + 1}.jpg"))
    return outs


def _verse_layout(text):
    size, lines = c.fit(text, "serif-sb", c.W - 2 * 84, 520, 88, 46, leading=1.28)
    return size, lines, 150 + len(lines) * size * 1.28


def render_blessing(out_dir, hook, slides, ref, cta):
    """A blessing passage, one verse per slide after a hook slide; the dove
    loops and waves through the slides and lands beside the last words."""
    n = 1 + len(slides)

    def draw_hook(d, im):
        f = c.font("serif-b", 92)
        d.text((78, 214), hook[0], font=f, fill=c.INK, anchor="ls")
        d.text((78, 324), hook[1], font=f, fill=c.INK, anchor="ls")
        d.text((84, 432), "follow the dove  >>>", font=c.font("hand-b", 60), fill=c.GOLD, anchor="ls")
        wm = c.wordmark("black", 150, 0.34)
        im.alpha_composite(wm, (c.W - 84 - wm.width, 70))

    def draw_verse(text, last):
        def draw(d, im):
            size, lines, bottom = _verse_layout(text)
            f = c.font("serif-sb", size)
            end = c.text_block(d, lines, f, 84, 150, size * 1.28, c.INK, align="left")
            if last:
                c.draw_tracked(d, (86, end + 62), ref.upper(), c.font("sans-sb", 32), c.GOLD, 3.0)
                d.text((84, c.H - 92), cta, font=c.font("hand-b", 58), fill=c.GOLD, anchor="ls")
        return draw

    drawers = [draw_hook] + [draw_verse(t, k == len(slides) - 1) for k, t in enumerate(slides)]
    last_bottom = _verse_layout(slides[-1])[2] + 70
    land_y = max(820, min(1040, last_bottom + 230))
    pts = [(230, 880), (520, 790), (820, 900)]
    for k in range(1, n):
        x0 = k * c.W
        if k == n - 1:
            pts += [(x0 + 120, 990), (x0 + 380, 1070), (x0 + 620, 980), (x0 + 800, land_y)]
        elif k % 2 == 1:
            pts += [(x0 + 270, 900), (x0 + 480, 1030), (x0 + 680, 1000), (x0 + 760, 860), (x0 + 650, 760),
                    (x0 + 520, 830), (x0 + 530, 960), (x0 + 680, 1050), (x0 + 900, 990)]
        else:
            pts += [(x0 + 250, 960), (x0 + 520, 1080), (x0 + 780, 990)]
    return render(out_dir, drawers, pts)
