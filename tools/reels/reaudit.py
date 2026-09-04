#!/usr/bin/env python3
"""Re-judge the sweep images with the current rubric. Nothing is regenerated, so a
full pass costs a couple of cents.

Kept as its own script because the rubric is the part of this pipeline most likely
to need another correction, and re-judging what is already on disk is the cheapest
way to see the effect of a change.
"""
import importlib.util, json, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location(
    "mr", os.path.join(REPO, "tools/reels/make_reel.py"))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)

WORK = os.path.join(REPO, ".sweep")
OUT = os.path.join(WORK, "reaudit.json")

sets = json.load(open(os.path.join(REPO, "studio/verses/sets.json")))["sets"]
narratives = {s["title"]: s for s in sets if s.get("kind") == "narrative"}
res = json.load(open(OUT)) if "--fresh" not in sys.argv and os.path.exists(OUT) else {}

for title, s in narratives.items():
    if title in res:
        continue
    slug = "".join(c if c.isalnum() else "-" for c in title)[:28]
    beats, verdict = [], "viable"
    for k, sc in enumerate(s["scenes"], start=1):
        cands = sorted(f for f in os.listdir(WORK) if f.startswith(f"{slug}-{k}-"))
        if not cands:
            # Untested, not failed. The sweep stops at a set's first bad beat, so
            # most sets have later beats that were never generated at all.
            beats.append({"beat": k, "pass": None, "file": None, "reason": "not generated"})
            verdict = "untested" if verdict == "viable" else verdict
            continue
        ok, why, keep = False, "no candidate", None
        for c in cands:
            try:
                ok, why = mr.audit_still(os.path.join(WORK, c), sc, title)
            except Exception as e:
                ok, why = False, f"error {type(e).__name__}"
            keep = c
            if ok:
                break
            time.sleep(1)
        beats.append({"beat": k, "pass": ok, "file": keep, "reason": why})
        if not ok:
            verdict = "drop"
        print(f"  {title} beat {k}: {'PASS' if ok else 'FAIL'} {why[:64]}", flush=True)
        time.sleep(1)
    res[title] = {"verdict": verdict, "beats": beats}
    json.dump(res, open(OUT, "w"), indent=1)

buckets = {"viable": [], "untested": [], "drop": []}
for t, r in res.items():
    buckets[r["verdict"]].append(t)
print("\n" + "=" * 64)
for name, label in (("viable", "VIABLE, every beat passed"),
                    ("untested", "PARTIAL, passed so far, beats still to generate"),
                    ("drop", "FAILED a beat")):
    print(f"\n{label} ({len(buckets[name])}):")
    for t in buckets[name]:
        bad = next((b for b in res[t]["beats"] if b["pass"] is False), None)
        print(f"  {t}" + (f"   <- beat {bad['beat']}: {bad['reason'][:52]}" if bad else ""))
