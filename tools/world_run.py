#!/usr/bin/env python3
"""
"Scripture in the world": the 11 AM Instagram carousel.

Every slide is a photograph with one short line placed in the scene (a
billboard, a cafe chalkboard, a note on a dashboard, a departure board), and
the last slide asks for an Amen. Most lines are word-for-word BSB; a couple
a day are our own conversational lines with the verse they come from beneath
them (studio/world/lines.json, checked by tools/check_world_lines.py). The
scenes are studio/world/scenes.json; Google's Gemini image model draws them.
This script plans the post, calls the model, gives every slide the same warm
black-and-white finish, checks the words on each slide, and records state.

    python3 tools/world_run.py status  W --date D   # posted, staged or fresh
    python3 tools/world_run.py plan    W --date D   # or --lines a,b,.. --scenes x,y,..
    python3 tools/world_run.py generate W [--only 3,5]
    python3 tools/world_run.py grade   W
    python3 tools/world_run.py verify  W            # compares W/work/read.json with the plan
    python3 tools/world_run.py final   W            # the cards that passed, in order
    python3 tools/world_run.py caption-check W
    python3 tools/world_run.py package W --date D --status posted|failed [--permalink U] [--media-id I] [--note T] [--staged]
    python3 tools/world_run.py sheet   W

The key: GEMINI_API_KEY, or --env-file PATH holding a GEMINI_API_KEY= line
(Ric's Mac reads the app repo's .env.local). In the cloud routine neither is
set: the environment's API credential adds the x-goog-api-key header on the
way out, so no command, file or variable there ever holds it.

W/work/read.json is written by whoever looks at the slides (Claude, in the
routine): {"1": "every word seen on slide 1", ...}, and W/work/defects.json
names slides with a visible flaw: {"4": "extra letters on a sign"}. `verify`
compares the words with the plan, word for word, ignoring case and
punctuation. A slide that fails is redrawn once; if it fails again, `final`
leaves it out. Nothing that misquotes Scripture is ever posted.
"""

import base64
import concurrent.futures
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    import PIL  # noqa: F401
except ImportError:
    # The cloud sandbox ships without Pillow, and its bare `pip` can install into
    # a different Python than `python3` (2026-10-08). Install into this one.
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "pillow"])

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORLD = os.path.join(ROOT, "studio", "world")
STATE = os.path.join(ROOT, "studio", "state", "world-pointer.json")
MORNING = os.path.join(ROOT, "studio", "state", "pointer.json")  # the 7 AM post's state
SETTINGS = os.path.join(ROOT, "studio", "config", "settings.json")
RAW = "https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/world/{date}/{n}.jpg"
MODEL = os.environ.get("WORLD_MODEL", "gemini-3-pro-image")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PRICE = 0.134  # dollars per 2K drawing on gemini-3-pro-image (ai.google.dev pricing, 2026-09)
W_OUT, H_OUT = 1080, 1350

# One theme gives each post its centre; the rest of the slides come from anywhere.
THEMES = ["trust", "peace", "strength", "hope", "love", "rest", "courage", "identity",
          "presence", "grace", "guidance", "timing", "joy", "prayer", "gratitude"]
CONTENT_SLIDES = 8   # plus the closing slide
SAID_PER_POST = 2    # our own conversational lines; the rest are Scripture
LINE_GAP = 12        # posts before a line may appear again
SCENE_GAP = 2        # posts before a scene may appear again
MIN_FINAL = 5        # cards a post needs after failed slides are left out

STYLE = ("A black-and-white 35mm film photograph with a subtle warm tone, natural light, "
         "soft film grain, shallow depth of field, candid and cinematic, photorealistic. "
         "Vertical 4:5 framing, with the words large and clear enough to read on a phone.")
RULE = ("These are the only readable words anywhere in the image: {words}. Spell every "
        "word exactly as written here and keep the punctuation. Add no other text, letters, "
        "numbers, logos, signs, labels, captions or watermarks anywhere.")


def load(path, default=None):
    if not os.path.exists(path) and default is not None:
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def api_key():
    key = os.environ.get("GEMINI_API_KEY")
    path = arg("--env-file")
    if not key and path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key  # None in the cloud: the proxy adds the header


def words(text):
    """The words of a line, for comparison: lowercase, punctuation gone,
    apostrophes and a handle's dot kept inside a word."""
    text = text.replace("’", "'").replace("‘", "'").lower()
    return re.findall(r"@?[a-z0-9]+(?:['.][a-z0-9]+)*", text)


def rows_of(text, width):
    """Wrap a line into rows of at most `width` characters, for boards."""
    rows, row = [], ""
    for word in text.split():
        if row and len(row) + 1 + len(word) > width:
            rows.append(row)
            row = word
        else:
            row = f"{row} {word}".strip()
    return rows + [row] if row else rows


def shape(text, scene):
    return text.upper() if scene.get("case") == "upper" else text


def prompt_for(line, scene):
    text = shape(line["text"], scene)
    ref = shape(line["ref"], scene)
    if scene.get("rows"):
        parts = rows_of(text, scene["rows"])
        text_q = " / ".join(f'"{r}"' for r in parts)
    else:
        parts = [text]
        text_q = f'"{text}"'
    quoted = ", ".join(f'"{p}"' for p in parts + [ref])
    body = (scene["prompt"].replace("{TEXT}", text_q).replace("{REF}", f'"{ref}"')
            .replace("{ROWS}", str(len(parts) + 1)))
    return f"{STYLE}\n\n{body}\n\n{RULE.format(words=quoted)}"


def fits(line, scene):
    return len(words(line["text"])) <= scene.get("maxWords", 99)


def pick(date, lines, scenes, state):
    """Today's lines and scenes: a theme's lines first, SAID_PER_POST of our
    own, nothing used in the last LINE_GAP posts, an opener that is strong
    enough to stop the scroll, and no scene from the last SCENE_GAP posts.
    Every choice follows from the date and the state, so a rerun is the same."""
    rng = random.Random(f"world-{date}")
    hist = state.get("history", [])
    theme = THEMES[state.get("postCount", 0) % len(THEMES)]
    used = {i for h in hist[-LINE_GAP:] for i in h.get("lines", [])}
    pool = [l for l in lines if l["kind"] in ("verse", "said") and l["id"] not in used]
    if len(pool) < CONTENT_SLIDES + SAID_PER_POST:  # a short pool: allow repeats
        pool = [l for l in lines if l["kind"] in ("verse", "said")]

    verses_taken = set()

    def draw(cands, n):
        """n lines from cands, never two from the same verse in one post."""
        cands = list(cands)
        rng.shuffle(cands)
        out = []
        for l in cands:
            if len(out) >= n:
                break
            if l["verse"] in verses_taken:
                continue
            verses_taken.add(l["verse"])
            out.append(l)
        return out

    on = [l for l in pool if theme in l["themes"]]
    said_on = draw([l for l in on if l["kind"] == "said"], SAID_PER_POST)
    chosen = said_on + draw([l for l in on if l["kind"] == "verse"], CONTENT_SLIDES - SAID_PER_POST)
    rest = [l for l in pool if l not in chosen]
    chosen += draw([l for l in rest if l["kind"] == "said"], SAID_PER_POST - len(said_on))
    chosen += draw([l for l in rest if l["kind"] == "verse" and l not in chosen], CONTENT_SLIDES - len(chosen))

    hooks = [l for l in chosen if l.get("hook")]
    first = hooks[0] if hooks else min(chosen, key=lambda l: len(words(l["text"])))
    others = [l for l in chosen if l is not first]
    rng.shuffle(others)
    ordered = [first] + others

    content = [s for s in scenes if s["kind"] == "content"]
    recent = {s for h in hist[-SCENE_GAP:] for s in h.get("scenes", [])}
    taken, assigned = set(), {}
    # Longest lines first, so the few scenes that hold a long verse go to them.
    for idx in sorted(range(len(ordered)), key=lambda i: (-len(words(ordered[i]["text"])), i)):
        line = ordered[idx]
        for relax in (0, 1):
            cands = [s for s in content if fits(line, s) and s["id"] not in taken
                     and (relax or s["id"] not in recent)]
            if idx == 0 and any(s.get("opener") for s in cands):
                cands = [s for s in cands if s.get("opener")]
            if cands:
                break
        if not cands:
            sys.exit(f"no scene can hold {line['id']}; add a scene with more room")
        choice = rng.choice(cands)
        taken.add(choice["id"])
        assigned[idx] = choice

    ctas = [l for l in lines if l["kind"] == "cta"]
    cta_scenes = [s for s in scenes if s["kind"] == "cta"]
    k = state.get("postCount", 0)
    pairs = [(line, assigned[i]) for i, line in enumerate(ordered)]
    pairs.append((ctas[k % len(ctas)], cta_scenes[k % len(cta_scenes)]))
    return theme, pairs


def audio_for(theme, state):
    """A song idea for Slack, the same way the 7 AM post suggests one: the
    first song in the theme's list (studio/config/settings.json audio.byTheme)
    that neither post used lately, so the two posts never suggest the same
    song on the same day."""
    audio = load(SETTINGS)["audio"]
    word = {"timing": "waiting"}.get(theme, theme)
    songs = next((v for k, v in audio["byTheme"].items() if word in [w.strip() for w in k.split(",")]),
                 audio.get("fallback", []))
    recent = list(state.get("usedAudio", []))[-8:] + list(load(MORNING, {}).get("usedAudio", []))[-3:]
    fresh = [x for x in songs if x not in recent]
    if fresh:
        return fresh[0]
    return min(songs, key=lambda x: recent.index(x) if x in recent else -1) if songs else None


def plan(work):
    lines = load(os.path.join(WORLD, "lines.json"))["lines"]
    scenes = load(os.path.join(WORLD, "scenes.json"))["scenes"]
    by_line = {x["id"]: x for x in lines}
    by_scene = {x["id"]: x for x in scenes}
    want_lines = [x for x in (arg("--lines") or "").split(",") if x]
    want_scenes = [x for x in (arg("--scenes") or "").split(",") if x]
    if want_lines:
        if len(want_lines) != len(want_scenes):
            sys.exit("--lines and --scenes must be the same length")
        theme, pairs = arg("--theme", "mixed"), [(by_line[l], by_scene[s]) for l, s in zip(want_lines, want_scenes)]
    else:
        date = arg("--date")
        if not date:
            sys.exit("plan needs --date (or --lines and --scenes)")
        theme, pairs = pick(date, lines, scenes, load(STATE, {}))
    slides = []
    for n, (line, scene) in enumerate(pairs, 1):
        if not fits(line, scene):
            sys.exit(f"{line['id']} is too long for {scene['id']}")
        # A fragment that starts mid-sentence in the BSB ("seek first...") opens
        # with a capital on the slide; the word check ignores case.
        line = dict(line, text=line["text"][:1].upper() + line["text"][1:])
        slides.append({"n": n, "line": line["id"], "kind": line["kind"], "scene": scene["id"],
                       "text": line["text"], "ref": line["ref"], "verse": line.get("verse"),
                       "prompt": prompt_for(line, scene)})
    audio = audio_for(theme, load(STATE, {}))
    dump(os.path.join(work, "work", "plan.json"),
         {"date": arg("--date"), "theme": theme, "audio": audio, "model": MODEL, "slides": slides})
    print(f"theme: {theme}; audio idea: {audio}")
    for s in slides:
        print(f'{s["n"]}. [{s["scene"]}] ({s["kind"]}) {s["text"]} ({s["ref"]})')


def draw_one(slide, key, raw_dir):
    body = {"contents": [{"parts": [{"text": slide["prompt"]}]}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": "4:5", "imageSize": "2K"}}}
    headers = {"content-type": "application/json"}
    if key:
        headers["x-goog-api-key"] = key
    url = API.format(model=MODEL)
    last = None
    for attempt in range(3):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.load(r)
            parts = d.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            images = [p["inlineData"] for p in parts if "inlineData" in p and not p.get("thought")]
            if not images:
                last = f"no image ({d.get('candidates', [{}])[0].get('finishReason')})"
                continue
            for old in os.listdir(raw_dir):  # a redraw replaces the old file whatever its type
                if old.startswith(f"slide{slide['n']}."):
                    os.remove(os.path.join(raw_dir, old))
            ext = "png" if "png" in images[-1].get("mimeType", "") else "jpg"
            path = os.path.join(raw_dir, f"slide{slide['n']}.{ext}")
            with open(path, "wb") as f:
                f.write(base64.b64decode(images[-1]["data"]))
            return {"n": slide["n"], "raw": path, "error": None}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # network hiccup: try again
            last = repr(e)
        time.sleep(6 * (attempt + 1))
    return {"n": slide["n"], "raw": None, "error": last}


def generate(work):
    p = load(os.path.join(work, "work", "plan.json"))
    only = {int(x) for x in (arg("--only") or "").split(",") if x}
    todo = [s for s in p["slides"] if not only or s["n"] in only]
    raw_dir = os.path.join(work, "work", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    key = api_key()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda s: draw_one(s, key, raw_dir), todo))
    by_n = {r["n"]: r for r in results}
    for s in p["slides"]:
        if s["n"] in by_n:
            s["raw"], s["error"] = by_n[s["n"]]["raw"], by_n[s["n"]]["error"]
            s["draws"] = s.get("draws", 0) + 1
            s.pop("card", None)
    dump(os.path.join(work, "work", "plan.json"), p)
    for r in results:
        print(f'slide {r["n"]}: {"ok" if r["raw"] else "FAILED " + str(r["error"])}')


def trim_border(im):
    """Cut away a flat photo-print border when the model draws one: edge rows
    and columns that are one even white or black. A real photo's edge always
    varies (stddev 8 and up); a drawn border is under 1. At most 8% a side."""
    g = ImageOps.grayscale(im)
    w, h = g.size

    def run(boxes):
        n = 0
        for box in boxes:
            st = ImageStat.Stat(g.crop(box))
            if st.stddev[0] >= 3 or 20 <= st.mean[0] <= 235:
                break
            n += 1
        return n + 4 if n else 0  # and the soft row where border meets photo

    top = run((0, y, w, y + 1) for y in range(int(h * 0.08)))
    bottom = run((0, h - 1 - y, w, h - y) for y in range(int(h * 0.08)))
    left = run((x, 0, x + 1, h) for x in range(int(w * 0.08)))
    right = run((w - 1 - x, 0, w - x, h) for x in range(int(w * 0.08)))
    return im.crop((left, top, w - right, h - bottom))


def finish(im):
    """The Chasten finish: cover-cut to 4:5, warm black and white, a little
    grain and a soft vignette, so nine different scenes read as one post."""
    im = trim_border(im.convert("RGB"))
    w, h = im.size
    if w / h > W_OUT / H_OUT:
        nw = round(h * W_OUT / H_OUT)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = round(w * H_OUT / W_OUT)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((W_OUT, H_OUT), Image.LANCZOS)
    mono = ImageOps.grayscale(im)
    mono = ImageOps.autocontrast(mono, cutoff=(0.4, 0.4))
    out = ImageOps.colorize(mono, black=(17, 14, 12), white=(248, 242, 233), mid=(128, 119, 108))
    noise = Image.effect_noise((W_OUT, H_OUT), 22)
    out = ImageChops.soft_light(out, Image.merge("RGB", [noise] * 3))
    ring = Image.radial_gradient("L").resize((W_OUT, H_OUT), Image.BILINEAR)
    ring = ring.point(lambda v: 255 - int(max(0, v - 110) * 0.30))
    return ImageChops.multiply(out, Image.merge("RGB", [ring] * 3))


def grade(work):
    p = load(os.path.join(work, "work", "plan.json"))
    raw_dir = os.path.join(work, "work", "raw")
    for s in p["slides"]:
        if not s.get("raw"):  # a re-plan keeps drawings already on disk
            found = [f for f in sorted(os.listdir(raw_dir)) if f.startswith(f"slide{s['n']}.")] \
                if os.path.isdir(raw_dir) else []
            s["raw"] = os.path.join(raw_dir, found[0]) if found else None
        if not s.get("raw"):
            print(f'slide {s["n"]}: no drawing to finish')
            continue
        out = finish(Image.open(s["raw"]))
        path = os.path.join(work, "work", f"card{s['n']}.jpg")
        out.save(path, quality=90, optimize=True, progressive=True)
        s["card"] = path
        print(f'slide {s["n"]}: {path}')
    dump(os.path.join(work, "work", "plan.json"), p)


def verify(work):
    p = load(os.path.join(work, "work", "plan.json"))
    read = load(os.path.join(work, "work", "read.json"))
    defects = load(os.path.join(work, "work", "defects.json"), {})
    report, bad = {}, []
    for s in p["slides"]:
        want = words(f'{s["text"]} {s["ref"]}')
        seen = words(read.get(str(s["n"]), ""))
        flaw = defects.get(str(s["n"]))
        ok = bool(s.get("card")) and want == seen and not flaw
        report[s["n"]] = {"ok": ok, "want": " ".join(want), "seen": " ".join(seen), "defect": flaw}
        if not ok:
            bad.append(s["n"])
        why = "" if ok else (f"\n  want: {' '.join(want)}\n  seen: {' '.join(seen)}" +
                             (f"\n  defect: {flaw}" if flaw else "") + ("" if s.get("card") else "\n  no card"))
        print(f'slide {s["n"]}: {"ok" if ok else "FAILED"}{why}')
    dump(os.path.join(work, "work", "verify.json"), {"bad": bad, "slides": report})
    print("redraw: " + (",".join(map(str, bad)) if bad else "none"))
    sys.exit(1 if bad else 0)


def final(work):
    """Copy the cards that passed, in order, to W/out/cards/1.jpg.. and record
    them. Exits 1 when too few are left to post, or the opener or every
    Scripture slide failed."""
    p = load(os.path.join(work, "work", "plan.json"))
    bad = set(load(os.path.join(work, "work", "verify.json"), {"bad": []})["bad"])
    keep = [s for s in p["slides"] if s.get("card") and s["n"] not in bad]
    out = os.path.join(work, "out", "cards")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for i, s in enumerate(keep, 1):
        shutil.copy(s["card"], os.path.join(out, f"{i}.jpg"))
    p["final"] = [{"n": i, "slide": s["n"], "line": s["line"], "kind": s["kind"], "scene": s["scene"],
                   "text": s["text"], "ref": s["ref"]} for i, s in enumerate(keep, 1)]
    dump(os.path.join(work, "work", "plan.json"), p)
    dropped = [s["n"] for s in p["slides"] if s["n"] in bad or not s.get("card")]
    print(f"final cards: {len(keep)}" + (f" (left out: {','.join(map(str, dropped))})" if dropped else ""))
    if len(keep) < MIN_FINAL or not any(s["kind"] == "verse" for s in keep):
        print(f"NOT ENOUGH: a post needs {MIN_FINAL} cards including Scripture")
        sys.exit(1)


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿]")


def caption_check(work):
    p = load(os.path.join(work, "work", "plan.json"))
    text = open(os.path.join(work, "work", "caption.txt"), encoding="utf-8").read().strip()
    rows = text.split("\n")
    tags = rows[-1].split()
    problems = []
    if len(rows[0]) >= 110:
        problems.append("the first line must be under 110 characters")
    if len(text) > 1000:
        problems.append("the caption must be under 1,000 characters")
    if "—" in text:
        problems.append("no em dashes")
    if "!" in text:
        problems.append("no exclamation marks")
    if not (3 <= len(tags) <= 5) or not all(t.startswith("#") for t in tags):
        problems.append("the last line must be 3 to 5 hashtags and nothing else")
    if any(t != t.lower() for t in tags):
        problems.append("hashtags must be lowercase")
    if [e for e in EMOJI.findall(text) if e != "\U0001F56F"]:
        problems.append("no emoji except the candle")
    refs = [s["ref"] for s in p.get("final", p["slides"]) if not s["ref"].startswith("@")]
    missing = [r for r in refs if r not in text]
    if missing:
        problems.append("add every reference on the slides: " + ", ".join(missing))
    print("caption ok" if not problems else "caption problems:\n  " + "\n  ".join(problems))
    sys.exit(1 if problems else 0)


def status(work):
    date = arg("--date")
    state = load(STATE, {})
    staged = os.path.join(ROOT, "world", date, "staged.json")
    if state.get("lastPostDate") == date:
        print("posted: today's 11 AM post already exists")
    elif os.path.exists(staged):
        print(f"staged: {len(load(staged)['slides'])} approved cards in world/{date}")
    else:
        print("fresh: plan and draw today's post")


def package(work):
    date, st = arg("--date"), arg("--status")
    if st not in ("posted", "failed"):
        sys.exit("--status must be posted or failed")
    state = load(STATE, {"postCount": 0, "lastPostDate": None, "history": []})
    if "--staged" in sys.argv:
        src = load(os.path.join(ROOT, "world", date, "staged.json"))
        slides, caption, theme, drawn = src["slides"], src["caption"], src.get("theme", "mixed"), src.get("drawn", 0)
        audio = src.get("audio") or audio_for(theme, state)
    else:
        p = load(os.path.join(work, "work", "plan.json"))
        slides, theme = p.get("final", []), p.get("theme")
        audio = p.get("audio")
        cap = os.path.join(work, "work", "caption.txt")
        caption = open(cap, encoding="utf-8").read().strip() if os.path.exists(cap) else ""
        drawn = sum(s.get("draws", 0) for s in p["slides"])
    post = {"id": date, "date": date, "kind": "world", "theme": theme,
            "title": slides[0]["text"] if slides else "Scripture in the world",
            "status": st, "permalink": arg("--permalink"), "mediaId": arg("--media-id"),
            "note": arg("--note", ""), "audio": audio, "caption": caption, "slides": slides,
            "cardUrls": [RAW.format(date=date, n=i) for i in range(1, len(slides) + 1)],
            "drawn": drawn, "cost": round(drawn * PRICE, 2)}
    dump(os.path.join(work, "out", "post.json"), post)
    if st == "posted":  # a failed day leaves no mark, so a rerun plans the same post
        state["postCount"] = state.get("postCount", 0) + 1
        state["lastPostDate"] = date
        if audio:
            state["usedAudio"] = (state.get("usedAudio", []) + [audio])[-12:]
        state["history"] = (state.get("history", []) + [{
            "date": date, "theme": theme,
            "lines": [s["line"] for s in slides if s.get("kind") != "cta"],
            "scenes": [s["scene"] for s in slides if s.get("kind") != "cta"]}])[-40:]
    dump(os.path.join(work, "out", "world-pointer.json"), state)
    print(f"packaged {date}: {st}, {len(slides)} cards, {drawn} drawings, about ${post['cost']:.2f}")


def sheet(work):
    p = load(os.path.join(work, "work", "plan.json"))
    cards = [s for s in p["slides"] if s.get("card")]
    tw, th, pad, cols = 360, 450, 14, 3
    rows = (len(cards) + cols - 1) // cols
    out = Image.new("RGB", (cols * tw + (cols + 1) * pad, rows * th + (rows + 1) * pad), (24, 21, 18))
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype(os.path.join(HERE, "assets", "fonts", "Inter_600SemiBold.ttf"), 22)
    except OSError:
        font = ImageFont.load_default()
    for i, s in enumerate(cards):
        x, y = pad + (i % cols) * (tw + pad), pad + (i // cols) * (th + pad)
        out.paste(Image.open(s["card"]).resize((tw, th), Image.LANCZOS), (x, y))
        draw.rounded_rectangle((x + 10, y + 10, x + 44, y + 44), 8, fill=(0, 0, 0))
        draw.text((x + 27, y + 27), str(s["n"]), font=font, fill=(255, 255, 255), anchor="mm")
    path = os.path.join(work, "work", "sheet.jpg")
    out.save(path, quality=88)
    print(path)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, work = sys.argv[1], os.path.abspath(sys.argv[2])
    {"status": status, "plan": plan, "generate": generate, "grade": grade, "verify": verify,
     "final": final, "caption-check": caption_check, "package": package, "sheet": sheet}[cmd](work)


if __name__ == "__main__":
    main()
