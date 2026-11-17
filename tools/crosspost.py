#!/usr/bin/env python3
"""
Facebook beside Instagram (Ric, 2026-11-17: "all socials... including carousels").

Every routine posts to Instagram first, then the same media and caption to the Chasten Bible App
Facebook Page, and records how that went in the day's post.json, so the Slack line shows both.
Instagram never waits on Facebook, and a Facebook failure never changes the Instagram status.

    python3 tools/crosspost.py facebook --record PATH --status posted|failed|skipped [--permalink U] [--id I] [--note T]

Only the Chasten Bible App Page (FACEBOOK_PAGE_ID) is ever posted to: the same Facebook login
manages other Pages that are not Chasten's.
"""

import json
import sys

FACEBOOK_PAGE_ID = "1260378077162903"


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def cmd_facebook(argv):
    path, status = arg(argv, "--record"), arg(argv, "--status")
    if status not in ("posted", "failed", "skipped"):
        raise SystemExit("--status is posted, failed or skipped")
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    fb = {"status": status, "permalink": arg(argv, "--permalink"), "id": arg(argv, "--id"), "note": arg(argv, "--note")}
    rec["facebook"] = {k: v for k, v in fb.items() if v is not None}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps(rec["facebook"]))
    return 0


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    sys.exit({"facebook": cmd_facebook}[cmd](rest))
