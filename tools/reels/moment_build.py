#!/usr/bin/env python3
"""Build one Moment, the way we agreed on 2026-09-06, spending only on steps that
have already passed a gate:

  shot card (free) -> start still, audited -> narration and word timings ->
  one Veo take -> gates -> the chained stare clip -> assembled by moment.py

Hard cap per story. A story that cannot clear the gates in two takes is shelved
and reported, never brute-forced. Everything paid is cached by story and day so
a retry re-buys nothing.

Output: reels/<date>/reel.mp4 and reels/<date>/meta.json
"""
import argparse, base64, importlib.util, json, os, shutil, subprocess, sys, time, urllib.error, urllib.request, uuid
from datetime import datetime
from zoneinfo import ZoneInfo

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def load(rel):
    spec = importlib.util.spec_from_file_location(os.path.basename(rel)[:-3], os.path.join(REPO, rel))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
mr = load("tools/reels/make_reel.py")
mo = load("tools/reels/moment.py")
log = mr.log
TODAY, OUTDIR_NAME = "", ""

VEO = "google/veo-3.1"
VEO_RATE, VEO_SECONDS, STILL_COST = 0.40, 8, 0.04
NEG = "people, person, human, hands, silhouette, text, lettering, watermark, modern objects, music"


class Ledger:
    def __init__(self, cap):
        self.cap, self.items = cap, []
    def can(self, cost):
        return sum(c for _, c in self.items) + cost <= self.cap + 1e-9
    def add(self, what, cost):
        self.items.append((what, cost)); log(f"    ${cost:.2f} {what}  (total ${self.total():.2f} of ${self.cap:.2f})")
    def total(self):
        return round(sum(c for _, c in self.items), 2)


def data_uri(path, mime="image/jpeg"):
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def align(audio, text, dest):
    """ElevenLabs forced alignment: word timestamps for the words George just read."""
    if os.path.exists(dest):
        return dest
    b = uuid.uuid4().hex.encode(); raw = open(audio, "rb").read()
    body = (b"--" + b + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n" + raw
            + b"\r\n--" + b + b"\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n" + text.encode() + b"\r\n--" + b + b"--\r\n")
    req = urllib.request.Request("https://api.elevenlabs.io/v1/forced-alignment", data=body,
                                 headers={"xi-api-key": mr.ELEVEN_KEY, "Content-Type": "multipart/form-data; boundary=" + b.decode()})
    j = json.load(urllib.request.urlopen(req, timeout=120)); json.dump(j, open(dest, "w")); return dest


def veo(prompt, image, dest, seed=None):
    inp = {"image": data_uri(image), "prompt": prompt, "negative_prompt": NEG, "duration": VEO_SECONDS,
           "resolution": "1080p", "aspect_ratio": "9:16", "generate_audio": True}
    if seed is not None:
        inp["seed"] = seed
    return mr.run_model(VEO, inp, dest, poll=True)


def last_frame(video, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-0.05", "-i", video, "-frames:v", "1", "-q:v", "2", "-y", dest], check=True)
    return dest


def assemble(take, extend, work, card, verse, out, trim=0.0):
    args = ["--take", take, "--verse", os.path.join(work, "narr-verse.mp3"), "--verse-align", os.path.join(work, "align-verse.json"),
            "--fact", os.path.join(work, "narr-fact.mp3"), "--fact-align", os.path.join(work, "align-fact.json"),
            "--hook", card["hook"], "--ref", verse["ref"], "--fact-ref", card["factRef"], "--fact-text", card["fact"],
            "--cta", card["cta"], "--out", out, "--scene", card["scene"], "--trim-start", f"{trim:.2f}"]
    if extend:
        args += ["--extend", extend]
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools/reels/moment.py"), *args], capture_output=True, text=True)
    if r.returncode:
        return None, (r.stdout + r.stderr).strip().splitlines()[-1][:200]
    return json.load(open(os.path.splitext(out)[0] + ".report.json")), ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", default=os.environ.get("CHASTEN_STORY", ""))
    ap.add_argument("--dry-run", action="store_true", help="exercise the flow on files already on disk; spends nothing")
    ap.add_argument("--dry-dir", default="")
    a = ap.parse_args()

    settings = json.load(open(os.path.join(REPO, "studio/config/settings.json")))
    cfg = settings["reels"]
    cards = json.load(open(os.path.join(REPO, "studio/moments.json")))["moments"]
    sets = {s["title"]: s for s in json.load(open(os.path.join(REPO, "studio/verses/sets.json")))["sets"]}
    ptr_path = os.path.join(REPO, "studio/state/moments-pointer.json")
    ptr = json.load(open(ptr_path)) if os.path.exists(ptr_path) else {"done": [], "shelved": []}
    today = os.environ.get("CHASTEN_DATE") or datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    preview = a.dry_run or bool(os.environ.get("CHASTEN_DATE"))
    global TODAY, OUTDIR_NAME
    TODAY, OUTDIR_NAME = today, ("preview-dryrun" if a.dry_run else today)

    if a.story:
        card = next((c for c in cards if c["title"] == a.story), None)
        if not card:
            raise SystemExit(f"no shot card titled {a.story!r}")
    else:
        card = next((c for c in cards if c["title"] not in ptr["done"] and c["title"] not in ptr["shelved"]), None)
        if not card:
            raise SystemExit("every shot card has been built or shelved; add more to studio/moments.json")
    vset = sets[card["title"]]
    verse = vset["verses"][0]
    tone = vset.get("tone", "gentle")
    voice = cfg["voiceByTone"][tone]
    slug = "".join(c if c.isalnum() else "-" for c in card["title"])[:28]
    work = os.path.join(REPO, ".reelwork", f"{today}-{slug}"); os.makedirs(work, exist_ok=True)
    ledger = Ledger(float(cfg.get("momentCap", 10.0)))
    log(f"{today}  moment: {card['title']!r}  verse {verse['ref']}  reader {voice.get('name')}  cap ${ledger.cap:.2f}")

    if a.dry_run:
        # Stand-ins from a previous build: proves the flow without a paid call.
        d = a.dry_dir
        for src, dst in (("veo31-a.mp4", "take1.mp4"), ("veo31-stare.mp4", "stare.mp4"), ("narr-verse.mp3", "narr-verse.mp3"),
                         ("align-verse.json", "align-verse.json"), ("narr-fact.mp3", "narr-fact.mp3"), ("align-fact.json", "align-fact.json")):
            shutil.copy(os.path.join(d, src), os.path.join(work, dst))
        take, stare, trim = os.path.join(work, "take1.mp4"), os.path.join(work, "stare.mp4"), 1.7
    else:
        # 1. Start still, audited before a single video second is bought.
        still = None
        for roll in range(2):
            if not ledger.can(STILL_COST):
                break
            dest = os.path.join(work, f"still{roll}.jpg")
            mr.run_model(mr.IMG_MODEL, {"prompt": f"Cinematic photograph of {card['still']}. {mr.PERIOD}. {mr.FRAME}{mr.SETTING}",
                                        "aspect_ratio": "9:16", "output_format": "jpg"}, dest)
            ledger.add(f"still roll {roll}", STILL_COST)
            ok, why = mr.audit_still(dest, card["scene"], card["title"])
            log(f"    still {roll}: {'PASS' if ok else 'FAIL'} {why}")
            if ok:
                still = dest; break
        if not still:
            return shelve(card, ptr, ptr_path, ledger, preview, "no start still passed the audit")

        # 2. Narration and word timings. Pennies.
        text = " ".join(verse["text"].split())
        mr.narrate(text, tone, voice, cfg, os.path.join(work, "narr-verse.mp3"))
        mr.narrate(card["fact"], tone, voice, cfg, os.path.join(work, "narr-fact.mp3"))
        align(os.path.join(work, "narr-verse.mp3"), text, os.path.join(work, "align-verse.json"))
        align(os.path.join(work, "narr-fact.mp3"), card["fact"], os.path.join(work, "align-fact.json"))
        log("    narration and alignment done")

        # 3. One take, then the gates. A second take only if the first fails.
        take, trim = None, 0.0
        for attempt in range(2):
            cost = VEO_RATE * VEO_SECONDS
            if not ledger.can(cost):
                log("    cap reached before a passing take"); break
            dest = os.path.join(work, f"take{attempt + 1}.mp4")
            veo(card["take"], still, dest, seed=None if attempt == 0 else 7 + attempt)
            ledger.add(f"take {attempt + 1}", cost)
            tmp = os.path.join(work, "gates"); os.makedirs(tmp, exist_ok=True)
            t_peak, t_close, ratio, _ = mo.analyse(dest, tmp)
            bad = mo.audit_frames(dest, card["scene"], tmp)
            early_only = bad and all(t <= 1.6 for t, _ in bad)
            log(f"    take {attempt + 1}: sound peak {t_peak:.1f}s, motion at peak {ratio:.2f}, frame audit {'clean' if not bad else bad}")
            if ratio >= mo.SYNC_HEAD and (not bad or early_only):
                take = dest
                if early_only:
                    trim = 1.7
                    if mo.audit_frames(dest, card["scene"], tmp, start=trim):
                        take = None; log("    a figure survives the trim; rejecting the take")
                if take:
                    break
        if not take:
            return shelve(card, ptr, ptr_path, ledger, preview, "no take passed the gates within the cap")

        # 4. The chained stare from the take's last frame. If it fails, the
        #    reel ends on the dark sooner; that is still better than a loop.
        stare = None
        frame = last_frame(take, os.path.join(work, "last.jpg"))
        if ledger.can(VEO_RATE * VEO_SECONDS):
            dest = os.path.join(work, "stare.mp4")
            veo(card["stare"], frame, dest)
            ledger.add("stare clip", VEO_RATE * VEO_SECONDS)
            bad = mo.audit_frames(dest, card["scene"], os.path.join(work, "gates"))
            stare = None if bad else dest
            log(f"    stare: {'clean' if stare else bad}")

    # 5. Assemble.
    outdir = os.path.join(REPO, "reels", OUTDIR_NAME); os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "reel.mp4")
    report, err = assemble(take, stare, work, card, verse, out, trim)
    if not report:
        return shelve(card, ptr, ptr_path, ledger, preview, f"assembly failed: {err}")
    meta = {"date": today, "title": card["title"], "kind": "moment", "narrative": True, "tone": tone,
            "voice": voice["voice_id"], "voiceName": voice.get("name"), "verses": [verse],
            "refLine": f"{verse['ref']}  ·  {settings.get('translation', 'BSB')}", "hook": card["hook"],
            "fact": card["fact"], "factRef": card["factRef"], "cta": card["cta"], "context": vset.get("context", []),
            "seconds": report["outSeconds"], "gates": {k: report[k] for k in ("soundPeak", "headMotionAtPeak", "synced", "footage", "darkTail") if k in report},
            "trimmedOpening": trim, "stareClip": bool(stare), "cost": ledger.total(), "costItems": ledger.items,
            "sizeBytes": os.path.getsize(out),
            "url": f"https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/reels/{today}/reel.mp4",
            "builtAt": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")}
    json.dump(meta, open(os.path.join(outdir, "meta.json"), "w"), ensure_ascii=False, indent=1)
    if not preview:
        ptr["done"] = ptr.get("done", []) + [card["title"]]; ptr["lastMomentId"] = today
        json.dump(ptr, open(ptr_path, "w"), indent=1)
    log(f"  done: {out} ({meta['sizeBytes']//1024}KB, {meta['seconds']}s, ${meta['cost']:.2f})")


def shelve(card, ptr, ptr_path, ledger, preview, why):
    log(f"  SHELVED {card['title']!r}: {why}  (spent ${ledger.total():.2f})")
    if not preview:
        ptr["shelved"] = ptr.get("shelved", []) + [card["title"]]
        json.dump(ptr, open(ptr_path, "w"), indent=1)
    outdir = os.path.join(REPO, "reels", OUTDIR_NAME); os.makedirs(outdir, exist_ok=True)
    json.dump({"date": TODAY, "title": card["title"], "shelved": why, "cost": ledger.total(), "items": ledger.items},
              open(os.path.join(outdir, "shelved.json"), "w"), indent=1)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
