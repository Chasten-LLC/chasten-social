#!/usr/bin/env python3
"""
Add photos to the Instagram background pool, cut for Instagram.

    python3 tools/add_backgrounds.py SOURCE_DIR [--tag NAME] [--dry-run]

Every card is 1080x1350 (4:5, the tallest shape the Instagram API publishes
in a carousel), so each photo is cut to exactly that once, here, instead of
centre-cropped at render time. The cut keeps the part of the photo with the
most going on (detail and colour), leaning gently toward the middle, so a
cross off to one side or a bloom low in the frame stays in the card.

For each photo it writes studio/bg/<id>.jpg and a manifest entry in
studio/library/backgrounds.json with the fields the renderer reads:
  ink    the verse colour, a warm white or a deep brown tinted by the photo
  light  true when the ink is light (then the scrim is dark)
  scrim  "dark" behind light ink, "light" behind dark ink
  credit the Pexels photographer from the file name (no attribution needed)
  dim    an extra veil (0 to 0.3) for light ink over a busy photo or one with
         big bright patches, so the verse never fights what is behind it
The id is the Pexels photo id at the end of the file name. A photo already in
the pool is skipped, so rerunning is safe.
"""

import colorsys
import json
import os
import re
import sys

from PIL import Image, ImageFilter, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG = os.path.join(ROOT, "studio", "bg")
MANIFEST = os.path.join(ROOT, "studio", "library", "backgrounds.json")
W, H = 1080, 1350
LIGHT_INK, DARK_INK = (250, 243, 236), (63, 46, 34)

# Where to centre the cut when detail and colour pick the wrong part: a cross
# at the edge of a sky full of busy clouds. Fraction of the photo's width.
FOCUS_X = {"10807887": 0.45}


def saliency_profile(im, horizontal):
    """How much is going on along the axis the crop window slides on."""
    small = im.copy()
    small.thumbnail((360, 360))
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES)
    sat = small.convert("HSV").getchannel("S")
    w, h = small.size
    e, s = edges.load(), sat.load()
    if horizontal:
        return [sum(0.65 * e[x, y] + 0.35 * s[x, y] for y in range(h)) for x in range(w)], w
    return [sum(0.65 * e[x, y] + 0.35 * s[x, y] for x in range(w)) for y in range(h)], h


def best_window(profile, window):
    """Start of the window with the most saliency, with a gentle pull to the middle."""
    n = len(profile)
    if window >= n:
        return 0
    total = sum(profile) or 1.0
    run = sum(profile[:window])
    best, best_at = None, 0
    middle = (n - window) / 2
    for start in range(0, n - window + 1):
        if start:
            run += profile[start + window - 1] - profile[start - 1]
        score = run / total - 0.25 * abs(start - middle) / n
        if best is None or score > best:
            best, best_at = score, start
    return best_at


def cut(im, focus_x=None):
    """Exactly W x H from the most eventful part of the photo."""
    im = im.convert("RGB")
    sw, sh = im.size
    target = W / H
    if sw / sh > target:  # wider than 4:5: slide across
        profile, n = saliency_profile(im, True)
        window = round(n * (sh * target / sw))
        x = round(best_window(profile, window) * sw / n)
        if focus_x is not None:
            x = round(min(max(focus_x * sw - sh * target / 2, 0), sw - sh * target))
        box = (x, 0, min(sw, x + round(sh * target)), sh)
    else:  # taller than 4:5: slide down
        profile, n = saliency_profile(im, False)
        window = round(n * (sw / target / sh))
        y = round(best_window(profile, window) * sh / n)
        box = (0, y, sw, min(sh, y + round(sw / target)))
    return im.crop(box).resize((W, H), Image.LANCZOS)


def verse_band(card):
    """Where the verse sits (the middle of the card), in grey, small."""
    return card.convert("L").crop((80, round(H * 0.22), W - 80, round(H * 0.78))).resize((460, 380))


def band_stats(card):
    """Brightness, busyness (edge strength), contrast, and the share of the
    verse area bright enough (190+) to swallow white letters."""
    band = verse_band(card)
    lum = ImageStat.Stat(band).mean[0]
    busy = ImageStat.Stat(band.filter(ImageFilter.FIND_EDGES)).mean[0]
    contrast = ImageStat.Stat(band).stddev[0]
    hist = band.histogram()
    bright = sum(hist[190:]) / sum(hist)
    return lum, busy, contrast, bright


def tint(base, color, amount):
    return "#%02X%02X%02X" % tuple(round(b + (c - b) * amount) for b, c in zip(base, color))


def dress(card):
    """Ink, light and scrim for this card, the way the existing pool is set."""
    lum, busy, contrast, bright = band_stats(card)
    avg = tuple(round(v) for v in ImageStat.Stat(card.resize((32, 40))).mean)
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in avg))
    hue = tuple(round(v * 255) for v in colorsys.hls_to_rgb(h, 0.5, min(1.0, s + 0.2)))
    # Busy and colourful photos read best as light ink on a dark veil; only a
    # truly bright middle takes dark ink on a light veil.
    if lum > 175:
        return {"ink": tint(DARK_INK, hue, 0.08), "light": False, "scrim": "light", "dim": 0.0}
    # Light ink: add a veil when the photo is busy, very uneven, or has big
    # bright patches where white letters would disappear.
    dim = 0.0
    if busy > 24 or contrast > 60:
        dim = 0.12 + max(0.0, busy - 24) * 0.008 + max(0.0, contrast - 60) * 0.004
    if bright >= 0.10:
        dim = max(dim, 0.15 + (bright - 0.10) * 0.5)
    return {"ink": tint(LIGHT_INK, hue, 0.05), "light": True, "scrim": "dark", "dim": round(min(dim, 0.3), 2)}


def credit_of(name):
    m = re.match(r"pexels-(.+)-(\d+)$", name)
    slug = m.group(1) if m else ""
    if not slug or re.fullmatch(r"[\d-]+", slug):
        return "Pexels"
    words = [w for w in slug.split("-") if not w.isdigit()]
    return " ".join(w.capitalize() for w in words) or "Pexels"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    source = args[0]
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "app-votd"
    dry = "--dry-run" in sys.argv
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    have = {item["id"] for item in manifest["items"]}
    added = []
    for name in sorted(os.listdir(source)):
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        stem = os.path.splitext(name)[0]
        m = re.search(r"(\d+)$", stem)
        if not m:
            print("skip (no photo id):", name)
            continue
        pid = m.group(1)
        if pid in have:
            continue
        im = Image.open(os.path.join(source, name))
        im.draft("RGB", (2400, 2400))
        card = cut(im, FOCUS_X.get(pid))
        item = dict(sorted({"id": pid, "credit": credit_of(stem), "desc": f"App Verse of the Day photo ({tag})",
                            "parts": 1, "query": tag, **dress(card)}.items()))
        added.append(item)
        have.add(pid)
        if not dry:
            card.save(os.path.join(BG, f"{pid}.jpg"), quality=86, optimize=True, progressive=True)
        print(f"{pid:>10}  {item['ink']}  {'light ink' if item['light'] else 'dark ink '}  dim {item['dim']:.2f}  {item['credit']}")
    if not dry and added:
        manifest["items"].extend(added)
        manifest["count"] = len(manifest["items"])
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(added)} added{' (dry run)' if dry else ''}; pool now {len(have)}")


if __name__ == "__main__":
    main()
