#!/usr/bin/env python3
"""
Daily orchestration for Chasten's Instagram verse posts.

The scheduled run pulls a few documents out of the dashboard's database into
a work directory, then calls this script, which does everything deterministic:

  python3 ig_run.py bootstrap WORKDIR     # unpack fonts, wordmarks from db docs
  python3 ig_run.py plan WORKDIR          # choose set/recipe/inks/backgrounds
  python3 ig_run.py render WORKDIR        # render the 3 cards (JPEG, 1080x1350)
  python3 ig_run.py package WORKDIR       # write db docs: state, post, card chunks
  python3 ig_run.py preview WORKDIR       # small inline previews for the email

WORKDIR layout (what read_db --out_dir produces):
  db/config/settings.json
  db/state/pointer.json
  db/verses/sets.json
  db/library/backgrounds.json
  db/bg/<id>.json                         # only the ones this run needs
  db/fonts/<name>.json, db/assets/<name>.json
Outputs:
  work/plan.json, work/card1.jpg .. card3.jpg, work/preview1.jpg ..,
  out/<collection>/<doc>.json ready for write_db --file_path

Every choice is a function of the pointer state, so a re-run on the same day
produces the same post (the pointer only advances in `package`).
"""

import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECIPES = ["photo-lead", "night", "photo", "paper"]
INKS = ["amber", "apricot", "rose", "sky", "sage", "lavender"]
CHUNK = 190_000  # bytes of base64 per document, well under the 256 KiB cap


def load(path, default=None):
    if not os.path.exists(path):
        if default is not None:
            return default
        raise SystemExit(f"missing {path}")
    with open(path) as f:
        return json.load(f)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def b64_to_file(doc_or_parts, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(doc_or_parts, list):
        data = "".join(p["b64"] for p in sorted(doc_or_parts, key=lambda p: p["part"]))
    else:
        data = doc_or_parts["b64"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))


def file_to_docs(path, meta):
    """One or more docs holding a file as base64 chunks."""
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    docs = []
    for i, p in enumerate(parts):
        docs.append(dict(meta, part=i, parts=len(parts), b64=p))
    return docs


# ------------------------------------------------------------- bootstrap
def bootstrap(work):
    """Assets ship in the repo next to this file. Just verify they are there."""
    fonts_dir = os.path.join(HERE, "assets", "fonts")
    img_dir = os.path.join(HERE, "assets", "img")
    for d in (fonts_dir, img_dir):
        if not os.path.isdir(d) or not os.listdir(d):
            raise SystemExit(f"missing assets: {d}")
    print("bootstrap ok:", sorted(os.listdir(fonts_dir)), sorted(os.listdir(img_dir)))


# ------------------------------------------------------------------ plan
def choose_set(sets, pointer):
    """The next set whose verses have not appeared recently; wraps around."""
    recent = set(pointer.get("recentVerses", []))
    used = set(pointer.get("usedSets", []))
    n = len(sets)
    start = pointer.get("nextSetIndex", 0) % n
    order = [(start + i) % n for i in range(n)]
    for idx in order:
        if idx in used:
            continue
        refs = [v["ref"] for v in sets[idx]["verses"]]
        if not any(r in recent for r in refs):
            return idx
    # everything used: start a new cycle, only avoiding the recency window
    for idx in order:
        refs = [v["ref"] for v in sets[idx]["verses"]]
        if not any(r in recent for r in refs):
            return idx, True
    return start


def choose_backgrounds(library, pointer, count, want_light=None):
    used = set(pointer.get("usedBackgrounds", []))
    pool = [b for b in library if b["id"] not in used]
    if len(pool) < count:
        pool = list(library)  # library exhausted: start over
        used = set()
    # walk the library in a fixed shuffled order seeded by post count so a
    # re-run picks the same photos
    import random
    rnd = random.Random(1000 + pointer.get("postCount", 0))
    rnd.shuffle(pool)
    # first background leads; the rest prefer the same tonal family so a
    # three-photo carousel feels like one set
    lead = pool[0]
    rest = [b for b in pool[1:] if b["light"] == lead["light"]] + [b for b in pool[1:] if b["light"] != lead["light"]]
    return [lead] + rest[:count - 1]


def plan(work):
    settings = load(os.path.join(work, "db", "config", "settings.json"))
    pointer = load(os.path.join(work, "db", "state", "pointer.json"), {"nextSetIndex": 0, "postCount": 0, "usedSets": [], "usedBackgrounds": [], "recentVerses": []})
    sets = load(os.path.join(work, "db", "verses", "sets.json"))["sets"]
    library = load(os.path.join(work, "db", "library", "backgrounds.json"))["items"]

    today = os.environ.get("CHASTEN_DATE") or dt.date.today().isoformat()
    post_count = pointer.get("postCount", 0)
    picked = choose_set(sets, pointer)
    new_cycle = False
    if isinstance(picked, tuple):
        picked, new_cycle = picked
    verse_set = sets[picked]
    recipe = settings.get("recipes", RECIPES)[post_count % len(settings.get("recipes", RECIPES))]
    ink = INKS[post_count % len(INKS)]

    n_photos = {"photo-lead": 1, "photo": 3}.get(recipe, 0)
    backgrounds = choose_backgrounds(library, pointer, n_photos) if n_photos else []

    cards = []
    for i, v in enumerate(verse_set["verses"][:3]):
        style = {"photo-lead": ["photo", "paper", "paper"], "night": ["night"] * 3, "photo": ["photo"] * 3, "paper": ["paper"] * 3}[recipe][i]
        card = {
            "style": style, "ref": f"{v['book']} {v['chapter']}", "verse": v["verse"], "text": v["text"],
            "translation": settings.get("translation", "BSB"), "fullRef": v["ref"],
            "out": os.path.join(work, "work", f"card{i + 1}.jpg"),
        }
        if style == "photo":
            bg = backgrounds[[c["style"] for c in cards].count("photo")]
            card.update({"photo": os.path.join(work, "work", "bg", f"{bg['id']}.jpg"), "photo_ink": bg["ink"], "scrim": bg["scrim"], "light_ink": bg["light"], "bgId": bg["id"], "bgCredit": bg.get("credit", "")})
        else:
            card["ink"] = ink
        cards.append(card)

    # Slide four: the closing call to action, inheriting today's ink and ground
    # so it reads as part of the set rather than an advert bolted on the end.
    cards.append({
        "style": "cta",
        "ground": "night" if recipe == "night" else "paper",
        "ink": ink,
        "text": settings.get("ctaText", "Follow @chasten.app for Scripture like this every day."),
        "out": os.path.join(work, "work", f"card{len(cards) + 1}.jpg"),
    })

    plan_doc = {
        "date": today, "postId": today, "setIndex": picked, "newCycle": new_cycle, "recipe": recipe, "ink": ink,
        "title": verse_set["title"], "kind": verse_set["kind"],
        "verses": verse_set["verses"][:3], "backgrounds": [b["id"] for b in backgrounds],
        "cards": cards, "postCount": post_count,
    }
    dump(os.path.join(work, "work", "plan.json"), plan_doc)
    print(json.dumps({k: plan_doc[k] for k in ["date", "recipe", "ink", "title", "kind", "backgrounds"]}))
    print("verses:", [v["ref"] for v in plan_doc["verses"]])
    print("need bg docs:", plan_doc["backgrounds"])


# ---------------------------------------------------------------- render
def render(work):
    plan_doc = load(os.path.join(work, "work", "plan.json"))
    repo = os.environ.get("CHASTEN_REPO") or os.path.dirname(os.path.abspath(work))
    for bid in plan_doc["backgrounds"]:
        src = os.path.join(repo, "studio", "bg", f"{bid}.jpg")
        if not os.path.exists(src):
            raise SystemExit(f"missing background {src}")
        dst = os.path.join(work, "work", "bg", f"{bid}.jpg")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    spec = {"cards": plan_doc["cards"]}
    spec_path = os.path.join(work, "work", "spec.json")
    dump(spec_path, spec)
    subprocess.run([sys.executable, os.path.join(HERE, "chasten_cards.py"), "batch", spec_path], check=True)
    # JPEG for Instagram (the API rejects PNG); re-save at a feed-friendly quality
    from PIL import Image
    for c in plan_doc["cards"]:
        im = Image.open(c["out"]).convert("RGB")
        im.save(c["out"], "JPEG", quality=88, optimize=True, progressive=True)
        print(c["out"], os.path.getsize(c["out"]), "bytes")


def preview(work):
    from PIL import Image
    plan_doc = load(os.path.join(work, "work", "plan.json"))
    outs = []
    for i, c in enumerate(plan_doc["cards"], start=1):
        im = Image.open(c["out"]).convert("RGB").resize((270, 338), Image.LANCZOS)
        p = os.path.join(work, "work", f"preview{i}.jpg")
        im.save(p, "JPEG", quality=58, optimize=True)
        b64 = base64.b64encode(open(p, "rb").read()).decode()
        with open(p + ".b64", "w") as f:
            f.write(b64)
        outs.append((p, os.path.getsize(p), len(b64)))
    print(outs)


# --------------------------------------------------------------- package
def package(work):
    """Write the documents the run pushes back: post record, card chunks, the
    advanced pointer. Caption is added by the run (work/caption.txt) if present."""
    plan_doc = load(os.path.join(work, "work", "plan.json"))
    pointer = load(os.path.join(work, "db", "state", "pointer.json"), {"nextSetIndex": 0, "postCount": 0, "usedSets": [], "usedBackgrounds": [], "recentVerses": []})
    library = load(os.path.join(work, "db", "library", "backgrounds.json"))["items"]
    caption_path = os.path.join(work, "work", "caption.txt")
    caption = open(caption_path).read().strip() if os.path.exists(caption_path) else ""
    status = load(os.path.join(work, "work", "status.json"), {"status": "ready", "permalink": None, "mediaId": None})

    out = os.path.join(work, "out")
    post_id = plan_doc["postId"]
    card_docs = []
    for i, c in enumerate(plan_doc["cards"], start=1):
        docs = file_to_docs(c["out"], {"postId": post_id, "index": i, "mime": "image/jpeg", "style": c["style"], "ref": c.get("fullRef", "")})
        for d in docs:
            name = f"{post_id}-{i}" if d["parts"] == 1 else f"{post_id}-{i}-{d['part']}"
            dump(os.path.join(out, "cards", f"{name}.json"), d)
            card_docs.append({"doc": name, "part": d["part"], "parts": d["parts"], "index": i})

    post_doc = {
        "id": post_id, "date": plan_doc["date"], "recipe": plan_doc["recipe"], "ink": plan_doc["ink"],
        "title": plan_doc["title"], "kind": plan_doc["kind"],
        "verses": [{"ref": v["ref"], "text": v["text"]} for v in plan_doc["verses"]],
        "styles": [c["style"] for c in plan_doc["cards"]],
        "backgrounds": [{"id": c.get("bgId"), "credit": c.get("bgCredit")} for c in plan_doc["cards"] if c.get("bgId")],
        "caption": caption, "cards": card_docs,
        "status": status.get("status", "ready"), "permalink": status.get("permalink"), "mediaId": status.get("mediaId"),
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    dump(os.path.join(out, "posts", f"{post_id}.json"), post_doc)

    # advance the pointer
    used_sets = list(pointer.get("usedSets", []))
    if plan_doc.get("newCycle"):
        used_sets = []
    used_sets.append(plan_doc["setIndex"])
    used_bg = list(pointer.get("usedBackgrounds", []))
    if plan_doc["backgrounds"] and len(set(used_bg) | set(plan_doc["backgrounds"])) >= len(library):
        used_bg = []
    used_bg += plan_doc["backgrounds"]
    recent = list(pointer.get("recentVerses", [])) + [v["ref"] for v in plan_doc["verses"]]
    recent = recent[-int(os.environ.get("CHASTEN_RECENT_WINDOW", 126)):]  # ~42 posts x 3 verses
    new_pointer = {
        "nextSetIndex": (plan_doc["setIndex"] + 1), "postCount": plan_doc["postCount"] + 1,
        "usedSets": used_sets, "usedBackgrounds": used_bg, "recentVerses": recent,
        "lastPostId": post_id, "lastRunAt": post_doc["createdAt"],
    }
    dump(os.path.join(out, "state", "pointer.json"), new_pointer)
    # group the writes into batches under the 1 MB request limit, cards first,
    # the post record and the pointer last so a half-finished run never
    # advances the pointer without its cards
    writes = []
    for root, _, files in os.walk(out):
        for fn in sorted(files):
            rel = os.path.relpath(os.path.join(root, fn), out)
            coll, doc = os.path.split(rel)
            writes.append({"op": "set", "collection": coll, "doc_id": doc[:-5], "file_path": os.path.join(out, rel)})
    order = {"cards": 0, "posts": 1, "state": 2}
    writes.sort(key=lambda w: (order.get(w["collection"], 9), w["doc_id"]))
    batches, cur, size = [], [], 0
    for w in writes:
        s = os.path.getsize(w["file_path"]) + 300
        if cur and size + s > 850_000:
            batches.append(cur)
            cur, size = [], 0
        cur.append(w)
        size += s
    if cur:
        batches.append(cur)
    dump(os.path.join(work, "work", "writes.json"), {"batches": batches})
    for i, b in enumerate(batches):
        print(f"BATCH {i + 1}/{len(batches)}:", json.dumps(b, separators=(",", ":")))


if __name__ == "__main__":
    cmd, work = sys.argv[1], os.path.abspath(sys.argv[2])
    {"bootstrap": bootstrap, "plan": plan, "render": render, "package": package, "preview": preview}[cmd](work)
