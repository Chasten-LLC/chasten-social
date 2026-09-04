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
         "no text, no words, no lettering, no watermark, no people, no faces")
MOTION_NEG = ("people, person, faces, animals, birds, morphing, warping, melting, distortion, "
              "fast motion, camera shake, zoom, text, letters, watermark, logo, style change")


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
    prev, off = "v0", CLIP - XFADE
    for i in range(1, len(clips)):
        lbl = "base" if i == len(clips) - 1 else f"x{i}"
        filt += f"[{prev}][v{i}]xfade=transition=fade:duration={XFADE}:offset={off}[{lbl}];\n"
        prev, off = lbl, off + CLIP - XFADE
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
    fp = os.path.join(os.path.dirname(out), "filter.txt")
    open(fp, "w").write(filt)

    subprocess.run([
        "ffmpeg", "-v", "error",
        *[a for c in clips for a in ("-i", c)],
        "-loop", "1", "-t", f"{verse_hold:.2f}", "-i", verse_png,
        "-loop", "1", "-t", f"{sign_dur:.2f}", "-i", sign_png,
        "-i", narr,
        "-/filter_complex", fp,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "24",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-y", out], check=True)
    os.remove(fp)
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
    if ptr.get("lastReelId") == today:
        log(f"a reel already exists for {today}, nothing to do")
        return

    idx = ptr.get("nextSetIndex", 0) % len(sets)
    vset = sets[idx]
    tone = vset.get("tone", cfg.get("defaultTone", "gentle"))
    voice = cfg["voiceByTone"][tone]
    scenes = cfg["scenes"][tone]
    si = ptr.get("sceneIndex", 0)

    # One verse per Reel. Three belong on a carousel, where people read at their own
    # pace; a Reel is watched, and shorter finishes better, which is what drives reach.
    verse = vset["verses"][0]
    text = " ".join(verse["text"].split())
    ref_line = f"{verse['ref']}  ·  {settings.get('translation', 'BSB')}"

    work = os.path.join(REPO, ".reelwork")
    outdir = os.path.join(REPO, "reels", today)
    os.makedirs(work, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)

    log(f"{today}  set {idx}: {vset['title']}  tone={tone}  voice={voice['voice_id']}")

    log("  narration")
    narr = os.path.join(work, "narr.mp3")
    speech = re.sub(r"(?<=[,;])\s+", " <#0.35#> ", text)   # a beat at each clause
    run_model(TTS_MODEL, {"text": speech, "voice_id": voice["voice_id"],
                          "speed": voice.get("speed", 0.9), "pitch": voice.get("pitch", 0),
                          "emotion": "auto", "audio_format": "mp3"}, narr)

    # Narration length decides how much footage to buy, so a long verse gets a
    # third clip instead of overrunning the runway and breaking the edit.
    narr_len = probe_duration(narr)
    n_clips = clips_needed(narr_len)
    scene_list = [scenes[(si + k) % len(scenes)] for k in range(n_clips)]
    log(f"  narration {narr_len:.1f}s -> {n_clips} clips")

    log("  stills")
    stills = []
    for i, sc in enumerate(scene_list, start=1):
        dest = os.path.join(work, f"still{i}.jpg")
        run_model(IMG_MODEL, {"prompt": f"Cinematic photograph of {sc}. {FRAME}",
                              "aspect_ratio": "9:16", "output_format": "jpg"}, dest)
        stills.append(dest)
        time.sleep(6)

    log("  animating")
    clips = []
    for i, (still, sc) in enumerate(zip(stills, scene_list), start=1):
        dest = os.path.join(work, f"clip{i}.mp4")
        with open(still, "rb") as f:
            uri = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        run_model(VID_MODEL, {
            "prompt": (f"Gentle natural movement in the scene: {sc}. Light shifts slowly and "
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
        "verses": [{"ref": verse["ref"], "text": text}],
        "refLine": ref_line, "onScreenText": text,
        "audioSearch": cfg["audioSearch"][tone],
        "scenes": scene_list, "clips": n_clips,
        "seconds": round(total, 2), "narrationSeconds": round(narr_len, 2),
        "sizeBytes": os.path.getsize(mp4),
        "url": f"https://raw.githubusercontent.com/Chasten-LLC/chasten-social/main/reels/{today}/reel.mp4",
        "builtAt": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
    }
    json.dump(meta, open(os.path.join(outdir, "meta.json"), "w"), ensure_ascii=False, indent=1)

    ptr.update({"nextSetIndex": (idx + 1) % len(sets), "sceneIndex": (si + n_clips) % len(scenes),
                "postCount": ptr.get("postCount", 0) + 1, "lastReelId": today})
    json.dump(ptr, open(ptr_path, "w"), indent=1)

    log(f"  done: {mp4} ({meta['sizeBytes']//1024}KB, {meta['seconds']}s)")


if __name__ == "__main__":
    main()
