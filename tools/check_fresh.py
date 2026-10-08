#!/usr/bin/env python3
"""
Plays both daily routines forward from the real records and checks that
Scripture stays fresh (the rules are in tools/verses.py):

  - no verse twice in one post;
  - no verse in both of a day's posts, a reel's verses included;
  - and it reports how long verses rest before they come back, so a pool that
    has grown too small for its format shows up before followers notice.

    python3 tools/check_fresh.py [--weeks 26] [--from YYYY-MM-DD]

It uses the planners themselves (morning.choose, share_run.choose,
world_run.pick), so what it checks is what the routines will do. Nothing is
drawn, posted or written. It exits 1 on any repeat within a post or a day.
"""

import collections
import datetime as dt
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import morning  # noqa: E402
import share_run  # noqa: E402
import verses  # noqa: E402
import world_run  # noqa: E402


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    start = dt.date.fromisoformat(arg("--from") or (dt.date.today() + dt.timedelta(days=1)).isoformat())
    weeks = int(arg("--weeks", "26"))
    led = verses.from_repo()
    mst = morning.state()
    sst = share_run.state()
    wst = world_run.load(world_run.STATE, {})
    lines = world_run.load(os.path.join(world_run.WORLD, "lines.json"))["lines"]
    scenes = world_run.load(os.path.join(world_run.WORLD, "scenes.json"))["scenes"]

    problems, seen = [], collections.defaultdict(list)   # verse -> dates it was posted (reels aside)
    reels, posts = [], 0
    for n in range(weeks * 7):
        day = (start + dt.timedelta(days=n)).isoformat()
        wd = dt.date.fromisoformat(day).weekday()

        # 7 AM
        fmt = morning.WEEK[wd]
        p = morning.choose(fmt, day, mst, led)
        am_refs, reel = p["refs"], fmt == "reel"
        if fmt == "reveal":
            mst["cast"] = mst.get("cast", 0) + p["people"]
        if reel:
            mst.setdefault("bg", []).append(p["background"])
            reels.append(verses.all_keys(am_refs))
        led.add(day, am_refs, reel=reel)  # its record is in the repo before the 11 AM runs

        # 11 AM
        kind = world_run.SHARE_DAYS.get(wd)
        if kind:
            q = share_run.choose(kind, day, sst, led)
            pm_refs = q["refs"]
            t = sst.setdefault("turn", {})
            for k in {"thought": ["scene"], "person": ["couple", "moment"], "blessing": ["scene", "line"]}[kind]:
                t[k] = t.get(k, 0) + 1
            pm_name = f"11 AM {kind}"
        else:
            theme, pairs = world_run.pick(day, lines, scenes, wst, led)
            content = [(line, scene) for line, scene in pairs if line["kind"] != "cta"]
            pm_refs = [line["ref"] for line, _ in content]
            wst["postCount"] = wst.get("postCount", 0) + 1
            wst["history"] = (wst.get("history", []) + [{
                "date": day, "theme": theme, "lines": [line["id"] for line, _ in content],
                "scenes": [scene["id"] for _, scene in content]}])[-40:]
            pm_name = "11 AM world"

        # the rules: within a post, then within the day
        for name, refs in ((f"7 AM {fmt}", am_refs), (pm_name, pm_refs)):
            ks = [verses.all_keys([r]) for r in refs]
            if sum(len(k) for k in ks) != len(set().union(*ks)):
                problems.append(f"{day} {name}: a verse appears twice in one post: {refs}")
        both = verses.all_keys(am_refs) & verses.all_keys(pm_refs)
        if both:
            problems.append(f"{day}: both posts carry {sorted(both)}")

        led.add(day, pm_refs)
        for refs in ([] if reel else [am_refs]) + [pm_refs]:
            for k in verses.all_keys(refs):
                seen[k].append(day)
        posts += 2

    gaps, settled = [], []  # settled: returns after the first two weeks, once the old pace has passed
    for k, days in seen.items():
        ds = sorted(set(dt.date.fromisoformat(d) for d in days))
        gaps += [(b - a).days for a, b in zip(ds, ds[1:])]
        settled += [(b - a).days for a, b in zip(ds, ds[1:]) if b >= start + dt.timedelta(days=14)]
    shared = [len(a & b) for a, b in zip(reels, reels[1:])]

    print(f"{posts} posts over {weeks} weeks from {start}: {len(seen)} different verses outside the reels")
    if gaps:
        print(f"a verse comes back after {min(gaps)} days at the soonest; median {statistics.median(gaps):.0f} days")
    if settled:
        print(f"after the first two weeks: {min(settled)} days at the soonest")
    if shared:
        print(f"back-to-back reels share {min(shared)} to {max(shared)} of their {morning.REEL_VERSES} verses")
    for p in problems:
        print("PROBLEM:", p)
    print("fresh: ok" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
