#!/usr/bin/env python3
"""Build one Chasten Reel end to end.

Everything is deterministic from studio/ plus one secret (REPLICATE_API_TOKEN),
so this runs unattended in CI. Tone is read from the verse set and drives both the
imagery and the narrator, so they can never disagree.

Output: reels/<date>/reel.mp4 and reels/<date>/meta.json
"""
import base64, json, os, re, subprocess, sys, time, urllib.error, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN = os.environ.get("REPLICATE_API_TOKEN", "").strip()
W, H = 1080, 1920
MARGIN = 96
IMG_MODEL = "black-forest-labs/flux-1.1-pro"
VID_MODEL = "kwaivgi/kling-v2.1"
TTS_MODEL = "minimax/speech-02-hd"

FRAME = ("Vertical composition with calm empty space in the upper third for text, "
         "no text, no words, no lettering, no watermark")
# Scenery sets are landscapes and stay empty. Narrative sets get people whether we
# ask for them or not, so direct the model instead of forbidding it: distance and
# turned backs give reverence, dodge faces, and stop the model fighting the prompt.
SCENERY = ", no people, no faces"
FIGURES = (", any people are small and far away, seen from behind or in silhouette, "
           "faces never visible")
MOTION_NEG = ("faces, facial features, morphing, warping, melting, distortion, extra limbs, "
              "fast motion, camera shake, zoom, text, letters, watermark, logo, style change, "
              "modern clothing, jacket, coat, hoodie, jeans, contemporary dress, modern buildings")
# Anachronism is the failure mode for biblical scenes. The first furnace render put
# four men in fur lined parkas, which reads as a mistake rather than as reverence.
PERIOD = ("ancient historical setting, period accurate clothing of the era, long flowing robes, "
          "no modern objects or dress")


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------- replicate
def api(url, body=None, wait=False):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 **({"Prefer": "wait"} if wait else {})},
        method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.load(r)


def run_model(model, payload, dest, poll=False, tries=4):
    """Replicate rate limits aggressively on new accounts, so back off and retry.
    Existing output is reused: a crash late in the run should not re-buy clips."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        log(f"    reusing {os.path.basename(dest)}")
        return dest
    for attempt in range(tries):
        try:
            p = api(f"https://api.replicate.com/v1/models/{model}/predictions",
                    {"input": payload}, wait=not poll)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                wait_s = 20 * (attempt + 1)
                log(f"    429, retrying in {wait_s}s")
                time.sleep(wait_s)
                continue
            raise
    if poll:
        t0 = time.time()
        while p.get("status") in ("starting", "processing"):
            time.sleep(15)
            p = api(f"https://api.replicate.com/v1/predictions/{p['id']}")
            if time.time() - t0 > 1500:
                raise SystemExit(f"timed out waiting on {model}")
    if p.get("status") != "succeeded":
        raise SystemExit(f"{model} failed: {str(p.get('error'))[:300]}")
    url = p["output"] if isinstance(p["output"], str) else p["output"][0]
    urllib.request.urlretrieve(url, dest)
    return dest


# gpt-4o-mini called a face legible on backs of heads and killed good images.
# On six stills with a verdict I set by looking, 4.1-mini scored 4/5 to its 2/5.
VLM = "openai/gpt-4.1-mini"


RUBRIC = """You are judging whether this image can be published as the backdrop of a
scripture video. Be fair. Most competent images should pass.

Story: {title}
Scene requested: {scene}

Robed or cloaked human figures ARE welcome in these images. Never fail an image
merely because people appear in it.

Reply strictly as JSON with keys ok (true/false) and reason (one short sentence).

Set ok to FALSE only for one of these clear defects:
  1. A human face is legible, meaning you could make out eyes, nose and mouth well
     enough to describe the person. Silhouettes, backs of heads, hooded or shadowed
     faces and distant figures are all FINE.
  2. Visible anatomical distortion: malformed hands, extra or missing limbs, melted
     or smeared features.
  3. Something modern: contemporary clothing such as jackets, coats, hoodies or
     jeans, vehicles, machinery, power lines, modern buildings. Robes, tunics,
     cloaks, sandals and ancient stonework are period correct and are NOT modern.
  4. The scene names specific things, such as a dove, a stairway, a city wall or a
     burning bush. If any of them is missing from the image, or is present but not
     recognisable as that thing, fail it. A beautiful picture of the right place
     without the thing that makes it this story is a failure.
  5. A key object is at an absurd scale, or the image is impossible in a way a
     viewer would read as an error rather than as style.

Set ok to TRUE in every other case. Empty landscapes, moody or dark lighting,
unusual compositions and artistic interpretation are all acceptable."""


def audit_still(path, scene, verse_title):
    """Ask a vision model whether the image is actually usable.

    Stills cost four cents, clips cost about a dollar sixty five, so it is worth a
    fraction of a cent to find out before animating.

    The first version of this rubric banned people outright and rejected all 23
    narrative sets, including a road to a walled city with two distant silhouettes
    that was the best image of the sweep. The failures worth catching are legible
    faces, distortion, anachronism and absurd scale, so it now names only those.
    """
    with open(path, "rb") as f:
        uri = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    try:
        p = api(f"https://api.replicate.com/v1/models/{VLM}/predictions",
                {"input": {"prompt": RUBRIC.format(title=verse_title, scene=scene),
                           "image_input": [uri], "temperature": 0,
                           "max_completion_tokens": 200}}, wait=True)
        out = p.get("output")
        txt = "".join(out) if isinstance(out, list) else str(out)
        m = re.search(r"\{.*?\}", txt, re.S)
        v = json.loads(m.group()) if m else {"ok": True, "reason": "unparsed"}
        return bool(v.get("ok", True)), str(v.get("reason", ""))[:120]
    except Exception as e:
        log(f"    audit unavailable ({type(e).__name__}), allowing through")
        return True, "audit skipped"


# ---------------------------------------------------------------- typography
def wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    return lines


def shadowed(base, draw_fn):
    """Two layers: a wide halo for separation from bright footage, then a tight
    core composited twice so letter edges hold against a sunlit field."""
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(halo), (0, 0, 0, 200))
    base.alpha_composite(halo.filter(ImageFilter.GaussianBlur(30)))
    core = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(core), (0, 0, 0, 235))
    core = core.filter(ImageFilter.GaussianBlur(6))
    base.alpha_composite(core)
    base.alpha_composite(core)
    draw_fn(ImageDraw.Draw(base), (255, 255, 255, 255))


def shadow_image(base, img, xy):
    black = Image.new("RGBA", img.size, (0, 0, 0, 255))
    black.putalpha(img.getchannel("A"))
    for blur, scale, reps in ((30, 200, 1), (6, 235, 2)):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        b = black.copy()
        b.putalpha(b.getchannel("A").point(lambda a: a * scale // 255))
        layer.alpha_composite(b, xy)
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
        for _ in range(reps):
            base.alpha_composite(layer)
    base.alpha_composite(img, xy)


def make_verse_overlay(text, ref, out):
    serif_p = os.path.join(REPO, "tools/assets/fonts/Literata_400Regular.ttf")
    sans_p = os.path.join(REPO, "tools/assets/fonts/Inter_600SemiBold.ttf")
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    size = 62 if len(text) < 190 else 56
    fv, fr = ImageFont.truetype(serif_p, size), ImageFont.truetype(sans_p, 32)
    lines = wrap(ImageDraw.Draw(img), text, fv, W - 2 * MARGIN)
    lh = int(size * 1.36)

    def draw(d, fill):
        y = 250
        for ln in lines:
            d.text((MARGIN, y), ln, font=fv, fill=fill)
            y += lh
        d.text((MARGIN, y + 34), ref, font=fr,
               fill=(fill[0], fill[1], fill[2], int(fill[3] * 0.85)))
    shadowed(img, draw)
    img.save(out)


def make_signoff_overlay(out):
    sans_p = os.path.join(REPO, "tools/assets/fonts/Inter_600SemiBold.ttf")
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wm = Image.open(os.path.join(REPO, "tools/assets/img/wordmark-white.png")).convert("RGBA")
    tw = 380
    wm = wm.resize((tw, int(wm.height * tw / wm.width)), Image.LANCZOS)
    f = ImageFont.truetype(sans_p, 34)
    sub = "A free Bible app  ·  chasten.ai"
    sw = ImageDraw.Draw(img).textlength(sub, font=f)

    def draw(d, fill):
        d.text(((W - sw) / 2, H // 2 + 70), sub, font=f, fill=fill)
    shadow_image(img, wm, ((W - tw) // 2, H // 2 - 90))
    shadowed(img, draw)
    img.save(out)


# ---------------------------------------------------------------- assembly
def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def clips_needed(narr_seconds, clip=10.0, xfade=0.5):
    """How many clips buy enough runway for this narration plus the sign-off.
    Two minimum, three max: past that the verse is too long and gets trimmed."""
    need = 1.2 + narr_seconds + 0.9 + 2.6
    for n in (2, 3):
        if n * clip - (n - 1) * xfade >= need:
            return n
    return 3


def assemble(clips, verse_png, sign_png, narr, out):
    """Timings derive from the narration so verses of any length cut correctly.
    Narration only, no bed: an Instagram instrumental is layered after download."""
    XFADE, CLIP, NARR_IN, VERSE_IN = 0.5, 10.0, 1.2, 0.5
    n = probe_duration(narr)
    runway = len(clips) * CLIP - (len(clips) - 1) * XFADE
    verse_hold = NARR_IN + n + 0.3 - VERSE_IN
    sign_in = NARR_IN + n + 0.9
    total = min(sign_in + 2.6, runway)
    sign_dur = max(total - sign_in, 1.2)          # never negative, always readable
    if sign_in + sign_dur > total:                 # narration ran right to the edge
        sign_in = max(total - sign_dur, NARR_IN)
    verse_hold = min(verse_hold, max(sign_in - VERSE_IN, 1.0))

    scale = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=24,setsar=1"
    filt = "".join(f"[{i}:v]{scale}[v{i}];\n" for i in range(len(clips)))
    # Each clip holds the screen for an equal share, so every authored beat is seen.
    seg = (total + (len(clips) - 1) * XFADE) / len(clips)
    prev, off = "v0", seg - XFADE
    for i in range(1, len(clips)):
        lbl = "base" if i == len(clips) - 1 else f"x{i}"
        filt += f"[{prev}][v{i}]xfade=transition=fade:duration={XFADE}:offset={off:.2f}[{lbl}];\n"
        prev, off = lbl, off + seg - XFADE
    ov, sg = len(clips), len(clips) + 1
    filt += (
        f"[{ov}:v]fps=24,format=rgba,fade=t=in:st=0:d=0.9:alpha=1,"
        f"fade=t=out:st={verse_hold - 0.6:.2f}:d=0.6:alpha=1,setpts=PTS-STARTPTS+{VERSE_IN}/TB[vs];\n"
        f"[{sg}:v]fps=24,format=rgba,fade=t=in:st=0:d=0.5:alpha=1,"
        f"setpts=PTS-STARTPTS+{sign_in:.2f}/TB[sg];\n"
        f"[base][vs]overlay=0:0:eof_action=pass[b1];\n"
        f"[b1][sg]overlay=0:0:eof_action=pass,trim=duration={total:.2f},format=yuv420p[vout];\n"
        f"[{sg + 1}:a]adelay={int(NARR_IN*1000)}|{int(NARR_IN*1000)},apad=whole_dur={total:.2f},"
        f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"atrim=duration={total:.2f},loudnorm=I=-16:TP=-1.5:LRA=11[aout]\n")
    graph = filt.replace("\n", "")

    subprocess.run([
        "ffmpeg", "-v", "error",
        *[a for c in clips for a in ("-i", c)],
        "-loop", "1", "-t", f"{verse_hold:.2f}", "-i", verse_png,
        "-loop", "1", "-t", f"{sign_dur:.2f}", "-i", sign_png,
        "-i", narr,
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        # CRF 22 rather than 18: Instagram re-encodes on upload, so the extra bits are
        # discarded anyway, and this roughly halves the download on a phone.
        "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p", "-r", "24",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-y", out], check=True)
    return total, n


# ---------------------------------------------------------------- main
def main():
    if not TOKEN:
        raise SystemExit("REPLICATE_API_TOKEN is not set")

    settings = json.load(open(os.path.join(REPO, "studio/config/settings.json")))
    sets = json.load(open(os.path.join(REPO, "studio/verses/sets.json")))["sets"]
    ptr_path = os.path.join(REPO, "studio/state/reels-pointer.json")
    ptr = json.load(open(ptr_path))
    cfg = settings["reels"]

    today = os.environ.get("CHASTEN_DATE") or \
        datetime.now(ZoneInfo(settings.get("timezone", "America/Chicago"))).date().isoformat()
    if ptr.get("lastReelId") == today and not os.environ.get("CHASTEN_SET_TITLE"):
        log(f"a reel already exists for {today}, nothing to do")
        return

    # Do not repeat a verse the carousel used recently. The two run independently,
    # so without this the same passage can land in both formats in the same week.
    carousel = os.path.join(REPO, "studio/state/pointer.json")
    recent = set(json.load(open(carousel)).get("recentVerses", [])) if os.path.exists(carousel) else set()
    recent |= set(ptr.get("recentVerses", []))

    force = os.environ.get("CHASTEN_SET_TITLE")
    start = (next(i for i, x in enumerate(sets) if x["title"] == force) if force
             else ptr.get("nextSetIndex", 0) % len(sets))
    work = os.path.join(REPO, ".reelwork")
    os.makedirs(work, exist_ok=True)

    # Try candidate sets until one produces stills that pass the audit. A story whose
    # imagery cannot be rendered well is skipped rather than shipped, which is the
    # whole point: it is cheaper to abandon a set than to animate a bad one.
    chosen_set = None
    for attempt in range(6):
        idx = (start + attempt) % len(sets)
        cand = sets[idx]
        cand_refs = {v["ref"] for v in cand["verses"][:int(cand.get("verseCount", 1))]}
        if not force and (cand_refs & recent):
            log(f"  skip {cand['title']!r}: verses used recently")
            continue

        tone = cand.get("tone", cfg.get("defaultTone", "gentle"))
        scenes = cand.get("scenes") or cfg["scenes"][tone]
        narrative = bool(cand.get("scenes"))
        si = 0 if narrative else ptr.get("sceneIndex", 0)
        n_scenes = len(scenes) if narrative else 2
        scene_list = [scenes[(si + k) % len(scenes)] for k in range(n_scenes)]

        log(f"  trying {cand['title']!r} [{tone}]")
        stills, ok = [], True
        for k, sc in enumerate(scene_list, start=1):
            # Two rolls per beat. The model keeps adding people to some scenes even
            # when told not to, and a second attempt usually lands. Four cents each,
            # so it is far cheaper than dropping a good story over one bad roll.
            good = False
            for roll in range(4):
                dest = os.path.join(work, f"still{idx}_{k}.jpg")
                if roll:
                    os.remove(dest)
                # Escalate toward distance, not toward emptiness. Ordering the
                # model to remove people it insists on drawing produced worse
                # images; pushing them further away produces better ones.
                extra = ["",
                         " Push any figures further away and smaller in the frame.",
                         " Wide establishing shot from a great distance, figures tiny.",
                         " Landscape and architecture only, no figures at all."][roll]
                run_model(IMG_MODEL,
                          {"prompt": f"Cinematic photograph of {sc}. "
                                     + (PERIOD + ". " if narrative else "")
                                     + FRAME + (FIGURES if narrative else SCENERY) + extra,
                           "aspect_ratio": "9:16", "output_format": "jpg"}, dest)
                good, why = audit_still(dest, sc, cand["title"])
                log(f"    beat {k}{f' retry {roll}' if roll else ''}: "
                    f"{'PASS' if good else 'FAIL'} {why}")
                if good:
                    break
                time.sleep(5)
            if not good:
                ok = False
                break
            stills.append(dest)
            time.sleep(5)

        if ok:
            chosen_set = (idx, cand, tone, scenes, narrative, si, scene_list, stills)
            break
        log(f"  dropping {cand['title']!r} and moving on")

    if chosen_set is None:
        raise SystemExit("no candidate set produced usable stills")

    idx, vset, tone, scenes, narrative, si, scene_list, stills = chosen_set
    voice = cfg["voiceByTone"][tone]
    if isinstance(voice, list):
        # A tone can list more than one reader. Rotate by date so the same voice
        # does not carry every reel of that tone.
        voice = voice[datetime.fromisoformat(today).toordinal() % len(voice)]

    n_verses = int(vset.get("verseCount", 1))
    chosen = vset["verses"][:n_verses]
    text = " ".join(" ".join(v["text"].split()) for v in chosen)
    refs = [v["ref"] for v in chosen]
    ref_line = (refs[0] if len(refs) == 1 else f"{refs[0]} to {refs[-1]}") + \
        f"  ·  {settings.get('translation', 'BSB')}"

    outdir = os.path.join(REPO, "reels", today)
    os.makedirs(outdir, exist_ok=True)
    log(f"{today}  set {idx}: {vset['title']}  tone={tone}  voice={voice['voice_id']}")

    log("  narration")
    narr = os.path.join(work, "narr.mp3")
    speech = re.sub(r"(?<=[,;.])\s+", " <#0.35#> ", text)   # a beat at each clause
    run_model(TTS_MODEL, {"text": speech, "voice_id": voice["voice_id"],
                          "speed": voice.get("speed", 0.9), "pitch": voice.get("pitch", 0),
                          "emotion": "auto", "audio_format": "mp3"}, narr)
    narr_len = probe_duration(narr)

    # A thematic set may need a third scene once the narration length is known.
    if not narrative:
        want = clips_needed(narr_len)
        while len(stills) < want:
            k = len(stills) + 1
            sc = scenes[(si + k - 1) % len(scenes)]
            dest = os.path.join(work, f"still{idx}_{k}.jpg")
            run_model(IMG_MODEL, {"prompt": f"Cinematic photograph of {sc}. "
                                            f"{FRAME}{SCENERY}",
                                  "aspect_ratio": "9:16", "output_format": "jpg"}, dest)
            good, why = audit_still(dest, sc, vset["title"])
            log(f"    extra beat {k}: {'PASS' if good else 'FAIL'} {why}")
            if not good:
                break
            stills.append(dest); scene_list.append(sc)
    n_clips = len(stills)
    log(f"  narration {narr_len:.1f}s -> {n_clips} clips")

    log("  animating")
    clips = []
    for i, (still, sc) in enumerate(zip(stills, scene_list), start=1):
        dest = os.path.join(work, f"clip{i}.mp4")
        with open(still, "rb") as f:
            uri = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        run_model(VID_MODEL, {
            "prompt": ((f"{PERIOD}. " if narrative else "") +
                       f"Gentle natural movement in the scene: {sc}. Light shifts slowly and "
                       "the air moves. Cinematic photographic realism, unhurried. The camera is "
                       "nearly still with only the faintest slow drift."),
            "negative_prompt": MOTION_NEG, "duration": 10, "mode": "pro",
            "start_image": uri}, dest, poll=True)
        clips.append(dest)
        log(f"    clip {i} done")

    log("  typography")
    verse_png = os.path.join(work, "verse.png")
    sign_png = os.path.join(work, "signoff.png")
    make_verse_overlay(text, ref_line, verse_png)
    make_signoff_overlay(sign_png)

    log("  assembling")
    mp4 = os.path.join(outdir, "reel.mp4")
    total, narr_len = assemble(clips, verse_png, sign_png, narr, mp4)

    meta = {
        "date": today, "setIndex": idx, "title": vset["title"], "kind": vset["kind"],
        "tone": tone, "voice": voice["voice_id"],
        "verses": [{"ref": v["ref"], "text": " ".join(v["text"].split())} for v in chosen],
        "narrative": narrative,
        "refLine": ref_line, "onScreenText": text,
        "audioSearch": cfg["audioSearch"][tone],
        "context": vset.get("context", []),
        "scenes": scene_list, "clips": n_clips,
        "seconds": round(total, 2), "narrationSeconds": round(narr_len, 2),
        "sizeBytes": os.path.getsize(mp4),
        "url": f"https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/reels/{today}/reel.mp4",
        "builtAt": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
    }
    json.dump(meta, open(os.path.join(outdir, "meta.json"), "w"), ensure_ascii=False, indent=1)

    # Keep a rolling memory so neither format repeats itself or the other.
    hist = (ptr.get("recentVerses", []) + [v["ref"] for v in chosen])[-90:]
    titles = (ptr.get("recentTitles", []) + [vset["title"]])[-60:]
    if force:
        log("  preview build: pointer left untouched")
        log(f"  done: {mp4} ({meta['sizeBytes']//1024}KB, {meta['seconds']}s)")
        return

    ptr.update({"recentVerses": hist, "recentTitles": titles,
                "nextSetIndex": (idx + 1) % len(sets), "sceneIndex": ptr.get("sceneIndex", 0) if narrative else (si + n_clips) % len(scenes),
                "postCount": ptr.get("postCount", 0) + 1, "lastReelId": today})
    json.dump(ptr, open(ptr_path, "w"), indent=1)

    log(f"  done: {mp4} ({meta['sizeBytes']//1024}KB, {meta['seconds']}s)")


if __name__ == "__main__":
    main()
