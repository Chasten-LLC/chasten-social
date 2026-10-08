#!/usr/bin/env python3
"""
Checks every verse in the 7 AM pools (studio/morning/*.json) against the app's
bundled BSB (../chasten-bible-app/assets/bible/bible.db), word for word.

    python3 tools/check_morning.py [--db PATH]

The pools hold the exact text the cloud routine sets in type, because the
routine has no Bible database of its own. So the rule is strict: an entry's
text must equal the verse (or the verses of its range, joined by one space)
exactly, except that a quotation mark left dangling at either end, because the
verse is lifted out of a longer speech, is dropped. Scripture text may never
hold an em dash, so verses that contain one are left out of the pools.

Format rules, enforced here as well:
  - whole sentences: an entry starts with a capital letter and ends with . ! or ?
    (the dove's middle slides may continue a sentence across slides);
  - a word limit per format, so every verse fits its layout at a readable size;
  - every icon the Follow the Line answers use exists, and every colour is a hue.
Run it after editing a pool, and before committing. It exits 1 on any problem.
"""

import json
import os
import re
import sqlite3
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
POOLS = os.path.join(ROOT, "studio", "morning")
DB = os.path.join(os.path.dirname(ROOT), "chasten-bible-app", "assets", "bible", "bible.db")

BOOKS = {
    "Genesis": "GEN", "Exodus": "EXO", "Numbers": "NUM", "Deuteronomy": "DEU", "Joshua": "JOS", "Ruth": "RUT",
    "Psalm": "PSA", "Psalms": "PSA", "Proverbs": "PRO", "Ecclesiastes": "ECC", "Song of Songs": "SNG",
    "Isaiah": "ISA", "Jeremiah": "JER", "Lamentations": "LAM", "Micah": "MIC", "Nahum": "NAM", "Habakkuk": "HAB",
    "Zephaniah": "ZEP", "Malachi": "MAL", "Matthew": "MAT", "Mark": "MRK", "Luke": "LUK", "John": "JHN",
    "Acts": "ACT", "Romans": "ROM", "1 Corinthians": "1CO", "2 Corinthians": "2CO", "Galatians": "GAL",
    "Ephesians": "EPH", "Philippians": "PHP", "Colossians": "COL", "1 Thessalonians": "1TH",
    "2 Thessalonians": "2TH", "1 Timothy": "1TI", "2 Timothy": "2TI", "Hebrews": "HEB", "James": "JAS",
    "1 Peter": "1PE", "1 John": "1JN", "Jude": "JUD",
}
LIMITS = {"monday": 22, "tuesday": 32, "wednesday": 32, "friday": 30, "reel": 30, "sunday": 34}
HUES = {"gold", "clay", "heart", "plum", "teal", "blue", "green"}
EM_DASH = "—"


def clean(t):
    """Drop a quotation mark left dangling at either end; nothing else changes."""
    t = t.strip()
    for o, c in (("“", "”"), ("‘", "’")):
        if t.endswith(c) and t.count(o) < t.count(c):
            t = t[:-1].rstrip()
        if t.startswith(o) and t.count(o) > t.count(c):
            t = t[1:].lstrip()
    return t


def whole_sentence(t):
    core = t.lstrip("\u201c\u2018")
    return core[:1].isupper() and re.search(r"[.!?][\u201d\u2019]?$", t) is not None


class Bible:
    def __init__(self, path):
        if not os.path.exists(path):
            raise SystemExit(f"no Bible database at {path} (pass --db)")
        self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    def verses(self, ref):
        m = re.match(r"^(.+?) (\d+):(\d+)(?:-(\d+))?$", ref)
        if not m or m.group(1) not in BOOKS:
            return None
        book, ch, a, b = BOOKS[m.group(1)], int(m.group(2)), int(m.group(3)), int(m.group(4) or m.group(3))
        rows = self.con.execute(
            "select v.text from verses v join books b on b.book_id = v.book_id where v.translation_id = 'BSB' "
            "and b.usfm_code = ? and v.chapter = ? and v.verse between ? and ? order by v.verse",
            (book, ch, a, b)).fetchall()
        return [r[0] for r in rows] if len(rows) == b - a + 1 else None


def main():
    db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else DB
    bible = Bible(db)
    problems, checked = [], 0

    def verse(where, ref, text, limit, whole=True):
        nonlocal checked
        checked += 1
        vs = bible.verses(ref)
        if vs is None:
            problems.append(f"{where}: {ref} is not a BSB reference")
            return
        want = clean(" ".join(vs))
        if text != want:
            problems.append(f"{where}: text differs from {ref}\n    pool:  {text}\n    BSB:   {want}")
        if EM_DASH in text:
            problems.append(f"{where}: {ref} holds an em dash; leave it out of the pools")
        if len(text.split()) > limit:
            problems.append(f"{where}: {ref} has {len(text.split())} words, over this format's {limit}")
        if whole and not whole_sentence(text):
            problems.append(f"{where}: {ref} is not a whole sentence")

    def load(name):
        return json.load(open(os.path.join(POOLS, name), encoding="utf-8"))

    for m in load("monday.json")["moments"]:
        verse(f"monday {m['id']}", m["ref"], m["text"], LIMITS["monday"])
        if m["layout"] not in ("left", "right", "top", "bottom", "center"):
            problems.append(f"monday {m['id']}: unknown layout {m['layout']}")
    for s in load("tuesday.json")["sets"]:
        if len(s["answers"]) != 4:
            problems.append(f"tuesday {s['id']}: needs four answers")
        for a in s["answers"]:
            verse(f"tuesday {s['id']}/{a['label']}", a["ref"], a["text"], LIMITS["tuesday"])
            if not os.path.exists(os.path.join(TOOLS, "assets", "icons", f"{a['icon']}.png")):
                problems.append(f"tuesday {s['id']}/{a['label']}: no icon {a['icon']}")
            if a["color"] not in HUES:
                problems.append(f"tuesday {s['id']}/{a['label']}: {a['color']} is not one of the app's hues")
    for e in load("wednesday.json")["entries"]:
        verse(f"wednesday {e['ref']}", e["ref"], e["text"], LIMITS["wednesday"])
    for e in load("friday.json")["entries"]:
        verse(f"friday {e['ref']}", e["ref"], e["text"], LIMITS["friday"])
    for e in load("reel.json")["verses"]:
        verse(f"reel {e['ref']}", e["ref"], e["text"], LIMITS["reel"])
    for bl in load("sunday.json")["blessings"]:
        vs = bible.verses(bl["ref"])
        if vs is None or len(vs) != len(bl["slides"]):
            problems.append(f"sunday {bl['ref']}: needs one slide per verse")
            continue
        for k, text in enumerate(bl["slides"]):
            checked += 1
            if text != clean(vs[k]):
                problems.append(f"sunday {bl['ref']} slide {k + 1}: differs from its verse\n    pool: {text}\n    BSB:  {clean(vs[k])}")
            if EM_DASH in text:
                problems.append(f"sunday {bl['ref']} slide {k + 1}: em dash")
            if len(text.split()) > LIMITS["sunday"]:
                problems.append(f"sunday {bl['ref']} slide {k + 1}: {len(text.split())} words, over {LIMITS['sunday']}")
        if not bl["slides"][0].lstrip("\u201c\u2018")[:1].isupper() or not re.search(r"[.!?][\u201d\u2019]?$", bl["slides"][-1]):
            problems.append(f"sunday {bl['ref']}: the passage must start and end a sentence")

    for p in problems:
        print(p)
    print(f"{checked} verses checked, {len(problems)} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
