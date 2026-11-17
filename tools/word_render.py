#!/usr/bin/env python3
"""
The daily word reel, made ahead in a monthly batch (Ric, 2026-11-10 and 2026-11-17).

Each reel is one screen, set by code so the Scripture is exact: the day's verse in the
BSB with one word marked by a hand-drawn gold underline, its reference, then the Hebrew
or Greek word behind it, its Latin spelling, its syllables lighting as a native voice
says it twice, its meaning, and the line that ties it to the verse. Behind it, the
verse's own picture drifts slowly; under it, the one theme every reel shares ("quiet
pad and piano", from 6 s in, about -30 LUFS, the word about -17).

Everything comes from the app's bank, read from an app checkout (--app): the calendar
that says which entry each date shows (the same table the app reads), the verse from
the bundled Bible, the word, the picture and the app's own voice clip. Nothing here
writes or edits Scripture.

This runs on a Mac (it photographs the words with headless Chrome). The cloud routine
never renders: it only posts a reel Ric approved (tools/word_reel.py).

    python3 tools/word_render.py render --app APP --from 2026-11-18 [--to 2026-12-17] --out DIR
    python3 tools/word_render.py check  DIR                 # measures every reel in DIR again
    python3 tools/word_render.py review DIR                 # DIR/index.html, one page to approve
    python3 tools/word_render.py approve DIR --dates 2026-11-18..2026-12-17 [--by "Ric, 2026-11-18"]

Every reel is held by checks that measure rather than look (render refuses a reel that
fails any of them):
  words   every word on screen equals the bank and the bundled BSB, read back from the page
  layout  nothing overlaps, nothing is cut off, nothing sits in Instagram's caption band,
          the marked words are one unbroken run, every glyph is in the font that sets it
  ink     the words' pixels stay inside the safe area of the frame
  file    H.264 + AAC in an mp4 Instagram takes for Reels: 1080 x 1920, 30 fps, 48 kHz,
          moov before mdat, NO edit list, length and size in range
  sound   the theme sits near -30 LUFS, the word near -17, nothing over -1 dBTP
"""

import datetime as dt
import hashlib
import html
import importlib.util
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import word_reel  # noqa: E402  (the shared names: schedule, captions, file names)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONTS = os.path.join(ROOT, "tools", "assets", "fonts")
THEME = os.path.join(ROOT, "studio", "audio", "word-theme.mp3")
# Literata has no Hebrew, and the app leaves Hebrew to the phone's own face. New Peninim MT
# is a book serif that ships with macOS, sits beside Literata, and holds every letter and
# vowel point in the bank (measured from its character map before each render).
HEBREW_FACE = "/System/Library/Fonts/Supplemental/NewPeninimMT.ttc"

W, H, SCALE = 360, 640, 3            # the page in points; the frame is 1080 x 1920
FPS = 30
TOTAL = 14.0                          # seconds
FADE_IN = 0.5
DRAW = (2.2, 2.9)                     # the underline draws itself
FIRST_SAY = 3.7
GAP_SAYS = 1.0
SLOW = 0.72                           # the word said slowly, its pitch kept (Ric, 2026-11-10)
BOIL_EVERY, BOILS, DRAW_STEPS = 7, 3, 6
MUSIC_LUFS, VOICE_LUFS = -30.0, -17.0
BED_FROM = 6.0                        # the theme's steady part begins here

# Where words may sit, in points. Instagram lays its caption, name and buttons over the
# bottom fifth, and its header over the top; the right edge carries the like and share
# column in the lower half.
SAFE = dict(left=24, right=W - 24, top=52, bottom=512)
BAND = dict(top=96, bottom=508)       # the verse-and-word block is fitted in here
MIN_FIT = 0.80                        # type never shrinks below 80 % of its size

CREAM, GOLD = "#FFF9F1", "#E8B75E"


# ------------------------------------------------------------------ the bank

def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Bank:
    """The app's bank, read the way the app reads it."""

    def __init__(self, app):
        self.app = os.path.abspath(app)
        scripts = os.path.join(self.app, "scripts")
        sys.path.insert(0, scripts)
        self.vd = _module("verse_days", os.path.join(scripts, "verse_days.py"))
        self.builder = _module("build_verse_days", os.path.join(scripts, "build-verse-days.py"))
        days, wrong = self.builder.calendar()
        if wrong:
            raise SystemExit("the app's calendar does not hold: " + "; ".join(wrong))
        self.days = days                                   # day of the year -> place in ENTRIES
        self.entries = self.vd.ENTRIES
        self.db = sqlite3.connect(os.path.join(self.app, "assets", "bible", "bible.db"))
        self.names = dict(self.db.execute(
            "select book_id, name from book_names where translation_id = 'BSB'").fetchall())
        self.commit = subprocess.run(["git", "-C", self.app, "rev-parse", "--short", "HEAD"],
                                     capture_output=True, text=True).stdout.strip()

    def app_calendar(self):
        """The app's own generated copy (verse-days.ts): the ids in order, and the 366-day calendar."""
        import re
        ts = open(os.path.join(self.app, "src", "features", "today", "verse-days.ts"), encoding="utf-8").read()
        ids = re.findall(r'\{ id: "([^"]+)"', ts)
        cal = ts[ts.index("export const VERSE_CALENDAR"):]
        cal = [int(x) for x in re.findall(r"\d+", cal[cal.index("["):cal.index("];")])]
        return ids, cal

    def entry_for(self, date):
        """The entry the app shows on this calendar date (votd.ts: day of the year, 1 January is 0).
        Read from the bank's table AND from the app's generated copy; they must agree."""
        day = (date - dt.date(date.year, 1, 1)).days
        e = self.entries[self.days[day]]
        ids, cal = self.app_calendar()
        if len(cal) != 366 or ids[cal[day]] != e["id"]:
            raise SystemExit(f"{date}: the bank says {e['id']}, the app's verse-days.ts says {ids[cal[day]] if cal else '?'}; "
                             "run build-verse-days.py --emit in the app or use the checkout the app shipped from")
        return e

    def verse(self, ref):
        row = self.db.execute("select text from verses where translation_id = 'BSB' and book_id = ? "
                              "and chapter = ? and verse = ?", ref).fetchone()
        if not row:
            raise SystemExit(f"{ref} is not in the bundled BSB")
        return row[0]

    def label(self, ref):
        name = self.names[ref[0]]
        return f"{'Psalm' if name == 'Psalms' else name} {ref[1]}:{ref[2]}"

    def picture(self, e):
        return os.path.join(self.app, "assets", "verse-days", "pictures", f"{e['id']}.1.webp")

    def voice(self, e):
        return os.path.join(self.app, "assets", "verse-days", "voice", f"{e['id']}.mp3")

    def reel(self, e):
        """Everything one reel shows, as plain data. The verse is the BSB's own text."""
        text = self.verse(e["ref"])
        parts = split_at_mark(text, e["mark"])
        if parts is None:
            raise SystemExit(f"{e['id']}: “{e['mark']}” is not in the BSB verse")
        return dict(id=e["id"], lang=e["lang"], ref=self.label(e["ref"]), verse=text, mark=e["mark"],
                    before=parts[0], after=parts[2], word=e["word"], roman=e["roman"], say=list(e["say"]),
                    gloss=e["gloss"], first=self.builder.first_sentence(e), more=e["more"])


def split_at_mark(text, mark):
    """The app's splitAtMark (verse-day-core.ts): the first place the words stand whole."""
    first = text.find(mark)
    if not mark or first < 0:
        return None
    at = first
    while at >= 0 and ((at > 0 and text[at - 1].isalpha()) or text[at + len(mark):at + len(mark) + 1].isalpha()):
        at = text.find(mark, at + 1)
    if at < 0:
        at = first
    return text[:at], mark, text[at + len(mark):]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ the page

def _face(family, path, weight=400, style="normal", index=None):
    src = f"url('file://{path}')"
    return f"@font-face{{font-family:'{family}';src:{src};font-weight:{weight};font-style:{style}}}"


FACES = "".join([
    _face("Literata", os.path.join(FONTS, "Literata_400Regular.ttf"), 400),
    _face("Literata", os.path.join(FONTS, "Literata_500Medium.ttf"), 500),
    _face("Literata", os.path.join(FONTS, "Literata_600SemiBold.ttf"), 600),
    _face("Literata", os.path.join(FONTS, "Literata_400Regular_Italic.ttf"), 400, "italic"),
    _face("Inter", os.path.join(FONTS, "Inter_400Regular.ttf"), 400),
    _face("Inter", os.path.join(FONTS, "Inter_500Medium.ttf"), 500),
    _face("Inter", os.path.join(FONTS, "Inter_600SemiBold.ttf"), 600),
    _face("Inter", os.path.join(FONTS, "Inter_700Bold.ttf"), 700),
    "@font-face{font-family:'ChastenHebrew';src:local('New Peninim MT');font-weight:400}",
])

# Runs in the page. MEASURE: fit the block into the band, then report every box, every
# line count and the text each element really holds. Otherwise draw the underline.
SCRIPT = r"""
document.fonts.ready.then(function () {
  var frame = document.getElementById('f'), block = document.getElementById('c');
  var place = function (s) {
    document.documentElement.style.setProperty('--s', s);
    var h = block.getBoundingClientRect().height;
    block.style.top = Math.max(BAND_TOP, BAND_TOP + (BAND_BOTTOM - BAND_TOP - h) / 2) + 'px';
    return h;
  };
  if (MEASURE) {
    var s = 1, h = place(s);
    while (h > BAND_BOTTOM - BAND_TOP && s > MIN_FIT + 1e-6) { s = Math.round((s - 0.02) * 100) / 100; h = place(s); }
    var f = frame.getBoundingClientRect(), out = {fit: s, block: null, boxes: {}, fonts: {}};
    var box = function (el) { var r = el.getBoundingClientRect();
      return {x0: r.left - f.left, y0: r.top - f.top, x1: r.right - f.left, y1: r.bottom - f.top}; };
    out.block = box(block);
    document.querySelectorAll('[data-k]').forEach(function (el) {
      var k = el.getAttribute('data-k'), cs = getComputedStyle(el);
      var lh = parseFloat(cs.lineHeight);
      out.boxes[k] = Object.assign(box(el), {text: el.innerText, lines: Math.round(el.getBoundingClientRect().height / lh),
        sw: el.scrollWidth, cw: el.clientWidth, dir: cs.direction, family: cs.fontFamily, rects: el.getClientRects().length});
    });
    ['verse', 'note'].forEach(function (k) {
      var el = document.querySelector('[data-k="' + k + '"]'), words = [], walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) { var t = walker.currentNode, re = /\S+/g, mm;
        while ((mm = re.exec(t.data))) { var rg = document.createRange(); rg.setStart(t, mm.index); rg.setEnd(t, mm.index + mm[0].length);
          words.push([mm[0], Math.round(rg.getBoundingClientRect().top)]); } }
      var last = words.length ? words[words.length - 1][1] : 0;
      out.boxes[k].lastLine = words.filter(function (w) { return Math.abs(w[1] - last) < 3; }).map(function (w) { return w[0]; }).join(' ');
    });
    [['Literata', '400 21px Literata'], ['Literata italic', 'italic 400 15px Literata'], ['Inter', '600 10px Inter'],
     ['Hebrew', '400 44px ChastenHebrew']].forEach(function (p) { out.fonts[p[0]] = document.fonts.check(p[1]); });
    out.loaded = Array.from(document.fonts).filter(function (x) { return x.status === 'loaded'; }).map(function (x) {
      return x.family + ' ' + x.weight + ' ' + x.style; });
    document.getElementById('report').textContent = JSON.stringify(out);
    return;
  }
  place(FIT);
  if (!SHOW) return;
  var mk = function (s) { return function (a, b) { s |= 0; s = s + 0x6D2B79F5 | 0; var t = Math.imul(s ^ s >>> 15, 1 | s);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return a + (b - a) * (((t ^ t >>> 14) >>> 0) / 4294967296); }; };
  var shape = mk(4242), nudge = mk(SEED * 7919 + 13);
  var m = document.getElementById('m'), svg = document.getElementById('u');
  var r = m.getBoundingClientRect(), f2 = frame.getBoundingClientRect();
  var x0 = r.left - f2.left - 2, x1 = r.right - f2.left + 3, y = r.bottom - f2.top - 4.5 * FIT, tilt = shape(-0.7, 0.7);
  var n = Math.max(5, Math.round((x1 - x0) / 13)), pts = [];
  for (var i = 0; i <= n; i++) {
    var k = i / n;
    pts.push([x0 + (x1 - x0) * k + (i && i < n ? shape(-1, 1) : 0),
              y + Math.sin(k * 5.2 + 0.6) * 0.95 + shape(-0.5, 0.5) + (k - 0.5) * tilt + nudge(-0.34, 0.34)]);
  }
  var d = 'M' + pts[0][0].toFixed(2) + ' ' + pts[0][1].toFixed(2);
  for (var j = 1; j < pts.length - 1; j++) {
    var mx = (pts[j][0] + pts[j + 1][0]) / 2, my = (pts[j][1] + pts[j + 1][1]) / 2;
    d += ' Q' + pts[j][0].toFixed(2) + ' ' + pts[j][1].toFixed(2) + ' ' + mx.toFixed(2) + ' ' + my.toFixed(2);
  }
  d += ' L' + pts[pts.length - 1][0].toFixed(2) + ' ' + pts[pts.length - 1][1].toFixed(2);
  var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', d); p.setAttribute('fill', 'none'); p.setAttribute('stroke', GOLD);
  p.setAttribute('stroke-width', 2.3 * FIT); p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(p);
  var L = p.getTotalLength();
  p.setAttribute('stroke-dasharray', L + ' ' + L); p.setAttribute('stroke-dashoffset', L * (1 - PROG));
});
"""


def page(r, wordmark, syl=-1, show=True, seed=0, prog=1.0, fit=1.0, measure=False):
    e = html.escape
    hebrew = r["lang"] == "hebrew"
    lit = lambda i: f"color:{GOLD};font-weight:700" if i == syl else "color:rgba(255,249,241,.8);font-weight:500"
    dot = '<span style="color:rgba(255,249,241,.4)"> · </span>'
    syls = dot.join(f'<span style="{lit(i)}">{e(s)}</span>' for i, s in enumerate(r["say"]))
    shade = "text-shadow:0 1px 10px rgba(0,0,0,.5)"
    eyebrow = "font-size:calc(10px*var(--s));font-weight:700;letter-spacing:.2em"
    if hebrew:
        word = (f'<div style="margin-top:calc(4px*var(--s));display:flex;align-items:center;justify-content:center;gap:calc(10px*var(--s))">'
                f'<span data-k="word" dir="rtl" lang="he" style="font-family:ChastenHebrew;font-size:calc(46px*var(--s));'
                f'line-height:calc(62px*var(--s));{shade}">{e(r["word"])}</span>'
                f'<span data-k="rtl" style="font-size:calc(11px*var(--s));font-weight:600;letter-spacing:.02em;line-height:calc(14px*var(--s));'
                f'color:rgba(255,249,241,.62);{shade}">reads right to left</span></div>')
    else:
        word = (f'<div data-k="word" lang="el" style="margin-top:calc(6px*var(--s));font-family:Literata;font-weight:500;'
                f'font-size:calc(38px*var(--s));line-height:calc(50px*var(--s));{shade}">{e(r["word"])}</div>')
    quote = lambda s: f"“{s}”"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FACES}
:root{{--s:{fit}}} html,body{{margin:0;background:transparent}}
body{{font-family:Inter;-webkit-font-smoothing:antialiased}} #report{{display:none}}</style></head><body>
<div id="f" style="position:relative;width:{W}px;height:{H}px;overflow:hidden;color:{CREAM};text-align:center">
  <div style="position:absolute;left:0;right:0;top:58px;display:flex;align-items:center;justify-content:center;gap:9px;opacity:.86">
    <img data-k="brand" src="file://{wordmark}" alt="" style="width:56px;height:auto">
    <span data-k="site" style="font-size:10.5px;font-weight:600;letter-spacing:.05em;line-height:14px;{shade}">chasten.ai</span></div>
  <div id="c" style="position:absolute;left:34px;right:34px;top:{BAND['top']}px;display:flex;flex-direction:column;align-items:center">
    <div data-k="eyebrow" style="{eyebrow};line-height:calc(13px*var(--s));color:rgba(255,249,241,.86);{shade}">VERSE OF THE DAY</div>
    <div data-k="verse" style="margin-top:calc(10px*var(--s));text-wrap:balance;font-family:Literata;font-size:calc(21px*var(--s));line-height:calc(31px*var(--s));{shade}">{e(r["before"])}<span id="m" style="white-space:nowrap">{e(r["mark"])}</span>{e(r["after"])}</div>
    <div data-k="ref" style="margin-top:calc(9px*var(--s));font-size:calc(10.5px*var(--s));line-height:calc(14px*var(--s));font-weight:600;letter-spacing:.16em;color:rgba(255,249,241,.78);{shade}">{e(r["ref"].upper())}</div>
    <div style="margin:calc(24px*var(--s)) 0 calc(22px*var(--s));width:30px;height:1px;background:rgba(255,249,241,.32)"></div>
    <div data-k="lang" style="{eyebrow};line-height:calc(13px*var(--s));color:{GOLD};{shade}">{"HEBREW" if hebrew else "GREEK"} WORD OF THE DAY</div>
    {word}
    <div data-k="roman" style="margin-top:calc(2px*var(--s));font-family:Literata;font-style:italic;font-size:calc(15.5px*var(--s));line-height:calc(20px*var(--s));{shade}">{e(r["roman"])}</div>
    <div data-k="say" style="margin-top:calc(6px*var(--s));font-size:calc(14px*var(--s));line-height:calc(20px*var(--s));letter-spacing:.02em;{shade}">{syls}</div>
    <div data-k="gloss" style="margin-top:calc(13px*var(--s));font-family:Literata;font-size:calc(19px*var(--s));line-height:calc(26px*var(--s));{shade}">{e(quote(r["gloss"]))}</div>
    <div data-k="note" style="margin-top:calc(7px*var(--s));text-wrap:pretty;max-width:282px;font-size:calc(13px*var(--s));line-height:calc(19.5px*var(--s));color:rgba(255,249,241,.8);{shade}">{note_html(r)}</div>
  </div>
  <svg id="u" width="{W}" height="{H}" viewBox="0 0 {W} {H}" style="position:absolute;left:0;top:0;overflow:visible"></svg>
</div><pre id="report"></pre>
<script>var MEASURE = {str(measure).lower()}, SHOW = {str(show).lower()}, SEED = {seed}, PROG = {prog}, FIT = {fit}, GOLD = "{GOLD}",
BAND_TOP = {BAND['top']}, BAND_BOTTOM = {BAND['bottom']}, MIN_FIT = {MIN_FIT};{SCRIPT}</script></body></html>"""


def note_html(r):
    """The card's two sentences, the marked words in the first one set bold in cream, as on the approved sample."""
    e = html.escape
    q = f"“{r['mark']}”"
    first = r["first"]
    if q in first:
        a, b = first.split(q, 1)
        first_html = f'{e(a)}<b style="font-weight:600;color:{CREAM}">{e(q)}</b>{e(b)}'
    else:
        first_html = e(first)
    return f"{first_html} {e(r['more'])}"


def chrome(args):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                    "--virtual-time-budget=8000", "--run-all-compositor-stages-before-draw"] + args,
                   stdout=subprocess.PIPE if "--dump-dom" in args else subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=120, check=False)


def measure(r, wordmark, work):
    hp = os.path.join(work, "measure.html")
    open(hp, "w").write(page(r, wordmark, measure=True))
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--virtual-time-budget=8000",
                          f"--window-size={W},{H}", "--dump-dom", "file://" + hp],
                         capture_output=True, text=True, timeout=120).stdout
    a, b = out.find('<pre id="report">'), out.find("</pre>")
    raw = html.unescape(out[a + len('<pre id="report">'):b]) if a >= 0 else ""
    if not raw.strip():
        raise SystemExit(f"{r['id']}: the page reported nothing (fonts or Chrome failed)")
    return json.loads(raw)


def shoot(name, html_text, work):
    hp, png = os.path.join(work, name + ".html"), os.path.join(work, name + ".png")
    open(hp, "w").write(html_text)
    chrome([f"--force-device-scale-factor={SCALE}", f"--window-size={W},{H}", "--default-background-color=00000000",
            f"--screenshot={png}", "file://" + hp])
    if not os.path.exists(png):
        raise SystemExit(f"Chrome made no picture for {name}")
    return png


# ------------------------------------------------------------------ the checks

ORDER = ["eyebrow", "verse", "ref", "lang", "word", "roman", "say", "gloss", "note"]


def check_layout(r, rep, bank_reel):
    """Every word equals the bank, nothing overlaps or is cut off, all of it in the safe area."""
    fails = []
    b = rep["boxes"]
    want = dict(eyebrow="VERSE OF THE DAY", verse=bank_reel["verse"], ref=bank_reel["ref"].upper(),
                lang=("HEBREW" if r["lang"] == "hebrew" else "GREEK") + " WORD OF THE DAY", word=bank_reel["word"],
                roman=bank_reel["roman"], say=" · ".join(bank_reel["say"]), gloss=f"“{bank_reel['gloss']}”",
                note=f"{bank_reel['first']} {bank_reel['more']}", site="chasten.ai")
    if r["lang"] == "hebrew":
        want["rtl"] = "reads right to left"
    for k, v in want.items():
        got = (b.get(k) or {}).get("text")
        if got != v:
            fails.append(f"words: {k} reads {got!r}, the bank says {v!r}")
    if rep["fit"] < MIN_FIT - 1e-6 or rep["block"]["y1"] > BAND["bottom"] + 0.5:
        fails.append(f"layout: the block does not fit the band even at {rep['fit']:.2f} (ends at {rep['block']['y1']:.0f} pt)")
    for k, x in b.items():
        if k == "brand":
            continue
        if x["x0"] < SAFE["left"] - 0.5 or x["x1"] > SAFE["right"] + 0.5 or x["y0"] < SAFE["top"] - 0.5 or x["y1"] > SAFE["bottom"] + 0.5:
            fails.append(f"layout: {k} leaves the safe area ({x['x0']:.0f},{x['y0']:.0f})-({x['x1']:.0f},{x['y1']:.0f})")
        if x["sw"] > x["cw"] + 1 and x["cw"] > 0:
            fails.append(f"layout: {k} is wider than its box ({x['sw']} > {x['cw']}), so it is cut off")
    seq = [k for k in ORDER if k in b]
    for a_, c_ in zip(seq, seq[1:]):
        if b[a_]["y1"] > b[c_]["y0"] + 0.5:
            fails.append(f"layout: {a_} runs into {c_} ({b[a_]['y1']:.1f} > {b[c_]['y0']:.1f})")
    for k in ("verse", "note"):
        last = (b.get(k) or {}).get("lastLine", "")
        if b.get(k, {}).get("lines", 1) > 1 and len(last.split()) < 2:
            fails.append(f"layout: the {k} ends on a line holding only {last!r}")
    if "rtl" in b:
        w, n = b["word"], b["rtl"]
        if not (n["x0"] >= w["x1"] - 0.5 or n["x1"] <= w["x0"] + 0.5 or n["y0"] >= w["y1"] - 0.5):
            fails.append("layout: the right-to-left note overlaps the Hebrew word")
        if w["dir"] != "rtl":
            fails.append("layout: the Hebrew word is not set right to left")
    if rep["fonts"].get("Literata") is not True or rep["fonts"].get("Inter") is not True or rep["fonts"].get("Literata italic") is not True:
        fails.append(f"fonts: not every face loaded {rep['fonts']}")
    if "ChastenHebrew" not in str(rep.get("loaded")) and r["lang"] == "hebrew":
        fails.append("fonts: the Hebrew face did not load")
    return fails


def check_glyphs(r):
    """Every letter of the word, and every letter of the English, is in the face that sets it."""
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:
        raise SystemExit("python3 -m pip install fonttools (the glyph check needs it)")
    fails = []
    lit = TTFont(os.path.join(FONTS, "Literata_400Regular.ttf")).getBestCmap()
    inter = TTFont(os.path.join(FONTS, "Inter_600SemiBold.ttf")).getBestCmap()
    if r["lang"] == "hebrew":
        heb = TTCollection(HEBREW_FACE).fonts[0].getBestCmap()
        miss = [c for c in r["word"] if ord(c) not in heb]
        if miss:
            fails.append(f"fonts: the Hebrew face has no {''.join(miss)!r}")
    else:
        miss = [c for c in r["word"] if ord(c) not in lit]
        if miss:
            fails.append(f"fonts: Literata has no {''.join(miss)!r}")
    serif = r["verse"] + r["gloss"] + r["roman"] + "“”"
    miss = sorted({c for c in serif if not c.isspace() and ord(c) not in lit})
    if miss:
        fails.append(f"fonts: Literata has no {''.join(miss)!r}")
    sans = "".join(r["say"]) + r["first"] + r["more"] + r["ref"].upper() + "·"
    miss = sorted({c for c in sans if not c.isspace() and ord(c) not in inter})
    if miss:
        fails.append(f"fonts: Inter has no {''.join(miss)!r}")
    return fails


def check_ink(png):
    """The words' pixels, by their own alpha, stay in the safe area; the caption band stays clear."""
    from PIL import Image
    a = Image.open(png).getchannel("A").point(lambda v: 255 if v > 90 else 0)
    box = a.getbbox()
    fails = []
    if not box:
        return ["ink: the layer is empty"]
    x0, y0, x1, y1 = [v / SCALE for v in box]
    if x0 < SAFE["left"] or x1 > SAFE["right"] or y0 < SAFE["top"] - 8 or y1 > SAFE["bottom"]:
        fails.append(f"ink: words reach ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f}) pt, outside the safe area")
    return fails


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]).stdout
    return json.loads(out)


def boxes(path):
    """The mp4's boxes, depth first: [(depth, type, offset)]."""
    found = []
    containers = {b"moov", b"trak", b"edts", b"mdia", b"minf", b"stbl", b"udta", b"dinf"}
    with open(path, "rb") as f:
        data = f.read()

    def walk(at, end, depth):
        while at + 8 <= end:
            size = int.from_bytes(data[at:at + 4], "big")
            kind = data[at + 4:at + 8]
            head = 8
            if size == 1:
                size, head = int.from_bytes(data[at + 8:at + 16], "big"), 16
            elif size == 0:
                size = end - at
            if size < head:
                break
            found.append((depth, kind.decode("latin-1"), at))
            if kind in containers:
                walk(at + head, at + size, depth + 1)
            at += size
    walk(0, len(data), 0)
    return found


def loudness(path):
    """Momentary loudness every 100 ms, and the true peak."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", "verbose", "-i", path, "-filter_complex", "ebur128=peak=true:framelog=verbose",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    series, peak, integrated = [], None, None
    for line in err.splitlines():
        if "t:" in line and " M:" in line:
            try:
                t = float(line.split("t:")[1].split()[0])
                m = float(line.split(" M:")[1].split()[0])
                series.append((t, m))
            except (IndexError, ValueError):
                pass
        elif line.strip().startswith("I:") and "LUFS" in line:
            integrated = float(line.split()[1])
        elif line.strip().startswith("Peak:") and "dBFS" in line:
            peak = float(line.split()[1])
    return series, peak, integrated


def check_file(path, timing):
    """The file Instagram fetches: format, length, size, no edit list, and the sound's levels."""
    fails, facts = [], {}
    p = probe(path)
    v = [s for s in p["streams"] if s["codec_type"] == "video"]
    a = [s for s in p["streams"] if s["codec_type"] == "audio"]
    if len(v) != 1 or len(a) != 1:
        return [f"file: {len(v)} video and {len(a)} audio streams, wanted one of each"], facts
    v, a = v[0], a[0]
    want = dict(codec_name="h264", pix_fmt="yuv420p", width=1080, height=1920, r_frame_rate="30/1")
    for k, val in want.items():
        if v.get(k) != val:
            fails.append(f"file: video {k} is {v.get(k)}, wanted {val}")
    if v.get("profile") not in ("High", "Main"):
        fails.append(f"file: H.264 profile {v.get('profile')}")
    if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000" or a.get("channels") not in (1, 2):
        fails.append(f"file: audio is {a.get('codec_name')} {a.get('sample_rate')} Hz x{a.get('channels')}, wanted AAC 48 kHz")
    dur = float(p["format"]["duration"])
    size = int(p["format"]["size"])
    facts.update(seconds=round(dur, 2), bytes=size, kbps=round(int(p["format"].get("bit_rate", 0)) / 1000))
    if not 12.0 <= dur <= 16.0:
        fails.append(f"file: {dur:.2f} s long")
    if abs(float(a.get("duration", dur)) - float(v.get("duration", dur))) > 0.12:
        fails.append(f"file: sound {a.get('duration')} s and picture {v.get('duration')} s differ")
    if float(a.get("start_time", 0)) > 0.01 or float(v.get("start_time", 0)) > 0.01:
        fails.append("file: a stream does not start at zero")
    if size > 50 * 1024 * 1024:
        fails.append(f"file: {size / 1e6:.1f} MB, over the 50 MB this batch allows (Instagram takes up to 300 MB)")
    kinds = boxes(path)
    if any(k == "elst" for _, k, _ in kinds):
        fails.append("file: there is an edit list (elst), which Instagram mistimes")
    top = [k for d, k, _ in kinds if d == 0]
    if "moov" not in top or "mdat" not in top or top.index("moov") > top.index("mdat"):
        fails.append(f"file: moov is not before mdat ({top})")
    series, peak, integrated = loudness(path)
    facts.update(lufs=integrated, peak=peak)
    voice = [m for t, m in series for s in timing["says"] if s + 0.2 <= t <= s + timing["voice_len"] + 0.3]
    bed = sorted(m for t, m in series if 9.5 <= t <= 12.0)
    if not voice or not bed:
        fails.append("sound: no loudness readings")
    else:
        vmax, bmed = max(voice), bed[len(bed) // 2]
        facts.update(voice_peak_lufs=round(vmax, 1), bed_lufs=round(bmed, 1))
        if not -17.5 <= vmax <= -11.0:
            fails.append(f"sound: the word peaks at {vmax:.1f} LUFS momentary, wanted about -14 momentary (the approved sample: -13.7)")
        if not -34.0 <= bmed <= -26.0:
            fails.append(f"sound: the theme sits at {bmed:.1f} LUFS, wanted about -30")
    if peak is None or peak > -1.0:
        fails.append(f"sound: true peak {peak} dBTP, wanted under -1")
    return fails, facts


# ------------------------------------------------------------------ the sound

def lufs_of(path, repeat=1):
    """Integrated loudness. A clip under a second is looped so the meter has enough to read."""
    args = ["ffmpeg", "-hide_banner", "-nostats"]
    if repeat > 1:
        args += ["-stream_loop", str(repeat - 1)]
    err = subprocess.run(args + ["-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(json.loads(err[err.rindex("{"):err.rindex("}") + 1])["input_i"])


def bed_file(work):
    """The theme's steady part, evened (it was not generated at one level), cut to the reel."""
    bed = os.path.join(work, "bed.wav")
    if not os.path.exists(bed):
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(BED_FROM), "-i", THEME, "-af",
             f"dynaudnorm=f=300:g=21:p=0.5:m=12:s=6,atrim=0:{TOTAL},apad=whole_dur={TOTAL}", "-ar", "48000", "-ac", "2", bed])
    return bed


def clip_seconds(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout.strip())


# ------------------------------------------------------------------ one reel

def timing_for(voice):
    vlen = clip_seconds(voice) / SLOW
    return dict(says=[FIRST_SAY, FIRST_SAY + vlen + GAP_SAYS], voice_len=vlen)


def render_one(bank, e, out_dir, work_root, log=print):
    from PIL import Image
    r = bank.reel(e)
    work = os.path.join(work_root, e["id"])
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    wordmark = os.path.join(bank.app, "assets", "images", "wordmark-white.png")
    fails = check_glyphs(r)
    rep = measure(r, wordmark, work)
    fails += check_layout(r, rep, bank.reel(e))           # read the bank again: the page must equal it
    fit = rep["fit"]

    # The words, one see-through layer per thing that changes.
    n = len(r["say"])
    shoot("plain", page(r, wordmark, show=False, fit=fit), work)
    for k in range(1, DRAW_STEPS + 1):
        shoot(f"draw-{k}", page(r, wordmark, seed=0, prog=k / DRAW_STEPS, fit=fit), work)
    for b in range(BOILS):
        for s in range(-1, n):
            shoot(f"boil-{b}-syl{s}", page(r, wordmark, syl=s, seed=b, fit=fit), work)
    for name in ("plain", f"boil-0-syl-1", f"boil-0-syl{n - 1}"):
        fails += check_ink(os.path.join(work, name + ".png"))

    voice = bank.voice(e)
    tm = timing_for(voice)

    def syllable(t):
        for s in tm["says"]:
            if s <= t < s + tm["voice_len"]:
                return min(n - 1, int((t - s) / tm["voice_len"] * n))     # equal shares, as the app lights them
        return -1

    def layer_at(i):
        t = i / FPS
        if t < DRAW[0]:
            return "plain"
        if t < DRAW[1]:
            return f"draw-{min(DRAW_STEPS, 1 + int((t - DRAW[0]) / (DRAW[1] - DRAW[0]) * DRAW_STEPS))}"
        return f"boil-{(i // BOIL_EVERY) % BOILS}-syl{syllable(t)}"

    # The picture drifts behind a veil that deepens toward the words.
    pic = Image.open(bank.picture(e)).convert("RGB")
    PW, PH = pic.size
    stops = [(0.0, .34), (0.10, .30), (0.20, .52), (0.55, .64), (1.0, .76)]
    col = Image.new("RGBA", (1, H * SCALE))
    for y in range(H * SCALE):
        k = y / (H * SCALE - 1)
        for (a0, v0), (a1, v1) in zip(stops, stops[1:]):
            if a0 <= k <= a1:
                a = v0 + (v1 - v0) * (k - a0) / (a1 - a0)
                break
        col.putpixel((0, y), (10, 7, 3, round(a * 255)))
    veil = col.resize((W * SCALE, H * SCALE))
    layers = {}
    FW, FH = W * SCALE, H * SCALE
    frames = round(TOTAL * FPS)
    silent = os.path.join(work, "silent.mp4")
    cover = None
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{FW}x{FH}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "slow",
                           "-bf", "0", "-g", "60", "-r", str(FPS), silent], stdin=subprocess.PIPE)
    cover_at = round((DRAW[1] + 0.4) * FPS)
    for i in range(frames):
        k = i / (frames - 1)
        ease = 0.5 - 0.5 * math.cos(math.pi * k)
        zoom = 1.15 - 0.06 * ease
        scale = max(FW / PW, FH / PH) * zoom
        cw, ch = FW / scale, FH / scale
        x0 = (PW - cw) / 2 + (ease - 0.5) * 14
        y0 = (PH - ch) / 2
        bg = pic.resize((FW, FH), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch)).convert("RGBA")
        bg.alpha_composite(veil)
        name = layer_at(i)
        if name not in layers:
            layers[name] = Image.open(os.path.join(work, name + ".png")).convert("RGBA")
        frame = bg.copy()
        frame.alpha_composite(layers[name])
        t = i / FPS
        if t < FADE_IN:
            frame = Image.blend(bg, frame, t / FADE_IN)
        rgb = frame.convert("RGB")
        if i == cover_at:
            cover = rgb.copy()
        ff.stdin.write(rgb.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit(f"{e['id']}: the picture would not encode")

    # The sound: the theme low and lower still under the word; the word twice, slowed, pitch kept.
    bed = bed_file(work_root)
    music_gain = 10 ** ((MUSIC_LUFS - lufs_of(bed)) / 20)
    voice_gain = 10 ** ((VOICE_LUFS - lufs_of(voice, repeat=6)) / 20)
    s1, s2 = tm["says"]
    dip0, dip1 = s1 - 0.25, s2 + tm["voice_len"] + 0.1
    music = (f"[1:a]volume={music_gain:.4f},afade=t=in:d=0.8,afade=t=out:st={TOTAL - 2.2}:d=2.2,"
             f"volume='1-0.4*(clip((t-{dip0 - 0.3})/0.3,0,1)-clip((t-{dip1})/0.6,0,1))':eval=frame[m]")
    words = (f"[2:a]aresample=48000,aformat=channel_layouts=stereo,atempo={SLOW},volume={voice_gain:.4f},asplit=2[v1][v2];"
             f"[v1]adelay={round(s1 * 1000)}:all=1[a1];[v2]adelay={round(s2 * 1000)}:all=1[a2]")
    mix = "[m][a1][a2]amix=inputs=3:normalize=0:duration=first,alimiter=limit=0.84:level=false[a]"
    mp4 = os.path.join(out_dir, f"{e['id']}.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", bed, "-i", voice, "-filter_complex", f"{music};{words};{mix}",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
         "-t", str(TOTAL), "-shortest", "-use_editlist", "0", "-movflags", "+faststart", mp4])
    jpg = os.path.join(out_dir, f"{e['id']}.jpg")
    cover.save(jpg, quality=90)
    file_fails, facts = check_file(mp4, tm)
    fails += file_fails
    meta = dict(reel=r, fit=fit, timing=tm, facts=facts, fails=fails, sha256=sha256(mp4), cover_sha256=sha256(jpg),
                picture=os.path.basename(bank.picture(e)), voice=os.path.basename(voice), picture_sha256=sha256(bank.picture(e)),
                voice_sha256=sha256(voice), app=bank.commit, layout=rep)
    with open(os.path.join(out_dir, f"{e['id']}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f"{e['id']}: {'OK' if not fails else 'FAILED'} fit {fit:.2f}, {facts.get('seconds')} s, "
        f"{facts.get('bytes', 0) / 1e6:.1f} MB, word {facts.get('voice_peak_lufs')} / theme {facts.get('bed_lufs')} LUFS, peak {facts.get('peak')}")
    for x in fails:
        log("   " + x)
    return meta


# ------------------------------------------------------------------ the batch

def dates_between(a, b):
    d, out = dt.date.fromisoformat(a), []
    while d <= dt.date.fromisoformat(b):
        out.append(d)
        d += dt.timedelta(days=1)
    return out


def cmd_render(argv):
    a = dict(zip(argv[::2], argv[1::2]))
    bank = Bank(a["--app"])
    out = os.path.abspath(a["--out"])
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, "_work")
    if "--ids" in a:  # a matrix of entries regardless of date: proves the layout holds for each
        ids = bank.entries if a["--ids"] == "all" else [x for x in bank.entries if x["id"] in a["--ids"].split(",")]
        fails = [x["id"] for x in ids if render_one(bank, x, out, os.path.join(out, "_work"))["fails"]]
        print(f"{len(ids)} entries, {len(fails)} failed: {', '.join(fails)}")
        return 1 if fails else 0
    dates = dates_between(a["--from"], a.get("--to", a["--from"]))
    batch_path = os.path.join(out, "batch.json")
    batch = json.load(open(batch_path)) if os.path.exists(batch_path) else {"days": {}}
    batch.update(app=bank.commit, theme_sha256=sha256(THEME))
    made = {}
    for d in dates:
        e = bank.entry_for(d)
        if e["id"] not in made:
            made[e["id"]] = render_one(bank, e, out, work)
        m = made[e["id"]]
        batch["days"][d.isoformat()] = dict(id=e["id"], ref=m["reel"]["ref"], ok=not m["fails"], sha256=m["sha256"],
                                            caption=word_reel.caption(m["reel"], d.isoformat()))
    with open(batch_path, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=1)
    bad = [d for d, x in batch["days"].items() if not x["ok"]]
    cap_bad = {d: word_reel.caption_problems(x["caption"], json.load(open(os.path.join(out, x["id"] + ".json")))["reel"])
               for d, x in batch["days"].items()}
    cap_bad = {d: p for d, p in cap_bad.items() if p}
    for d, p in cap_bad.items():
        print(f"{d} caption: " + "; ".join(p))
    print(f"{len(dates)} days, {len(made)} reels, {len(bad)} failed, {len(cap_bad)} captions with problems")
    shutil.rmtree(work, ignore_errors=True)
    return 1 if bad or cap_bad else 0


def cmd_check(argv):
    out = os.path.abspath(argv[0])
    bad = 0
    for name in sorted(os.listdir(out)):
        if name.endswith(".json") and name != "batch.json":
            meta = json.load(open(os.path.join(out, name)))
            mp4 = os.path.join(out, name[:-5] + ".mp4")
            fails, facts = check_file(mp4, meta["timing"])
            if sha256(mp4) != meta["sha256"]:
                fails.append("file: changed since it was rendered")
            fails += meta["fails"]
            bad += bool(fails)
            print(f"{name[:-5]}: {'OK' if not fails else 'FAILED'} {facts}")
            for x in fails:
                print("   " + x)
    return 1 if bad else 0


def cmd_review(argv):
    out = os.path.abspath(argv[0])
    batch = json.load(open(os.path.join(out, "batch.json")))
    rows = []
    for d, x in sorted(batch["days"].items()):
        meta = json.load(open(os.path.join(out, x["id"] + ".json")))
        r, f = meta["reel"], meta["facts"]
        day = dt.date.fromisoformat(d).strftime("%a %-d %b")
        verdict = "All checks pass" if not meta["fails"] else "FAILED: " + "; ".join(meta["fails"])
        rows.append(f"""<article><video src="{x['id']}.mp4" poster="{x['id']}.jpg" controls playsinline preload="none"></video>
<div class="t"><p class="d">{html.escape(day)}</p><h2>{html.escape(r['ref'])} · <span lang="{'he' if r['lang'] == 'hebrew' else 'el'}">{html.escape(r['word'])}</span> {html.escape(r['roman'])}</h2>
<p class="m">{html.escape(verdict)} · {f.get('seconds')} s · {f.get('bytes', 0) / 1e6:.1f} MB · word {f.get('voice_peak_lufs')} LUFS, theme {f.get('bed_lufs')} LUFS · type at {meta['fit']:.0%}</p>
<pre>{html.escape(x['caption'])}</pre></div></article>""")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Word reels for review</title><style>
:root{{--bg:#FBF7F0;--ink:#1F1A14;--soft:#6B6155;--line:#E6DCCD}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14110D;--ink:#F3ECE1;--soft:#A99E8F;--line:#2C261F}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px}} h1{{font-size:22px;margin:0 0 4px}} .s{{color:var(--soft);margin:0 0 20px}}
article{{display:flex;gap:20px;padding:18px 0;border-top:1px solid var(--line);align-items:flex-start}}
video{{width:230px;aspect-ratio:9/16;border-radius:10px;background:#000;flex:none}}
.t{{min-width:0}} .d{{margin:0;color:var(--soft);font-size:13px}} h2{{font-size:17px;margin:2px 0 4px}}
.m{{color:var(--soft);font-size:13px;margin:0 0 8px}} pre{{white-space:pre-wrap;font:13px/1.45 ui-monospace,monospace;margin:0}}
@media (max-width:640px){{article{{flex-direction:column}} video{{width:100%;max-width:300px}}}}
</style></head><body><main><h1>Word reels, {html.escape(min(batch['days']))} to {html.escape(max(batch['days']))}</h1>
<p class="s">Each reel with the caption that goes with it, made from the app's bank at commit {html.escape(batch.get('app', ''))}.</p>
{''.join(rows)}</main></body></html>"""
    path = os.path.join(out, "index.html")
    open(path, "w", encoding="utf-8").write(doc)
    print(path)
    return 0


def cmd_approve(argv):
    """Copy the approved reels into the repo and mark their days. Only Ric's word runs this."""
    out = os.path.abspath(argv[0])
    a = dict(zip(argv[1::2], argv[2::2]))
    lo, hi = a["--dates"].split("..")
    by = a.get("--by", "Ric")
    batch = json.load(open(os.path.join(out, "batch.json")))
    sched = word_reel.load_schedule()
    n = 0
    for d in dates_between(lo, hi):
        x = batch["days"].get(d.isoformat())
        if not x:
            raise SystemExit(f"{d}: not in this batch")
        meta = json.load(open(os.path.join(out, x["id"] + ".json")))
        if meta["fails"] or not x["ok"]:
            raise SystemExit(f"{d}: {x['id']} failed its checks and cannot be approved")
        mp4 = os.path.join(out, x["id"] + ".mp4")
        if sha256(mp4) != x["sha256"]:
            raise SystemExit(f"{d}: {x['id']}.mp4 changed after it was checked")
        name = word_reel.reel_name(x["id"], x["sha256"])
        dest = os.path.join(ROOT, word_reel.REELS, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest + ".mp4"):
            shutil.copyfile(mp4, dest + ".mp4")
            shutil.copyfile(os.path.join(out, x["id"] + ".jpg"), dest + ".jpg")
        r = meta["reel"]
        sched["days"][d.isoformat()] = dict(id=x["id"], file=f"{word_reel.REELS}/{name}.mp4", cover=f"{word_reel.REELS}/{name}.jpg",
                                            sha256=x["sha256"], ref=r["ref"], word=r["word"], roman=r["roman"], lang=r["lang"],
                                            caption=x["caption"], app=batch.get("app"), approved=by)
        n += 1
    word_reel.save_schedule(sched)
    print(f"{n} days approved by {by}")
    return 0


def cmd_calendar(argv):
    """{date: reference} the app shows, for tools/check_fresh.py --word-calendar."""
    a = dict(zip(argv[::2], argv[1::2]))
    bank = Bank(a["--app"])
    out = {d.isoformat(): bank.label(bank.entry_for(d)["ref"]) for d in dates_between(a["--from"], a["--to"])}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    sys.exit({"calendar": cmd_calendar, "render": cmd_render, "check": cmd_check, "review": cmd_review, "approve": cmd_approve}[cmd](rest))
