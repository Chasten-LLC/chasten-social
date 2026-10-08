"""
What Chasten has already posted, verse by verse, so every planner keeps
Scripture fresh across both daily posts (Ric, 2026-10-08: "material should be
fresh as much as possible").

The rules every planner follows:
  - a verse never appears twice in one post (each planner picks distinct verses);
  - a verse never appears in both of a day's posts, a reel's verses included;
  - otherwise the verse that has rested longest goes first, and a verse never
    posted beats them all. A post Ric approved in advance holds its verse from
    the day it is staged, so nothing runs it a few days before.

The record is built from the posts' own records, so there is no second state
file to keep in step: posts/<date>/post.json (the old 7 AM), morning/<date>/
post.json (the 7 AM formats) and world/<date>/post.json (the 11 AM, world and
share). Only posts that went out count. A reel flashes 45 verses, so a reel
counts for its own day only; counting it for weeks would starve every pool.

    from verses import from_repo
    led = from_repo()
    led.rest(["Isaiah 41:10"], "2026-10-14")   # days to its nearest other post, 0 = today
"""

import datetime as dt
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEVER = 10 ** 6  # the rest of a verse never posted

BOOKS = {
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM", "Deuteronomy": "DEU",
    "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT", "1 Samuel": "1SA", "2 Samuel": "2SA",
    "1 Kings": "1KI", "2 Kings": "2KI", "1 Chronicles": "1CH", "2 Chronicles": "2CH", "Ezra": "EZR",
    "Nehemiah": "NEH", "Esther": "EST", "Job": "JOB", "Psalm": "PSA", "Psalms": "PSA", "Proverbs": "PRO",
    "Ecclesiastes": "ECC", "Song of Songs": "SNG", "Song of Solomon": "SNG", "Isaiah": "ISA",
    "Jeremiah": "JER", "Lamentations": "LAM", "Ezekiel": "EZK", "Daniel": "DAN", "Hosea": "HOS",
    "Joel": "JOL", "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON", "Micah": "MIC", "Nahum": "NAM",
    "Habakkuk": "HAB", "Zephaniah": "ZEP", "Haggai": "HAG", "Zechariah": "ZEC", "Malachi": "MAL",
    "Matthew": "MAT", "Mark": "MRK", "Luke": "LUK", "John": "JHN", "Acts": "ACT", "Romans": "ROM",
    "1 Corinthians": "1CO", "2 Corinthians": "2CO", "Galatians": "GAL", "Ephesians": "EPH",
    "Philippians": "PHP", "Colossians": "COL", "1 Thessalonians": "1TH", "2 Thessalonians": "2TH",
    "1 Timothy": "1TI", "2 Timothy": "2TI", "Titus": "TIT", "Philemon": "PHM", "Hebrews": "HEB",
    "James": "JAS", "1 Peter": "1PE", "2 Peter": "2PE", "1 John": "1JN", "2 John": "2JN",
    "3 John": "3JN", "Jude": "JUD", "Revelation": "REV",
}
CODES = set(BOOKS.values())
REF = re.compile(r"^(.+?) (\d+):(\d+)(?:-(?:(\d+):)?(\d+))?$")


def keys(ref):
    """Every verse a reference covers, as (book, chapter, verse): "Psalm 115:14-15" is two
    verses, "ROM 8:31" one. A reference that cannot be read keeps its own text as its key,
    so two identical ones still match."""
    m = REF.match((ref or "").strip())
    if not m:
        return {("?", ref, 0)}
    name, ch, v1, ch2, v2 = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
    book = BOOKS.get(name) or (name if name in CODES else None)
    if not book:
        return {("?", ref, 0)}
    if v2 is None:
        return {(book, ch, v1)}
    if ch2:  # across a chapter break: keep both ends, which is enough to match
        return {(book, ch, v1), (book, int(ch2), int(v2))}
    return {(book, ch, v) for v in range(v1, int(v2) + 1)}


def all_keys(refs):
    out = set()
    for r in refs:
        out |= keys(r)
    return out


class Ledger:
    def __init__(self):
        self.dates = {}       # verse -> dates a post (not a reel) carried it, or an approved one will
        self.reel_dates = {}  # verse -> dates a reel flashed it
        self.days = {}        # date -> every verse posted that day, reels included

    def copy(self):
        c = Ledger()
        c.dates = {k: set(v) for k, v in self.dates.items()}
        c.reel_dates = {k: set(v) for k, v in self.reel_dates.items()}
        c.days = {k: set(v) for k, v in self.days.items()}
        return c

    def add(self, date, refs, reel=False):
        ks = all_keys(refs)
        self.days.setdefault(date, set()).update(ks)
        book = self.reel_dates if reel else self.dates
        for k in ks:
            book.setdefault(k, set()).add(date)

    @staticmethod
    def _nearest(ks, book, today):
        t = dt.date.fromisoformat(today)
        best = NEVER
        for k in ks:
            for d in book.get(k, ()):
                if d != today:
                    best = min(best, abs((t - dt.date.fromisoformat(d)).days))
        return best

    def reel_rest(self, refs, today):
        """Days to the nearest reel that flashed any of these verses; NEVER if none did."""
        return self._nearest(all_keys(refs), self.reel_dates, today)

    def together(self, refs, today):
        """Days to the nearest other day all these verses went out together (this entry's
        own post, for a pool entry), NEVER if never."""
        ks = list(all_keys(refs))
        if not ks:
            return NEVER
        common = set.intersection(*(set(self.dates.get(k, ())) for k in ks))
        common.discard(today)
        t = dt.date.fromisoformat(today)
        return min((abs((t - dt.date.fromisoformat(d)).days) for d in common), default=NEVER)

    def rest(self, refs, today):
        """Days to the nearest other post of any of these verses, before or after today
        (an approved post waiting for its date counts); 0 when one is posted today, a
        reel's included; NEVER when none ever was."""
        ks = all_keys(refs)
        if ks & self.days.get(today, set()):
            return 0
        return self._nearest(ks, self.dates, today)


def freshest(entries, refs_of, today, ledger):
    """Today's entry from a weekly pool: the one that went out longest ago, so each runs
    once a cycle; never-posted ones first, in pool order. The order is fixed by the
    pool and its own posts, so the world post can see two weeks ahead and leave these
    verses alone (world_run.upcoming). An entry with a verse already posted today is
    taken only when every entry has one."""
    best, best_score = None, None
    for e in entries:
        refs = refs_of(e)
        score = (ledger.rest(refs, today) > 0, ledger.together(refs, today))
        if best_score is None or score > best_score:
            best, best_score = e, score
    return best, best_score


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def refs_of_record(p, folder):
    """(refs, is_reel) for one post record, whatever routine wrote it."""
    if folder == "posts":
        return [v["ref"] for v in p.get("verses", []) if v.get("ref")], False
    if folder == "morning":
        if p.get("format") == "reel":
            return p.get("reelRefs", []), True
        return p.get("refs", []), False
    if p.get("kind") == "share":
        return p.get("refs", []), False
    return [s["ref"] for s in p.get("slides", []) if s.get("kind") != "cta" and s.get("ref")], False


def from_repo(root=ROOT):
    """The ledger of every post that went out, from the records in the repo, and of the
    posts Ric approved in advance (staged), on the dates they are waiting for."""
    led = Ledger()
    for folder in ("posts", "morning", "world"):
        for path in sorted(glob.glob(os.path.join(root, folder, "*", "post.json"))):
            p = _load(path)
            if not p or p.get("status") != "posted":
                continue
            date = p.get("date") or os.path.basename(os.path.dirname(path))
            refs, reel = refs_of_record(p, folder)
            led.add(date, refs, reel)
    monday = _load(os.path.join(root, "studio", "morning", "monday.json")) or {}
    refs_by_moment = {m["id"]: m["ref"] for m in monday.get("moments", [])}
    for path in glob.glob(os.path.join(root, "studio", "morning", "staged", "*.jpg")):
        name = os.path.basename(path)[:-4]
        date, moment = name[:10], name[11:]
        if moment in refs_by_moment:
            led.add(date, [refs_by_moment[moment]])
    for path in glob.glob(os.path.join(root, "world", "*", "staged.json")):
        p = _load(path) or {}
        date = os.path.basename(os.path.dirname(path))
        led.add(date, [s["ref"] for s in p.get("slides", []) if s.get("kind") != "cta" and s.get("ref")])
    return led
