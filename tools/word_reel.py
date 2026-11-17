#!/usr/bin/env python3
"""
The daily word reel's posting side: what the cloud routine runs each morning around
tools/word_render.py (docs/word-routine-prompt.md).

Each morning at 7 AM Central the routine makes today's reel from the app's own bank
(`word_render.py today`), which refuses a reel that fails any of its measured checks, then
puts the reel, its cover, its caption and its record in word/<date>/, posts it once, and
leaves word/<date>/post.json for Slack. Ric decided on 2026-11-17 that reels run every
day the app has a verse and word for, with no approval step.

    python3 tools/word_reel.py switch  [--date D --ios N --android M]   # read, or turn on once
    python3 tools/word_reel.py status  --date D      # posted | switch-off | fresh
    python3 tools/word_reel.py media   --date D      # the public video and cover URLs and the caption, as JSON
    python3 tools/word_reel.py package --date D --status posted|failed [--permalink U] [--media-id I] [--note T]

The switch (Ric, 2026-11-10): reels start by themselves once readers have the app's new Today
cards. The routine counts production readers who sent `today_verse_cards_shown` on iPhone and
on Android; the first morning both are above zero, `switch` writes studio/state/word-switch.json
and it never turns off again.

Standard library only.
"""

import datetime as dt
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD = os.path.join(ROOT, "word")
CALENDAR = os.path.join(WORD, "calendar.json")      # {date: reference} ahead, for tools/verses.py
SWITCH = os.path.join(ROOT, "studio", "state", "word-switch.json")
RAW = "https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main"

SHARE_LINES = ["Send this to someone who loves the Word.", "Save this and say it with us.",
               "Share it with a friend who is reading along."]
SIGN_OFF = "\U0001F56F️ A new word every morning in Chasten, a free Bible app. chasten.ai"


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ the caption

def caption(r, date):
    """The caption, written from the bank alone. The verse is the BSB's own text, whole; every
    other line is about the word and says only what the card in the app says."""
    hebrew = r["lang"] == "hebrew"
    lang = "Hebrew" if hebrew else "Greek"
    said = "-".join(r["say"])
    how = (f"Said the way it is spoken in Israel today: {said}. Hebrew reads right to left." if hebrew
           else f"Said the way Greeks say it today: {said}.")
    share = SHARE_LINES[dt.date.fromisoformat(date).toordinal() % len(SHARE_LINES)]
    return "\n\n".join([
        f"The {lang} word behind “{r['mark']}” in {r['ref']}.",
        f"{r['word']} ({r['roman']}): “{r['gloss']}.” {r['more']}",
        f"{r['ref']} (BSB): {r['verse']}",
        how,
        f"{share}\n{SIGN_OFF}\n#bibleverse #faith #biblestudy #{lang.lower()}",
    ])


def caption_problems(text, r):
    out = []
    if "—" in text:
        out.append("an em dash")
    ours = text.replace(r.get("verse", ""), "").replace(r.get("more", ""), "")   # Scripture and the bank keep their own marks
    if "!" in ours:
        out.append("an exclamation mark in our own words")
    if len(text) > 1200:
        out.append(f"{len(text)} characters, over 1,200")
    first = text.split("\n", 1)[0]
    if len(first) >= 110:
        out.append(f"line 1 is {len(first)} characters; Instagram cuts at about 110")
    if f"{r['ref']} (BSB): {r['verse']}" not in text:
        out.append("the verse is not there word for word")
    tags = text.rstrip().split("\n")[-1].split()
    if not 3 <= len(tags) <= 5 or not all(t.startswith("#") and t == t.lower() for t in tags):
        out.append("the last line is not three to five lowercase hashtags")
    return out


# ------------------------------------------------------------------ the routine's steps

def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def switch_state():
    return _load(SWITCH, {"on": False})


def cmd_switch(argv):
    st = switch_state()
    if st.get("on") or "--date" not in argv:
        print(json.dumps(st))
        return 0
    ios, android = int(arg(argv, "--ios", 0)), int(arg(argv, "--android", 0))
    if ios > 0 and android > 0:
        st = {"on": True, "since": arg(argv, "--date"), "ios": ios, "android": android,
              "why": "production readers on both platforms sent today_verse_cards_shown"}
        _dump(SWITCH, st)
        print(json.dumps(dict(st, changed=True)))
    else:
        print(json.dumps(dict(st, ios=ios, android=android)))
    return 0


def day_dir(date):
    return os.path.join(WORD, date)


def cmd_status(argv):
    date = arg(argv, "--date")
    rec = _load(os.path.join(day_dir(date), "post.json"), {})
    if rec.get("status") == "posted":
        s = "posted"
    elif not switch_state().get("on"):
        s = "switch-off"
    else:
        s = "fresh"
    print(json.dumps({"status": s, "ref": rec.get("ref"), "permalink": rec.get("permalink")}))
    return 0


def cmd_media(argv):
    """The public URLs, only for a reel whose file is the one its record was checked as."""
    date = arg(argv, "--date")
    d = day_dir(date)
    rec = _load(os.path.join(d, "reel.json"), {})
    mp4, jpg, cap = (os.path.join(d, x) for x in ("reel.mp4", "cover.jpg", "caption.txt"))
    if not rec or rec.get("fails") or not all(os.path.exists(x) for x in (mp4, jpg, cap)):
        print(json.dumps({"status": "not-ready", "why": "the reel, its cover, caption or record is missing, or it failed a check"}))
        return 1
    if sha256(mp4) != rec["sha256"]:
        print(json.dumps({"status": "not-ready", "why": "reel.mp4 is not the file that passed the checks"}))
        return 1
    print(json.dumps({"status": "ready", "video_url": f"{RAW}/word/{date}/reel.mp4", "cover_url": f"{RAW}/word/{date}/cover.jpg",
                      "caption": open(cap, encoding="utf-8").read()}, ensure_ascii=False))
    return 0


def cmd_package(argv):
    date, status = arg(argv, "--date"), arg(argv, "--status")
    if status not in ("posted", "failed"):
        raise SystemExit("--status is posted or failed")
    path = os.path.join(day_dir(date), "post.json")
    if _load(path, {}).get("status") == "posted":
        raise SystemExit(f"{date} is already posted; the record stays as it is")
    r = _load(os.path.join(day_dir(date), "reel.json"), {})
    rec = {"date": date, "kind": "word-reel", "status": status, "id": r.get("id"), "ref": r.get("ref"),
           "refs": [r["ref"]] if r.get("ref") else [], "word": r.get("word"), "roman": r.get("roman"),
           "lang": r.get("lang"), "app": r.get("app"), "permalink": arg(argv, "--permalink"),
           "mediaId": arg(argv, "--media-id"), "note": arg(argv, "--note")}
    _dump(path, {k: v for k, v in rec.items() if v is not None})
    print(path)
    return 0


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    sys.exit({"switch": cmd_switch, "status": cmd_status, "media": cmd_media, "package": cmd_package}[cmd](rest))
