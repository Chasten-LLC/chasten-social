#!/usr/bin/env python3
"""
Check that every Scripture line in studio/world/lines.json is a word-for-word,
contiguous piece of its BSB verse, using the Chasten app's bundled Bible.

    python3 tools/check_world_lines.py [--db PATH]

PATH defaults to the app repo beside this one
(../chasten-bible-app/assets/bible/bible.db). Run it after adding lines; it
exits 1 and names each line that drifts from the text, the way the trivia
checker does in the app repo.
"""

import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(os.path.dirname(ROOT), "chasten-bible-app", "assets", "bible", "bible.db")


def flat(text):
    """Letters, digits and single spaces, lowercase: quotes and punctuation
    around a fragment may differ, the words and their order may not."""
    text = text.replace("’", "'").lower()
    return " ".join(re.findall(r"[a-z0-9']+", text))


def main():
    db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else DB
    lines = json.load(open(os.path.join(ROOT, "studio", "world", "lines.json"), encoding="utf-8"))["lines"]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    bad = 0
    for line in lines:
        if line.get("kind") != "verse":
            continue
        code, cv = line["verse"].split(" ")
        chapter, verse = (int(x) for x in cv.split(":"))
        row = con.execute(
            "select v.text from verses v join books b on b.book_id = v.book_id "
            "where v.translation_id = 'BSB' and b.usfm_code = ? and v.chapter = ? and v.verse = ?",
            (code, chapter, verse)).fetchone()
        if not row:
            print(f"{line['id']}: no BSB verse {line['verse']}")
            bad += 1
        elif flat(line["text"]) not in flat(row[0]):
            print(f"{line['id']}: not in {line['verse']}\n  line:  {line['text']}\n  verse: {row[0]}")
            bad += 1
    print(f"{len([l for l in lines if l.get('kind') == 'verse'])} lines checked, {bad} wrong")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
