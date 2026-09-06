#!/usr/bin/env python3
"""Post a short Slack message when a carousel or a reel is ready.

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
    if not HOOK:
        print("SLACK_WEBHOOK_URL is not set; nothing sent"); return
    req = urllib.request.Request(HOOK, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("slack:", r.status, r.read()[:80].decode())


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


def reel(path):
    day = path.split("/")[1]
    meta = json.load(open(os.path.join(REPO, "reels", day, "meta.json")))
    caption = open(os.path.join(REPO, path)).read().strip()
    lines = [f":clapper: *Chasten Reel {day}* is ready: <{meta['url']}|Download the video>",
             f"Audio: search `{meta['audioSearch'][0]}` in Instagram's music library, instrumental only, the verse is already narrated."]
    if meta.get("context"):
        lines.append("*Story notes*")
        lines += [f"• {v['text']} [{v['ref']}]" for v in meta["context"][:3]]
    lines.append("*Description*")
    lines.append("```\n" + caption + "\n```")
    lines.append(f"_{meta['tone']}, {meta.get('voiceName') or meta['voice']}, {meta['seconds']:.0f}s_")
    return "\n".join(lines)


if __name__ == "__main__":
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        send(":wave: Chasten notifier is connected. Carousel and reel messages will land here.")
        sys.exit(0)
    sent = 0
    for f in changed_files():
        if f.startswith("posts/") and f.endswith("/post.json"):
            send(carousel(f)); sent += 1
        elif f.startswith("reels/") and f.endswith("/caption.md"):
            send(reel(f)); sent += 1
    print(f"{sent} message(s)")
