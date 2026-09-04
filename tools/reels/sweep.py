#!/usr/bin/env python3
"""Viability sweep over every narrative set.

Generates any beat that has no image yet and judges it, so a story that cannot be
rendered is found once here rather than one failure at a time in production.
Resumable and idempotent: existing files are reused, so a rerun costs nothing for
work already done.
"""
import importlib.util, json, os, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location(
    "mr", os.path.join(REPO, "tools/reels/make_reel.py"))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)

WORK = os.path.join(REPO, ".sweep")
REPORT = os.path.join(WORK, "report.json")
ROLLS = 2          # the live build allows four; two is enough to judge viability
os.makedirs(WORK, exist_ok=True)

# Matches the live build: escalate toward distance, never toward emptiness.
ESCALATE = ["",
            " Push any figures further away and smaller in the frame.",
            " Wide establishing shot from a great distance, figures tiny."]

sets = json.load(open(os.path.join(REPO, "studio/verses/sets.json")))["sets"]
narratives = [s for s in sets if s.get("kind") == "narrative"]
report = json.load(open(REPORT)) if os.path.exists(REPORT) else {}

print(f"sweeping {len(narratives)} narrative sets, up to {ROLLS} rolls per beat\n", flush=True)
for s in narratives:
    title = s["title"]
    slug = "".join(c if c.isalnum() else "-" for c in title)[:28]
    beats, viable = [], True
    for k, sc in enumerate(s["scenes"], start=1):
        passed, why, used = False, "", 0
        # Judge whatever is already on disk before paying for anything new.
        for c in sorted(f for f in os.listdir(WORK) if f.startswith(f"{slug}-{k}-")):
            used += 1
            try:
                passed, why = mr.audit_still(os.path.join(WORK, c), sc, title)
            except Exception as e:
                passed, why = False, f"error {type(e).__name__}"
            if passed:
                break
        for roll in range(used, ROLLS):
            if passed:
                break
            dest = os.path.join(WORK, f"{slug}-{k}-{roll}.jpg")
            try:
                mr.run_model(mr.IMG_MODEL,
                             {"prompt": f"Cinematic photograph of {sc}. {mr.PERIOD}. "
                                        f"{mr.FRAME}{mr.FIGURES}{ESCALATE[roll]}",
                              "aspect_ratio": "9:16", "output_format": "jpg"}, dest)
                passed, why = mr.audit_still(dest, sc, title)
            except Exception as e:
                passed, why = False, f"error {type(e).__name__}"
            used = roll + 1
            if not passed:
                time.sleep(5)
        beats.append({"beat": k, "pass": passed, "rolls": used, "reason": why})
        if not passed:
            viable = False
        print(f"  {title} beat {k}: {'PASS' if passed else 'FAIL'} "
              f"(roll {used}) {why[:66]}", flush=True)
        time.sleep(3)
    report[title] = {"verdict": "viable" if viable else "drop", "beats": beats}
    json.dump(report, open(REPORT, "w"), indent=1)

viable = [t for t, r in report.items() if r["verdict"] == "viable"]
dead = [t for t, r in report.items() if r["verdict"] == "drop"]
print("\n" + "=" * 64)
print(f"VIABLE ({len(viable)}):")
for t in viable:
    print(f"  + {t}")
print(f"\nDROP ({len(dead)}):")
for t in dead:
    bad = next((b for b in report[t]["beats"] if not b["pass"]), None)
    print(f"  - {t}  (beat {bad['beat']}: {bad['reason'][:56]})" if bad else f"  - {t}")
