#!/usr/bin/env python3
"""Post a short Slack message when a carousel (7 AM or 11 AM) or a reel is ready.

Runs in GitHub Actions on push, because that is the only place in this system
that can hold a secret: cloud routines reject environment variables, and the
repo is public. The webhook URL lives in the SLACK_WEBHOOK_URL secret and is
never written anywhere else.

The caption goes inside a code block so Slack offers a copy control on it.
"""
import json, os, subprocess, sys, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
RAW = "https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main"


def send(text):
    if os.environ.get("CHASTEN_TEST"):
        text = ":test_tube: test of the rebuilt chain, ignore the thumbs line\n" + text
    if os.environ.get("CHASTEN_PUSHED") == "false":
        text = (":warning: the build's commit did not reach GitHub, so the download link will not work yet. "
                f"Action log: {os.environ.get('CHASTEN_RUN_URL', '')}\n" + text)
    if not HOOK:
        print("SLACK_WEBHOOK_URL is not set; nothing sent. The message would have been:\n" + text); return
    req = urllib.request.Request(HOOK, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def changed_files():
    out = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                         cwd=REPO, capture_output=True, text=True)
    return [f for f in out.stdout.split() if f]


def carousel(path):
    p = json.load(open(os.path.join(REPO, path)))
    if p.get("status") != "posted":
        return (f":warning: *Chasten IG {p['date']}* did not post: {p.get('note') or 'see the run log'}.\n"
                f"Cards are in the repo under posts/{p['date']} to post by hand.")
    lines = [f":white_check_mark: *Chasten IG {p['date']}* posted: <{p['permalink']}|{p['title']}>"]
    if p.get("audio"):
        lines.append(f"Audio idea: search `{p['audio']}` in Instagram's music library.")
    return "\n".join(lines)


def world(path):
    """The 11 AM "Scripture in the world" carousel (tools/world_run.py)."""
    p = json.load(open(os.path.join(REPO, path)))
    if p.get("status") != "posted":
        return (f":warning: *Chasten IG 11 AM {p['date']}* did not post: {p.get('note') or 'see the run log'}.\n"
                f"Any finished cards are in the repo under world/{p['date']}.")
    drawn = f" \u00b7 {p['drawn']} drawing{'s' if p['drawn'] != 1 else ''}, about ${p.get('cost', 0):.2f}" if p.get("drawn") else ""
    if p.get("kind") == "share":  # Wednesday, Thursday and Sunday (tools/share_run.py)
        lines = [f":white_check_mark: *Chasten IG 11 AM {p['date']}* \u00b7 {p.get('name', 'share post')}: <{p['permalink']}|{p.get('title', '')}>",
                 f"{len(p.get('items', []))} slides \u00b7 {', '.join(p.get('refs') or [])}{drawn}"]
        if p.get("note"):
            lines.append(p["note"])
        return "\n".join(lines)
    lines = [f":white_check_mark: *Chasten IG 11 AM {p['date']}* posted: <{p['permalink']}|{p['title']}>",
             f"{len(p.get('slides', []))} slides \u00b7 theme: {p.get('theme', 'mixed')} \u00b7 look: {p.get('look', 'bw').replace('-', ' ')}{drawn}"]
    if p.get("audio"):
        lines.append(f"Audio idea: search `{p['audio']}` in Instagram's music library.")
    return "\n".join(lines)


def morning(path):
    """The 7 AM interactive post (tools/morning.py): a different format each weekday."""
    p = json.load(open(os.path.join(REPO, path)))
    name = p.get("name", "7 AM post")
    if p.get("status") != "posted":
        return (f":warning: *Chasten IG 7 AM {p['date']}* ({name}) did not post: {p.get('note') or 'see the run log'}.\n"
                f"Whatever was made is in the repo under morning/{p['date']}.")
    kind = {"reel": "reel", "dove": "video carousel"}.get(p.get("format"), "carousel")
    detail = f"{len(p.get('items', []))} slides" if kind != "reel" else "7.5 s, strings"
    if p.get("format") == "reveal":
        if p.get("drawn"):
            detail += " \u00b7 photo drawn ({}), about ${:.2f}".format(p["drawn"], p.get("cost", 0))
        else:
            detail += " \u00b7 photo approved in advance"
    refs = ", ".join(p.get("refs") or []) or f"{p.get('verseCount', 0)} verses"
    lines = [f":white_check_mark: *Chasten IG 7 AM {p['date']}* \u00b7 {name}: <{p['permalink']}|{p.get('title', '')}>",
             f"{kind} \u00b7 {detail} \u00b7 {refs}"]
    if p.get("note"):
        lines.append(p["note"])
    return "\n".join(lines)


def reel(path):
    day = path.split("/")[1]
    meta = json.load(open(os.path.join(REPO, "reels", day, "meta.json")))
    cap_path = os.path.join(REPO, path)
    caption = open(cap_path).read().strip() if os.path.exists(cap_path) else "(the caption step failed; see the Action log and write one)"
    g = meta.get("gates", {})
    lines = [f":clapper: *Chasten Reel {day}* \u00b7 {meta['title']}",
             f"<{meta['url']}|Download the video> \u00b7 {meta['seconds']:.0f}s \u00b7 ${meta.get('cost', 0):.2f}",
             f"Hook: {meta.get('hook', '')}", f"Verse: {meta['verses'][0]['ref']}",
             f"Fact: {meta.get('fact', '')} [{meta.get('factRef', '')}]"]
    if g:
        lines.append(f"Gates: sound meets motion {g.get('headMotionAtPeak', '?')}, footage {g.get('footage', '?')}s, dark tail {g.get('darkTail', '?')}s")
    if meta.get("context"):
        lines.append("*Story notes*"); lines += [f"\u2022 {v['text']} [{v['ref']}]" for v in meta["context"][:3]]
    lines += ["*Description*", "```\n" + caption + "\n```",
              ":thumbsup: to post to Instagram, Facebook and YouTube \u00b7 reply here with changes \u00b7 :thumbsdown: to shelve"]
    return "\n".join(lines)


def shelved(path):
    s = json.load(open(os.path.join(REPO, path)))
    return (f":warning: *Chasten Reel {s['date']}* \u00b7 {s['title']} was shelved: {s['shelved']}. "
            f"Spent ${s.get('cost', 0):.2f}. The next story in the queue runs next time.")


def failed(run_url, day):
    return (f":x: *Chasten Reel {day}* did not build. Nothing was posted. "
            f"Whatever it spent before failing is in the log: {run_url}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--failed":
        send(failed(args[1], args[2] if len(args) > 2 else "")); sys.exit(0)
    if not args and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        send(":wave: Chasten notifier is connected. Carousel and reel messages will land here.")
        sys.exit(0)
    sent = 0
    for f in args or changed_files():
        if f.startswith("posts/") and f.endswith("/post.json"):
            send(carousel(f)); sent += 1
        elif f.startswith("world/") and f.endswith("/post.json"):
            send(world(f)); sent += 1
        elif f.startswith("morning/") and f.endswith("/post.json"):
            send(morning(f)); sent += 1
        elif f.startswith("reels/") and f.endswith("/caption.md"):
            send(reel(f)); sent += 1
        elif f.startswith("reels/") and f.endswith("/shelved.json"):
            send(shelved(f)); sent += 1
    print(f"{sent} message(s)")
