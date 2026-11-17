#!/usr/bin/env python3
"""
The daily word reel's posting side: what the cloud routine runs each morning (docs/word-routine-prompt.md).

The reels are made ahead on a Mac in a monthly batch (tools/word_render.py) and Ric approves
them; approval copies each one into word/reels/ and marks its day in word/schedule.json. This
file only reads that schedule. It never renders and never changes a reel.

    python3 tools/word_reel.py switch  [--date D --ios N --android M]   # read, or turn on once
    python3 tools/word_reel.py status  --date D      # posted | switch-off | missing | unapproved | broken | ready
    python3 tools/word_reel.py media   --date D      # the public video and cover URLs and the caption, as JSON
    python3 tools/word_reel.py package --date D --status posted|failed|skipped [--permalink U] [--media-id I] [--note T]
    python3 tools/word_reel.py caption-check --date D

The switch (Ric, 2026-11-10): reels start by themselves once readers have the app's new Today
cards. The routine counts production readers who sent `today_verse_cards_shown` on iPhone and
on Android; the first morning both are above zero, `switch` writes studio/state/word-switch.json
and it never turns off again.

Standard library only: the cloud sandbox needs nothing installed to post.
"""

import datetime as dt
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REELS = "word/reels"
SCHEDULE = os.path.join(ROOT, "word", "schedule.json")
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


def load_schedule():
    return _load(SCHEDULE, {"days": {}})


def save_schedule(s):
    s["days"] = dict(sorted(s["days"].items()))
    _dump(SCHEDULE, s)


def reel_name(entry_id, sha):
    """A reel's file name never changes once posted: the entry and the start of its hash."""
    return f"{entry_id}.{sha[:8]}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ the caption

def caption(r, date):
    """The caption, written from the bank alone so Ric approves it with the reel. The verse is
    the BSB's own text, whole; every other line is about the word and says only what the card
    in the app says."""
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


def day_record(date):
    return os.path.join(ROOT, "word", date, "post.json")


def status_of(date):
    rec = _load(day_record(date), {})
    if rec.get("status") == "posted":
        return "posted", rec
    if not switch_state().get("on"):
        return "switch-off", {}
    day = load_schedule()["days"].get(date)
    if not day:
        return "missing", {}
    if not day.get("approved"):
        return "unapproved", day
    path = os.path.join(ROOT, day["file"])
    if not os.path.exists(path) or sha256(path) != day["sha256"]:
        return "broken", day
    if not os.path.exists(os.path.join(ROOT, day["cover"])):
        return "broken", day
    return "ready", day


def cmd_status(argv):
    s, day = status_of(arg(argv, "--date"))
    print(json.dumps({"status": s, "id": day.get("id"), "ref": day.get("ref"), "permalink": day.get("permalink")}))
    return 0


def cmd_media(argv):
    date = arg(argv, "--date")
    s, day = status_of(date)
    if s != "ready":
        print(json.dumps({"status": s}))
        return 1
    print(json.dumps({"status": s, "video_url": f"{RAW}/{day['file']}", "cover_url": f"{RAW}/{day['cover']}",
                      "caption": day["caption"]}, ensure_ascii=False))
    return 0


def cmd_caption_check(argv):
    day = load_schedule()["days"].get(arg(argv, "--date"), {})
    if not day:
        print("no reel for this date")
        return 1
    r = dict(day, mark=day["caption"].split("“", 1)[1].split("”", 1)[0], more="")
    verse_line = [x for x in day["caption"].split("\n\n") if x.startswith(f"{day['ref']} (BSB): ")]
    r["verse"] = verse_line[0][len(f"{day['ref']} (BSB): "):] if verse_line else ""
    p = caption_problems(day["caption"], r)
    print("caption ok" if not p else "; ".join(p))
    return 1 if p else 0


def cmd_package(argv):
    date, status = arg(argv, "--date"), arg(argv, "--status")
    if status not in ("posted", "failed", "skipped"):
        raise SystemExit("--status is posted, failed or skipped")
    old = _load(day_record(date), {})
    if old.get("status") == "posted":
        raise SystemExit(f"{date} is already posted; the record stays as it is")
    day = load_schedule()["days"].get(date, {})
    rec = {"date": date, "kind": "word-reel", "status": status, "id": day.get("id"), "ref": day.get("ref"),
           "refs": [day["ref"]] if day.get("ref") else [], "word": day.get("word"), "roman": day.get("roman"),
           "lang": day.get("lang"), "file": day.get("file"), "permalink": arg(argv, "--permalink"),
           "mediaId": arg(argv, "--media-id"), "note": arg(argv, "--note")}
    _dump(day_record(date), {k: v for k, v in rec.items() if v is not None})
    print(day_record(date))
    return 0


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    sys.exit({"switch": cmd_switch, "status": cmd_status, "media": cmd_media, "package": cmd_package,
              "caption-check": cmd_caption_check}[cmd](rest))
