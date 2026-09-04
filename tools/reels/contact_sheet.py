#!/usr/bin/env python3
"""Lay every narrative set out as one page of thumbnails.

The audit catches faces, anachronism and distortion. It does not reliably catch an
image that is beautiful but tells the wrong story, so the last check is a person
looking at all of them at once.
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = os.path.join(REPO, ".sweep")
FONT = os.path.join(REPO, "tools/assets/fonts/Inter_600SemiBold.ttf")
TW, TH, PAD, LAB = 210, 373, 12, 26          # 9:16 thumbnails

report = json.load(open(os.path.join(WORK, "report.json")))
sets = {s["title"]: s for s in
        json.load(open(os.path.join(REPO, "studio/verses/sets.json")))["sets"]}
titles = [t for t in report if report[t]["verdict"] == "viable"] or list(report)

cols = 3
rows = len(titles)
W = PAD + cols * (TW + PAD)
RH = LAB + TH + PAD
sheet = Image.new("RGB", (W, PAD + rows * RH), (18, 18, 20))
d = ImageDraw.Draw(sheet)
f = ImageFont.truetype(FONT, 15)
fs = ImageFont.truetype(FONT, 12)

for r, title in enumerate(titles):
    y = PAD + r * RH
    d.text((PAD, y + 4), title, font=f, fill=(238, 236, 230))
    refs = ", ".join(v["ref"] for v in sets[title]["verses"][:sets[title].get("verseCount", 1)])
    d.text((PAD + d.textlength(title, font=f) + 14, y + 6), refs, font=fs, fill=(140, 138, 132))
    slug = "".join(c if c.isalnum() else "-" for c in title)[:28]
    for k in range(1, 4):
        x = PAD + (k - 1) * (TW + PAD)
        box = (x, y + LAB, x + TW, y + LAB + TH)
        # Show the roll the audit actually accepted, which is the last one on disk.
        cands = sorted(f2 for f2 in os.listdir(WORK) if f2.startswith(f"{slug}-{k}-"))
        if not cands:
            d.rectangle(box, outline=(60, 58, 56))
            d.text((x + 8, y + LAB + 8), "none", font=fs, fill=(120, 60, 60))
            continue
        im = Image.open(os.path.join(WORK, cands[-1])).convert("RGB")
        im = im.resize((TW, TH), Image.LANCZOS)
        sheet.paste(im, (x, y + LAB))
        d.text((x + 6, y + LAB + TH - 18), f"beat {k}", font=fs, fill=(255, 255, 255))

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "contact-sheet.jpg")
sheet.save(out, quality=86)
print(f"{out}  {sheet.size[0]}x{sheet.size[1]}  {os.path.getsize(out)//1024}KB  {len(titles)} sets")
