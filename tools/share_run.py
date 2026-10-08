#!/usr/bin/env python3
"""
The 11 AM share days: Wednesday, Thursday and Sunday post a share format instead
of "Scripture in the world" (tools/world_run.py runs the other four days).

  Wed  thought   "Saw this and thought of you": a photo of a friend smiling at you,
                 then a verse card with a line of ours and "Send this to the one you thought of."
  Thu  person    "Send this to your person": two lines of a conversation over two photos
                 of the same couple (the second drawn from the first, so it is the same
                 two people), then the verse that answers them
  Sun  blessing  "A blessing for your week" (on a month's first Sunday "Hello, <Month>."):
                 a cozy seasonal still life with a blessing line of ours, then the verse card

The photos are drawn by gemini-3-pro-image; every word on a slide is set in code,
and every verse comes from studio/share, proved word for word against the app's BSB
by tools/check_morning.py. Posts land in world/<date>, beside the other 11 AM posts.

    python3 tools/share_run.py status  W --date D
    python3 tools/share_run.py plan    W --date D [--kind thought|person|blessing]
    python3 tools/share_run.py draw    W [--only 1,2] [--env-file PATH]
    python3 tools/share_run.py render  W [--place top|bottom]
    python3 tools/share_run.py frames  W
    python3 tools/share_run.py caption-check W
    python3 tools/share_run.py media   W --date D
    python3 tools/share_run.py package W --date D --status posted|failed [--permalink U] [--media-id I] [--note T]
"""

import base64
import datetime as dt
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

import morning as m  # helpers: arg, load, dump, next_unused, api_key, the Pillow and numpy guard
from formats import share as sh

ROOT, POOLS = m.ROOT, os.path.join(m.ROOT, "studio", "share")
STATE = os.path.join(ROOT, "studio", "state", "share-pointer.json")
RAW = "https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/world/{date}/{file}"
from world_run import SHARE_DAYS as DAYS                  # weekday -> kind
NAMES = {"thought": "Saw this and thought of you", "person": "Send this to your person", "blessing": "A blessing for your week"}
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
arg, load, dump = m.arg, m.load, m.dump


def state():
    return load(STATE, {"lastPostId": None, "count": 0, "used": {}, "turn": {}})


def status(work):
    day = arg("--date")
    if state().get("lastPostId") == day or os.path.exists(os.path.join(ROOT, "world", day, "post.json")):
        print("posted: today's 11 AM post already exists")
    else:
        print("fresh: plan and build today's post")


def plan(work):
    day = arg("--date")
    date = dt.date.fromisoformat(day)
    kind = arg("--kind") or DAYS.get(date.weekday())
    if not kind:
        raise SystemExit(f"{day} is not a share day; run tools/world_run.py")
    st, used, turn = state(), state().get("used", {}), state().get("turn", {})
    data = load(os.path.join(POOLS, {"thought": "wednesday.json", "person": "thursday.json", "blessing": "sunday.json"}[kind]))
    p = {"date": day, "kind": kind, "name": NAMES[kind], "cta": data["cta"]}
    if kind == "thought":
        pick, reset = m.next_unused([e["ref"] for e in data["entries"]], used.get(kind, []))
        e = next(x for x in data["entries"] if x["ref"] == pick)
        scene = data["scenes"][turn.get("scene", 0) % len(data["scenes"])]
        p.update({"pick": pick, "reset": reset, "entry": e, "hook": data["hook"], "title": data["hook"],
                  "prompts": [f"{data['style']}\n\n{scene} {data['framing']}"]})
    elif kind == "person":
        pick, reset = m.next_unused([e["ref"] for e in data["dialogues"]], used.get(kind, []))
        e = next(x for x in data["dialogues"] if x["ref"] == pick)
        couple = data["couples"][turn.get("couple", 0) % len(data["couples"])]
        a, b = data["moments"][turn.get("moment", 0) % len(data["moments"])]
        base = f"{data['style']}\n\nThe couple: {couple}."
        p.update({"pick": pick, "reset": reset, "entry": e, "title": f"“{e['a']}”", "basedOn": {"2": 1},
                  "prompts": [f"{base} Moment: {a}. {data['framing']}",
                              f"{data['sequel']}\n\n{base} Moment: {b}. {data['framing']}"]})
    else:
        pick, reset = m.next_unused([e["ref"] for e in data["entries"]], used.get(kind, []))
        e = next(x for x in data["entries"] if x["ref"] == pick)
        scenes = data["scenes"][SEASONS[date.month]]
        scene = scenes[turn.get("scene", 0) % len(scenes)]
        line = data["lines"][turn.get("line", 0) % len(data["lines"])]
        title = f"Hello, {date.strftime('%B')}." if date.day <= 7 else "A blessing for your week"
        p.update({"pick": pick, "reset": reset, "entry": e, "heading": title, "line": line, "title": title,
                  "prompts": [f"{data['style']}\n\n{scene}. {data['framing']}"]})
    p["refs"] = [p["entry"]["ref"]]
    dump(os.path.join(work, "work", "plan.json"), p)
    print(f"{day}: {NAMES[kind]} ({kind}); verse {p['entry']['ref']}; {len(p['prompts'])} photo(s) to draw")


def _draw_one(prompt, out_png, refs=()):
    parts = []
    for r in refs:  # a photo this one must match (the same couple), sent ahead of the words
        im = m.Image.open(r).convert("RGB")
        im.thumbnail((1024, 1024))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
    parts.append({"text": prompt})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5", "imageSize": "2K"}}}
    headers = {"content-type": "application/json"}
    key = m.api_key()
    if key:
        headers["x-goog-api-key"] = key
    last = None
    for attempt in range(3):
        req = urllib.request.Request(m.API.format(model=m.MODEL), data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.load(r)
            parts = d.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            images = [x["inlineData"] for x in parts if "inlineData" in x and not x.get("thought")]
            if not images:
                last = f"no image ({d.get('candidates', [{}])[0].get('finishReason')})"
                continue
            raw = out_png + ".bin"
            with open(raw, "wb") as f:
                f.write(base64.b64decode(images[-1]["data"]))
            import world_run
            world_run.trim_border(m.Image.open(raw).convert("RGB")).save(out_png)
            os.remove(raw)
            return None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # network hiccup: try again
            last = repr(e)
        time.sleep(6 * (attempt + 1))
    return last


def draw(work):
    p = load(os.path.join(work, "work", "plan.json"))
    only = {int(x) for x in (arg("--only") or "").split(",") if x}
    based = {int(k): v for k, v in p.get("basedOn", {}).items()}
    for n, src in based.items():  # a photo drawn from another is redrawn whenever its source is
        if only and src in only:
            only.add(n)
    for n, prompt in enumerate(p["prompts"], 1):
        if only and n not in only:
            continue
        refs = [os.path.join(work, "work", f"photo-{based[n]}.png")] if n in based else []
        if refs and not os.path.exists(refs[0]):
            print(f"photo {n}: FAILED its source photo {based[n]} is missing")
            continue
        err = _draw_one(prompt, os.path.join(work, "work", f"photo-{n}.png"), refs)
        p["drawings"] = p.get("drawings", 0) + 1
        print(f"photo {n}: " + (f"FAILED {err}" if err else os.path.join(work, "work", f"photo-{n}.png")))
    dump(os.path.join(work, "work", "plan.json"), p)


def render(work):
    p = load(os.path.join(work, "work", "plan.json"))
    out = os.path.join(work, "out", "media")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    p["place"] = arg("--place") or p.get("place", "top")
    e, photo, place = p["entry"], (lambda n: os.path.join(work, "work", f"photo-{n}.png")), p["place"]
    if p["kind"] == "thought":
        sh.photo_slide(photo(1), os.path.join(out, "1.jpg"), "hook", p["hook"], place=place)
        sh.verse_card(os.path.join(out, "2.jpg"), e["text"], e["ref"], e["line"], p["cta"])
    elif p["kind"] == "person":
        sh.photo_slide(photo(1), os.path.join(out, "1.jpg"), "quote", e["a"], place=place)
        sh.photo_slide(photo(2), os.path.join(out, "2.jpg"), "quote", e["b"], place=place)
        sh.verse_card(os.path.join(out, "3.jpg"), e["text"], e["ref"], None, p["cta"])
    else:  # the cue keeps our blessing line from reading as the verse itself
        sh.photo_slide(photo(1), os.path.join(out, "1.jpg"), "title", p["heading"], p["line"], cue="Swipe for the verse")
        sh.verse_card(os.path.join(out, "2.jpg"), e["text"], e["ref"], None, p["cta"])
    p["items"] = sorted(os.listdir(out), key=lambda f: int(f.split(".")[0]))
    dump(os.path.join(work, "work", "plan.json"), p)
    print(f"rendered {len(p['items'])} slides for {p['name']} in {out}")


def frames(work):
    p = load(os.path.join(work, "work", "plan.json"))
    check = os.path.join(work, "work", "check")
    shutil.rmtree(check, ignore_errors=True)
    shutil.copytree(os.path.join(work, "out", "media"), check)
    print(f"{len(p['items'])} slides to read in {check}:")
    for f in p["items"]:
        print(" ", os.path.join(check, f))


def caption_check(work):
    m.caption_check(work)  # the same rules; the plan's refs must appear


def media(work):
    p = load(os.path.join(work, "work", "plan.json"))
    day = arg("--date") or p["date"]
    print(json.dumps({"type": "carousel", "items": [{"kind": "image", "url": RAW.format(date=day, file=f)} for f in p["items"]]}, indent=1))


def package(work):
    p = load(os.path.join(work, "work", "plan.json"))
    day = arg("--date") or p["date"]
    st_ = arg("--status", "failed")
    cap = os.path.join(work, "work", "caption.txt")
    caption = open(cap, encoding="utf-8").read().strip() if os.path.exists(cap) else ""
    post = {"id": day, "date": day, "kind": "share", "share": p["kind"], "name": p["name"], "title": p.get("title", ""),
            "status": st_, "permalink": arg("--permalink"), "mediaId": arg("--media-id"), "note": arg("--note", ""),
            "refs": p["refs"], "items": p.get("items", []), "caption": caption,
            "drawn": p.get("drawings", 0), "cost": round(m.PRICE * p.get("drawings", 0), 2)}
    s = state()
    if st_ == "posted":  # like the world post: a failed day leaves no mark, so a rerun plans the same post
        s["lastPostId"], s["count"] = day, s.get("count", 0) + 1
        used = s.setdefault("used", {})
        if p.get("reset"):
            used[p["kind"]] = []
        used.setdefault(p["kind"], []).append(p["pick"])
        t = s.setdefault("turn", {})
        for k in {"thought": ["scene"], "person": ["couple", "moment"], "blessing": ["scene", "line"]}[p["kind"]]:
            t[k] = t.get(k, 0) + 1
    dump(os.path.join(work, "out", "post.json"), post)
    dump(os.path.join(work, "out", "share-pointer.json"), s)
    print(f"packaged {day}: {st_}, {p['name']}, {len(post['items'])} slides, {post['drawn']} drawings")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, work = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(work, "work"), exist_ok=True)
    {"status": status, "plan": plan, "draw": draw, "render": render, "frames": frames,
     "caption-check": caption_check, "media": media, "package": package}[cmd](work)
