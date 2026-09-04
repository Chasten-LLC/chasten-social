#!/usr/bin/env python3
"""Lay every narrative set out as one page of thumbnails.

The audit catches faces, anachronism, distortion and scale. It does not reliably
catch an image that is beautiful but tells the wrong story, so the last gate is a
person looking at all of them at once. Two sets per row keeps the page a shape a
human will actually scroll through.
"""
import hashlib, json, os, sys
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = os.path.join(REPO, ".sweep")
SERIF = os.path.join(REPO, "tools/assets/fonts/Inter_600SemiBold.ttf")
TW, TH, GAP, LAB, PAD, COLS = 180, 320, 6, 26, 16, 2
BLOCK = 3 * TW + 2 * GAP
ROWH = LAB + TH + PAD

report = json.load(open(os.path.join(WORK, "report.json")))
sets = {s["title"]: s for s in
        json.load(open(os.path.join(REPO, "studio/verses/sets.json")))["sets"]}
titles = sorted(t for t in report if report[t]["verdict"] == "viable") or sorted(report)

rows = (len(titles) + COLS - 1) // COLS
W = PAD + COLS * (BLOCK + PAD)
sheet = Image.new("RGB", (W, PAD + rows * ROWH), (16, 16, 18))
d = ImageDraw.Draw(sheet)
ft = ImageFont.truetype(SERIF, 15)
fs = ImageFont.truetype(SERIF, 12)

for i, title in enumerate(titles):
    cx = PAD + (i % COLS) * (BLOCK + PAD)
    cy = PAD + (i // COLS) * ROWH
    d.text((cx, cy + 3), title, font=ft, fill=(240, 238, 232))
    s = sets[title]
    refs = ", ".join(v["ref"] for v in s["verses"][:s.get("verseCount", 1)])
    d.text((cx + d.textlength(title, font=ft) + 12, cy + 5), refs, font=fs,
           fill=(138, 136, 130))
    slug = "".join(c if c.isalnum() else "-" for c in title)[:28]
    for k in range(1, 4):
        h = hashlib.md5(s["scenes"][k - 1].encode()).hexdigest()[:6]
        x = cx + (k - 1) * (TW + GAP)
        y = cy + LAB
        cands = sorted(f for f in os.listdir(WORK) if f.startswith(f"{slug}-{k}-{h}-"))
        if not cands:
            d.rectangle((x, y, x + TW, y + TH), outline=(70, 50, 50))
            d.text((x + 8, y + 8), "not generated", font=fs, fill=(170, 90, 90))
            continue
        # The audit stops at the first roll that passes, so the last file on disk
        # for a beat is the one it accepted.
        im = Image.open(os.path.join(WORK, cands[-1])).convert("RGB").resize(
            (TW, TH), Image.LANCZOS)
        sheet.paste(im, (x, y))
        d.text((x + 6, y + TH - 17), f"{k}", font=fs, fill=(255, 255, 255))

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "contact-sheet.jpg")
sheet.save(out, quality=84)
print(f"{out}  {sheet.size[0]}x{sheet.size[1]}  {os.path.getsize(out)//1024}KB  {len(titles)} sets")
