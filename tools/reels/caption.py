#!/usr/bin/env python3
"""Write the caption for a finished Moment, inside the build Action.

Claude (Sonnet 4.5, through Replicate, since that key is the one the Action
holds) writes it from the story metadata; the mechanical rules are checked
here, with one rewrite allowed, and a plain caption built from the metadata
stands in if the model cannot satisfy them. reels/<day>/caption.md always
exists when this returns, so the Slack message never waits on a caption.

    python tools/reels/caption.py reels/2026-09-07
"""
import json, os, re, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN = os.environ.get("REPLICATE_API_TOKEN", "").strip()
MODEL = "anthropic/claude-4.5-sonnet"
SIGNOFF = "Chasten is a free Bible app. chasten.ai"
CANDLE = "\U0001f56f"


def api(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                                          "Prefer": "wait=60"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def ask(system, prompt):
    p = api(f"https://api.replicate.com/v1/models/{MODEL}/predictions",
            {"input": {"system_prompt": system, "prompt": prompt, "max_tokens": 1024}})
    t0 = time.time()
    while p.get("status") in ("starting", "processing"):
        time.sleep(5); p = api(f"https://api.replicate.com/v1/predictions/{p['id']}")
        if time.time() - t0 > 300: raise RuntimeError("caption model timed out")
    if p.get("status") != "succeeded": raise RuntimeError(f"caption model failed: {str(p.get('error'))[:200]}")
    out = p.get("output") or []
    return ("".join(out) if isinstance(out, list) else str(out)).strip()


def chapter_of(meta):
    m = re.match(r"Read (.+?) in Chasten", meta.get("cta", ""))
    if m: return m.group(1)
    return re.sub(r":\d+.*$", "", meta["verses"][0]["ref"])


def problems(c, ref):
    lines = [l for l in c.strip().split("\n")]
    hook, tags = lines[0].strip(), lines[-1].split()
    out = []
    if len(hook) >= 110: out.append("the first line must be under 110 characters")
    if "—" in c or "–" in c: out.append("no em dashes or en dashes anywhere")
    if "!" in c: out.append("no exclamation marks")
    if len(c) > 1200: out.append("the whole caption must be under 1200 characters")
    if not (12 <= len(tags) <= 15) or not all(t.startswith("#") and t == t.lower() for t in tags):
        out.append("the last line must be 12 to 15 lowercase hashtags and nothing else")
    if SIGNOFF not in c: out.append(f"the sign-off line '{SIGNOFF}' is missing")
    if ref not in c: out.append(f"the references line with {ref} is missing")
    if any(0x1F300 <= ord(ch) <= 0x1FAFF and ch != CANDLE for ch in c): out.append("no emoji except the candle")
    return out


def fallback(meta, cfg):
    ref, chapter = meta["verses"][0]["ref"], chapter_of(meta)
    tags = cfg["hashtags"]["core"] + cfg["hashtags"]["themes"]["faith"]
    return "\n".join([meta.get("hook", meta["title"].capitalize() + "."), "",
                      f"{meta.get('fact', '')} The whole story is in {chapter}.", "", f"{ref} (BSB)", "",
                      f"Read {chapter} free in Chasten.", "Save this for the day you need it.", "",
                      f"{CANDLE}️ {SIGNOFF}", "", " ".join(tags[:15])])


def main(day_dir, force=False):
    meta = json.load(open(os.path.join(day_dir, "meta.json")))
    have = os.path.join(day_dir, "caption.md")
    if os.path.exists(have) and not force:
        print(f"  reusing {have} ({meta.get('captionBy', 'unknown author')})"); return open(have).read()
    cfg = json.load(open(os.path.join(REPO, "studio/config/settings.json")))
    ref = meta["verses"][0]["ref"]
    rules = "\n".join(f"- {r}" for r in cfg["captionRules"])
    themes = cfg["hashtags"]["themes"]
    system = f"""You write Instagram captions for Chasten, a free Bible app. Output only the caption text, nothing else: no title, no quotes around it, no commentary.

Rules, all of them binding:
{rules}
- This caption is for a Reel that shows one moment from a Bible story: the creature or element on screen, the verse read aloud and printed. Line 1 names the moment in plain words, what is happening and what it costs, and the verse lands it. The metadata hook is a good starting point, not a requirement.
- Every fact you state must be in the verses or the background verses given. Never add tradition, legend or commentary that scripture does not say. Never mention audio, music or the video itself.
- The primary call to action is to read the chapter free in Chasten (use the cta given, e.g. "Read Jonah 2 free in Chasten."). The secondary is to save it for the day you need it, or to send it to someone.
- The references line is the verse reference followed by " (BSB)".
- Hashtags: the core set {" ".join(cfg["hashtags"]["core"])} plus two or three theme tags chosen from {json.dumps(themes)}, twelve to fifteen total, lowercase, on the last line.
- Structure, each part separated by a blank line: hook line; one to three short sentences; references line; two calls to action on two lines; sign-off line "{CANDLE}️ {SIGNOFF}"; hashtag line."""
    prompt = "Story metadata:\n" + json.dumps({k: meta.get(k) for k in
                                                 ("title", "hook", "verses", "fact", "factRef", "cta", "context")}, indent=1, ensure_ascii=False)
    caption, by = None, "fallback"
    if TOKEN:
        try:
            draft = ask(system, prompt)
            for attempt in range(2):
                bad = problems(draft, ref)
                if not bad:
                    caption, by = draft, MODEL; break
                print(f"  caption draft {attempt + 1} broke: {'; '.join(bad)}")
                draft = ask(system, prompt + "\n\nYour previous caption broke these rules; write it again and fix them:\n- " + "\n- ".join(bad) + "\n\nPrevious caption:\n" + draft)
        except Exception as e:  # the reel still ships; the caption is the least of it
            print(f"  caption model unavailable: {e}")
    if caption is None:
        caption = fallback(meta, cfg)
        bad = problems(caption, ref)
        if bad: print(f"  fallback caption broke: {'; '.join(bad)}")
    open(os.path.join(day_dir, "caption.md"), "w").write(caption.strip() + "\n")
    meta["captionBy"] = by
    json.dump(meta, open(os.path.join(day_dir, "meta.json"), "w"), indent=1, ensure_ascii=False)
    print(f"  caption by {by}: {len(caption)} chars, hook {len(caption.split(chr(10))[0])} chars")
    return caption


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if x != "--force"]
    main(args[0] if args else os.path.join(REPO, "reels", os.environ.get("CHASTEN_DATE", "")), force="--force" in sys.argv)
