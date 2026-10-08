#!/usr/bin/env python3
"""
The 7 AM Instagram post: a different interactive format each day of the week.

  Mon  reveal  Swipe to reveal: a candid photo of young women of faith, mosaic to sharp,
               the verse revealed inside it (the photo is drawn each week)
  Tue  follow  Follow the line: a question, four answers, a line from each to its verse
  Wed  zoom    Swipe to zoom in: "You're THIS close to..." and a verse between the fingertips
  Thu  reel    Stop on your verse: 45 verses flash in a 7.5 second reel; hold to stop on one
  Fri  flip    Hold the dots and slide: a sunrise flipbook that ends on a morning verse
  Sat  reel    Stop on your verse again, with another photo and order
  Sun  dove    The traveling dove: a video carousel through a blessing, one verse per slide

Every verse comes from the pools in studio/morning, which tools/check_morning.py
proves word for word against the app's BSB before they are committed. Nothing
here edits Scripture; it only sets it in type.

    python3 tools/morning.py status  W --date D
    python3 tools/morning.py plan    W --date D [--format reveal|follow|zoom|reel|flip|dove]
    python3 tools/morning.py draw    W [--env-file PATH] [--redraw]   # Monday only: the photo
    python3 tools/morning.py render  W [--text-at X]          # Monday may move the verse band
    python3 tools/morning.py frames  W                        # stills to read back, W/work/check
    python3 tools/morning.py caption-check W
    python3 tools/morning.py media   W --date D               # public URLs, in slide order
    python3 tools/morning.py package W --date D --status posted|failed [--permalink U]
                                       [--media-id I] [--note T]

State lives in studio/state/morning-pointer.json and only advances in `package`,
so a re-run on the same day plans the same post.
"""

import base64
import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _ensure(modules):
    """The cloud sandbox ships without these, and its bare pip can serve another Python."""
    missing = []
    for mod, pkg in modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)


_ensure([("PIL", "pillow"), ("numpy", "numpy")])

from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from formats import common as c  # noqa: E402

POOLS = os.path.join(ROOT, "studio", "morning")
STATE = os.path.join(ROOT, "studio", "state", "morning-pointer.json")
BG_TALL = os.path.join(ROOT, "studio", "bg-tall")
MUSIC = os.path.join(ROOT, "studio", "audio", "strings.mp3")
MUSIC_START = 2.5
RAW = "https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/morning/{date}/{file}"
WEEK = ["reveal", "follow", "zoom", "reel", "flip", "reel", "dove"]     # Monday first
NAMES = {"reveal": "Swipe to reveal", "follow": "Follow the line", "zoom": "Swipe to zoom in",
         "reel": "Stop on your verse", "flip": "Hold the dots: sunrise", "dove": "The traveling dove"}
MODEL = os.environ.get("MORNING_MODEL", "gemini-3-pro-image")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PRICE = 0.134       # dollars per 2K drawing (ai.google.dev pricing, 2026-09)
REEL_VERSES = 45
BG_GAP = 12         # reels before a background may come back


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(path, default=None):
    if not os.path.exists(path) and default is not None:
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def pool(name):
    return load(os.path.join(POOLS, name))


def state():
    return load(STATE, {"lastPostId": None, "count": 0, "used": {}, "bg": [], "cast": 0})


def next_unused(ids, used):
    """The first entry not used in this cycle; when every one has been used, a new cycle."""
    for i in ids:
        if i not in used:
            return i, False
    return ids[0], True


# ------------------------------------------------------------------ status
def status(work):
    day = arg("--date")
    st = state()
    if st.get("lastPostId") == day or os.path.exists(os.path.join(ROOT, "morning", day, "post.json")):
        print("posted: today's 7 AM post already exists")
    else:
        print("fresh: plan and build today's post")


# -------------------------------------------------------------------- plan
def plan(work):
    day = arg("--date")
    date = dt.date.fromisoformat(day)
    fmt = arg("--format") or WEEK[date.weekday()]
    st = state()
    used = st.get("used", {})
    p = {"date": day, "format": fmt, "name": NAMES[fmt]}
    if fmt == "reveal":
        data = pool("monday.json")
        pick, reset = next_unused([m["id"] for m in data["moments"]], used.get("reveal", []))
        m = next(x for x in data["moments"] if x["id"] == pick)
        cast = data["cast"]
        k = st.get("cast", 0)
        people = [cast[(k + i) % len(cast)] for i in range(m["people"])]
        if len(people) == 1:
            who = f"The young woman is {people[0]}."
        else:
            who = "The friends: " + ", ".join(people[:-1]) + f" and {people[-1]}."
        prompt = f"{data['style']}\n\n{m['scene']}\n\nCast: {who}"
        p.update({"pick": pick, "reset": reset, "moment": m, "prompt": prompt, "people": len(people),
                  "refs": [m["ref"]], "title": m["text"]})
    elif fmt == "follow":
        data = pool("tuesday.json")
        pick, reset = next_unused([s["id"] for s in data["sets"]], used.get("follow", []))
        s = next(x for x in data["sets"] if x["id"] == pick)
        p.update({"pick": pick, "reset": reset, "set": s, "refs": [a["ref"] for a in s["answers"]],
                  "title": " ".join(s["title"]), "seed": date.toordinal()})
    elif fmt == "zoom":
        data = pool("wednesday.json")
        pick, reset = next_unused([e["ref"] for e in data["entries"]], used.get("zoom", []))
        e = next(x for x in data["entries"] if x["ref"] == pick)
        p.update({"pick": pick, "reset": reset, "entry": e, "hook": data["hook"], "refs": [e["ref"]],
                  "title": "You're THIS close to " + e["lead"].strip(".").strip()})
    elif fmt == "flip":
        data = pool("friday.json")
        pick, reset = next_unused([e["ref"] for e in data["entries"]], used.get("flip", []))
        e = next(x for x in data["entries"] if x["ref"] == pick)
        p.update({"pick": pick, "reset": reset, "entry": e, "heading": data["title"], "refs": [e["ref"]],
                  "title": "Sunrise, " + e["ref"]})
    elif fmt == "dove":
        data = pool("sunday.json")
        pick, reset = next_unused([b["ref"] for b in data["blessings"]], used.get("dove", []))
        b = next(x for x in data["blessings"] if x["ref"] == pick)
        p.update({"pick": pick, "reset": reset, "blessing": b, "cta": data["cta"], "refs": [b["ref"]],
                  "title": "A blessing, " + b["ref"]})
    elif fmt == "reel":
        verses = pool("reel.json")["verses"]
        rng = random.Random(date.toordinal())
        chosen = rng.sample(verses, min(REEL_VERSES, len(verses)))
        photos = sorted(f[:-4] for f in os.listdir(BG_TALL) if f.endswith(".jpg"))
        recent = st.get("bg", [])[-BG_GAP:]
        fresh = [x for x in photos if x not in recent] or photos
        bg = fresh[date.toordinal() % len(fresh)]
        p.update({"verses": chosen, "background": bg, "music": "strings", "refs": [v["ref"] for v in chosen],
                  "title": f"{len(chosen)} verses"})
    else:
        raise SystemExit(f"unknown format {fmt}")
    dump(os.path.join(work, "work", "plan.json"), p)
    print(f"{day}: {NAMES[fmt]} ({fmt})")
    if fmt == "reveal":
        print(f"moment: {p['pick']} ({p['moment']['layout']}), {p['people']} people; verse {p['moment']['ref']}")
        print("next: python3 tools/morning.py draw W")
    elif fmt == "reel":
        print(f"background {p['background']}, {len(p['verses'])} verses, music strings")
    else:
        print("verses: " + ", ".join(p["refs"]))


# -------------------------------------------------------------------- draw
def api_key():
    key = os.environ.get("GEMINI_API_KEY")
    env_file = arg("--env-file")
    if not key and env_file and os.path.exists(env_file):
        for line in open(env_file):
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key  # None in the cloud: the environment adds the header itself


def draw(work):
    p = load(os.path.join(work, "work", "plan.json"))
    if p["format"] != "reveal":
        print("nothing to draw: only Monday's post has a photo drawn")
        return
    m = p["moment"]
    staged = os.path.join(POOLS, "staged", f"{p['date']}-{p['pick']}.jpg")
    if os.path.exists(staged) and "--redraw" not in sys.argv:
        # a photo Ric approved in advance for this date and moment: use it, draw nothing
        Image.open(staged).convert("RGB").save(os.path.join(work, "work", "photo.png"))
        p["staged"] = True
        dump(os.path.join(work, "work", "plan.json"), p)
        print(f"staged: using the approved photo {os.path.relpath(staged, ROOT)}; nothing drawn")
        return
    body = {"contents": [{"parts": [{"text": p["prompt"]}]}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": m["aspect"], "imageSize": "2K"}}}
    headers = {"content-type": "application/json"}
    key = api_key()
    if key:
        headers["x-goog-api-key"] = key
    last = None
    for attempt in range(3):
        req = urllib.request.Request(API.format(model=MODEL), data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.load(r)
            parts = d.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            images = [x["inlineData"] for x in parts if "inlineData" in x and not x.get("thought")]
            if not images:
                last = f"no image ({d.get('candidates', [{}])[0].get('finishReason')})"
                continue
            raw = os.path.join(work, "work", "photo-raw.bin")
            with open(raw, "wb") as f:
                f.write(base64.b64decode(images[-1]["data"]))
            import world_run  # the 11 AM tool's border trim: the model sometimes draws a print border
            im = world_run.trim_border(Image.open(raw).convert("RGB"))
            im.save(os.path.join(work, "work", "photo.png"))
            p["drawings"] = p.get("drawings", 0) + 1
            dump(os.path.join(work, "work", "plan.json"), p)
            print(f"drawn: {os.path.join(work, 'work', 'photo.png')} ({im.width}x{im.height}); drawings so far {p['drawings']}")
            return
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # network hiccup: try again
            last = repr(e)
        time.sleep(6 * (attempt + 1))
    raise SystemExit(f"FAILED to draw: {last}")


# ------------------------------------------------------------------ render
def render(work):
    p = load(os.path.join(work, "work", "plan.json"))
    out = os.path.join(work, "out", "media")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    fmt = p["format"]
    items = []
    if fmt == "reveal":
        from formats import reveal
        m = p["moment"]
        photo = os.path.join(work, "work", "photo.png")
        if not os.path.exists(photo):
            raise SystemExit("no photo yet: run draw first")
        text_at = float(arg("--text-at", m.get("text_at", 0.46)))
        reveal.render(out, m["text"], m["ref"], photo, layout=m["layout"], text_at=text_at, col=m.get("col", 0.42))
        p["textAt"] = text_at
        items = [{"kind": "image", "file": f"{k}.jpg"} for k in range(1, 9)]
    elif fmt == "follow":
        from formats import follow_line
        s = p["set"]
        answers = [{"label": a["label"], "icon": a["icon"], "color": c.HUES[a["color"]]} for a in s["answers"]]
        verses = {a["label"]: {"text": a["text"], "ref": a["ref"], "for": a["for"]} for a in s["answers"]}
        paths = follow_line.render(out, answers, verses, seed=p["seed"], title=tuple(s["title"]))
        items = [{"kind": "image", "file": os.path.basename(x)} for x in paths]
    elif fmt == "zoom":
        from formats import zoom
        e = p["entry"]
        paths = zoom.render(out, e["text"], e["ref"], lead=e["lead"], hook=tuple(p["hook"]))
        items = [{"kind": "image", "file": os.path.basename(x)} for x in paths]
    elif fmt == "flip":
        from formats import flipbook
        e = p["entry"]
        paths = flipbook.render_sunrise(out, e["text"], e["ref"], title=p["heading"])
        items = [{"kind": "image", "file": os.path.basename(x)} for x in paths]
    elif fmt == "dove":
        _ensure([("imageio_ffmpeg", "imageio-ffmpeg")]) if not shutil.which("ffmpeg") else None
        from formats import traveling
        b = p["blessing"]
        paths = traveling.render_blessing(out, b["hook"], b["slides"], b["ref"], p["cta"])
        items = [{"kind": "video", "file": os.path.basename(x)} for x in paths]
    elif fmt == "reel":
        _ensure([("imageio_ffmpeg", "imageio-ffmpeg")]) if not shutil.which("ffmpeg") else None
        from formats import reel
        photo = os.path.join(BG_TALL, f"{p['background']}.jpg")
        reel.render(os.path.join(out, "reel.mp4"), [(v["text"], v["ref"]) for v in p["verses"]], photo,
                    MUSIC, music_start=MUSIC_START)
        reel.cover(os.path.join(out, "cover.jpg"), photo)
        items = [{"kind": "reel", "file": "reel.mp4", "cover": "cover.jpg"}]
    p["items"] = items
    dump(os.path.join(work, "work", "plan.json"), p)
    total = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out))
    print(f"rendered {len(items)} item(s) for {NAMES[fmt]} in {out} ({total / 1e6:.1f} MB)")
    for it in items:
        print(" ", it["kind"], it["file"])


# ------------------------------------------------------------------ frames
def _ffmpeg():
    from formats.reel import ffmpeg_bin
    return ffmpeg_bin()


def _grab(video, seconds, out_jpg):
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{seconds:.2f}", "-i", video,
                    "-frames:v", "1", "-q:v", "3", out_jpg], check=True)


def _duration(video):
    r = subprocess.run([_ffmpeg(), "-i", video], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "Duration:" in line:
            h, mi, se = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(mi) * 60 + float(se)
    return 0.0


def frames(work):
    """The stills Claude reads back in the routine: few, chosen to show every word that will post."""
    p = load(os.path.join(work, "work", "plan.json"))
    media = os.path.join(work, "out", "media")
    check = os.path.join(work, "work", "check")
    shutil.rmtree(check, ignore_errors=True)
    os.makedirs(check)
    fmt, picks = p["format"], []
    if fmt == "reveal":
        picks = ["1.jpg", "8.jpg"]
    elif fmt == "follow":
        picks = ["1.jpg", "4.jpg", "5.jpg", "6.jpg", "7.jpg", "8.jpg"]
    elif fmt == "zoom":
        picks = ["1.jpg", "5.jpg"]
    elif fmt == "flip":
        picks = ["1.jpg", "10.jpg"]
    for f in picks:
        shutil.copy(os.path.join(media, f), os.path.join(check, f))
    if fmt == "reel":
        reel_mp4 = os.path.join(media, "reel.mp4")
        for k, t in enumerate((0.4, 3.6, 7.0), 1):
            _grab(reel_mp4, t, os.path.join(check, f"reel-{k}.jpg"))
        shutil.copy(os.path.join(media, "cover.jpg"), os.path.join(check, "cover.jpg"))
    if fmt == "dove":
        vids = sorted((f for f in os.listdir(media) if f.endswith(".mp4")), key=lambda f: int(f.split(".")[0]))
        for f in vids:
            d = _duration(os.path.join(media, f))
            when = d - 0.05 if f == vids[-1] else d * 0.5
            _grab(os.path.join(media, f), when, os.path.join(check, f.replace(".mp4", "-frame.jpg")))
    names = sorted(os.listdir(check))
    print(f"{len(names)} stills to read in {check}:")
    for n in names:
        print(" ", os.path.join(check, n))


# ------------------------------------------------------------ caption-check
def caption_check(work):
    p = load(os.path.join(work, "work", "plan.json"))
    path = os.path.join(work, "work", "caption.txt")
    if not os.path.exists(path):
        raise SystemExit(f"write {path} first")
    t = open(path, encoding="utf-8").read().strip()
    lines = t.splitlines()
    problems = []
    if len(lines[0]) >= 110:
        problems.append(f"line 1 is {len(lines[0])} characters; keep it under 110")
    if len(t) > 1200:
        problems.append(f"caption is {len(t)} characters; keep it under 1,200")
    if "—" in t:
        problems.append("an em dash; use a comma, a colon or a full stop")
    if "!" in t:
        problems.append("an exclamation mark; Chasten's voice is warm and calm")
    tags = lines[-1].split()
    if not tags or not all(x.startswith("#") for x in tags) or not 3 <= len(tags) <= 5:
        problems.append("the last line must be three to five hashtags and nothing else")
    elif any(x != x.lower() for x in tags):
        problems.append("hashtags must be lowercase")
    if "\U0001F56F️ Chasten is a free Bible app. chasten.ai" not in t:
        problems.append("missing the sign-off line")
    if p["format"] != "reel":
        for r in p["refs"]:
            if r not in t:
                problems.append(f"missing the reference {r}")
    else:
        if "BSB" not in t:
            problems.append("say the verses are from the BSB")
    for x in problems:
        print("PROBLEM:", x)
    print("caption ok" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


# ------------------------------------------------------------------- media
def media(work):
    p = load(os.path.join(work, "work", "plan.json"))
    day = arg("--date") or p["date"]
    out = {"type": "reel" if p["format"] == "reel" else ("video-carousel" if p["format"] == "dove" else "carousel"),
           "items": []}
    for it in p["items"]:
        entry = {"kind": it["kind"], "url": RAW.format(date=day, file=it["file"])}
        if it.get("cover"):
            entry["cover"] = RAW.format(date=day, file=it["cover"])
        out["items"].append(entry)
    print(json.dumps(out, indent=1))


# ----------------------------------------------------------------- package
def package(work):
    p = load(os.path.join(work, "work", "plan.json"))
    day = arg("--date") or p["date"]
    status_ = arg("--status", "failed")
    caption_path = os.path.join(work, "work", "caption.txt")
    caption = open(caption_path, encoding="utf-8").read().strip() if os.path.exists(caption_path) else ""
    post = {"date": day, "format": p["format"], "name": p["name"], "title": p.get("title", ""), "status": status_,
            "permalink": arg("--permalink"), "mediaId": arg("--media-id"), "note": arg("--note", ""),
            "refs": p["refs"] if p["format"] != "reel" else [], "verseCount": len(p["refs"]),
            "items": [it["file"] for it in p.get("items", [])], "caption": caption}
    if p["format"] == "reveal":
        post.update({"moment": p["pick"], "drawn": p.get("drawings", 0), "cost": round(PRICE * p.get("drawings", 0), 2)})
    if p["format"] == "reel":
        post.update({"background": p["background"], "music": p["music"]})
    st = state()
    st["lastPostId"] = day
    st["count"] = st.get("count", 0) + 1
    used = st.setdefault("used", {})
    if p.get("pick") is not None:
        key = p["format"]
        if p.get("reset"):
            used[key] = []
        used.setdefault(key, []).append(p["pick"])
    if p["format"] == "reel":
        st.setdefault("bg", []).append(p["background"])
        st["bg"] = st["bg"][-40:]
    if p["format"] == "reveal":
        st["cast"] = st.get("cast", 0) + p["people"]
    dump(os.path.join(work, "out", "post.json"), post)
    dump(os.path.join(work, "out", "morning-pointer.json"), st)
    print(f"packaged {day}: {status_}, {p['name']}, {len(post['items'])} item(s)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, work = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(work, "work"), exist_ok=True)
    {"status": status, "plan": plan, "draw": draw, "render": render, "frames": frames,
     "caption-check": caption_check, "media": media, "package": package}[cmd](work)
