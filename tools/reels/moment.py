#!/usr/bin/env python3
"""Assemble one Moment: a take with native sound, the reading placed after the
moment, the words revealed as they are spoken, a fact, a close.

    moment.py --take t.mp4 --verse v.mp3 --verse-align v.json --fact f.mp3
              --fact-align f.json --hook "What shut the lion's mouth?"
              --ref "Daniel 6:22" --fact-ref "Daniel 6:17" --book "Daniel 6" --out reel.mp4

The take is analysed, not trusted: the loudest transient in its audio and the
biggest motion in its frames must land within SYNC_TOL of each other or the take
is rejected. The end of that transient is where the moment closes, and the
reading starts a breath after it. A second take chained from the first's
last frame carries the reading; whatever footage still does not cover, the
picture fades to the dark of the setting and the fact and the close sit on that.
The animal is never looped or frozen: Ric called the loop "extremely creepy",
and he was right.
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 24
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIF = os.path.join(REPO, "tools/assets/fonts/Literata_400Regular.ttf")
SANS = os.path.join(REPO, "tools/assets/fonts/Inter_600SemiBold.ttf")
WORDMARK = os.path.join(REPO, "tools/assets/img/wordmark-white.png")
SYNC_HEAD = 0.5          # head motion at the sound peak, as a share of its own maximum
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 260, 1440, 96   # clear of Instagram's own UI


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed:\n{r.stderr[-1500:]}")


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip())


# ---------------------------------------------------------------- analysis
def analyse(take, tmp):
    """Where the moment is. The sound peak must coincide with the jaws moving,
    judged in the upper part of the frame where a low-angle shot keeps the head,
    not with the biggest motion anywhere, which is usually the animal walking in.
    Returns (t_peak, t_close, head_ratio, t_global_motion)."""
    sr, w = 8000, 400                                   # 50 ms windows, 20 fps frames
    raw = os.path.join(tmp, "a.raw"); gray = os.path.join(tmp, "v.gray")
    run(["ffmpeg", "-v", "error", "-i", take, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-y", raw])
    run(["ffmpeg", "-v", "error", "-i", take, "-vf", "scale=96:170,format=gray", "-r", "20", "-f", "rawvideo", "-y", gray])
    a = np.fromfile(raw, dtype="<i2").astype(float) / 32768
    n = len(a) // w
    env = np.sqrt((a[:n * w].reshape(n, w) ** 2).mean(axis=1))
    v = np.fromfile(gray, dtype=np.uint8); nf = len(v) // (96 * 170)
    v = v[:nf * 96 * 170].reshape(nf, 170, 96).astype(float)
    motion = np.abs(np.diff(v.reshape(nf, -1), axis=0)).mean(axis=1)
    head = np.abs(np.diff(v[:, :94, :].reshape(nf, -1), axis=0)).mean(axis=1)
    t_peak = float(np.argmax(env)) * w / sr
    lo, hi = max(0, int((t_peak - 0.4) * 20)), int((t_peak + 0.4) * 20) + 1
    local = head[lo:hi].max() if hi > lo and len(head[lo:hi]) else 0.0
    ratio = float(local / head.max()) if head.max() > 0 else 0.0
    loud = np.where(env >= 0.3 * env.max())[0]
    t_close = float(loud[-1] + 1) * w / sr                # end of the last loud window
    return t_peak, t_close, ratio, float(np.argmax(motion)) / 20


# ---------------------------------------------------------------- text
def phrases(align, max_words=6):
    """Word timings into lines of at most max_words, broken at punctuation."""
    words = [w for w in align["words"] if w.get("text", "").strip()]
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w["text"].rstrip()[-1:] in ".;,!?":
            lines.append(cur); cur = []
    if cur:
        lines.append(cur)
    return [(" ".join(w["text"].strip() for w in ln), ln[0]["start"], ln[-1]["end"]) for ln in lines]


def card(text, out, font_path, size, fill=(255, 255, 255, 255), sub=None, y=None, wrap_px=None):
    """One transparent overlay: text centred, a dark halo behind it for legibility."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    font = ImageFont.truetype(font_path, size)
    d = ImageDraw.Draw(img)
    maxw = wrap_px or (W - 2 * SAFE_SIDE)
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = wd
    lines.append(cur)
    lh = int(size * 1.3)
    block = len(lines) * lh + (int(size * 0.9) + 20 if sub else 0)
    top = y if y is not None else (SAFE_TOP + SAFE_BOTTOM) // 2 - block // 2
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0)); hd = ImageDraw.Draw(halo)
    for i, ln in enumerate(lines):
        x = (W - d.textlength(ln, font=font)) / 2
        hd.text((x, top + i * lh), ln, font=font, fill=(0, 0, 0, 230))
    from PIL import ImageFilter
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(18)))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(4)))
    for i, ln in enumerate(lines):
        x = (W - d.textlength(ln, font=font)) / 2
        d.text((x, top + i * lh), ln, font=font, fill=fill)
    if sub:
        fs = ImageFont.truetype(SANS, int(size * 0.55))
        x = (W - d.textlength(sub, font=fs)) / 2
        d.text((x, top + len(lines) * lh + 18), sub, font=fs, fill=(fill[0], fill[1], fill[2], 200))
    img.save(out)
    return out


def close_card(cta, out):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f = ImageFont.truetype(SANS, 46)
    wm = Image.open(WORDMARK).convert("RGBA"); wm = wm.resize((360, int(360 * wm.height / wm.width)))
    y = (SAFE_TOP + SAFE_BOTTOM) // 2 - 80
    img.alpha_composite(wm, ((W - wm.width) // 2, y))
    x = (W - d.textlength(cta, font=f)) / 2
    d.text((x, y + wm.height + 34), cta, font=f, fill=(255, 255, 255, 235))
    img.save(out); return out


# ---------------------------------------------------------------- build
def audit_frames(take, scene, tmp, start=0.0):
    """Look at the take the way the still audit looks at a still: several frames,
    the same rubric, reject on any person. Veo put a kneeling figure in an empty
    opening shot that nothing else would have caught."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mr", os.path.join(REPO, "tools/reels/make_reel.py"))
    mr = importlib.util.module_from_spec(spec); spec.loader.exec_module(mr)
    length = duration(take)
    times = [t for t in (start + 0.1, start + 0.6, start + 1.3, start + 2.5, (start + length) / 2, length - 0.4) if t < length]
    bad = []
    for t in times:
        f = os.path.join(tmp, f"audit-{t:.1f}.jpg")
        run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", take, "-frames:v", "1", "-y", f])
        # Only the defects a take can hide from the still audit: a person, or
        # something modern. Subject fidelity is judged by eye and by the sync gate;
        # asking a model to name the animal in a motion-blurred frame is how a
        # charging lion gets called a bear.
        ok, why = frame_people_check(mr, f)
        if not ok:
            bad.append((round(t, 1), why))
    return bad


def frame_people_check(mr, path):
    import base64, json, re
    with open(path, "rb") as fh:
        uri = "data:image/jpeg;base64," + base64.b64encode(fh.read()).decode()
    q = ("Look carefully at the whole image, including small and distant areas. Reply strictly as JSON with keys "
         "ok (true/false) and reason. Set ok to false ONLY if you can see (a) any person, human figure, silhouette, "
         "human hand or human shadow, however small or distant, or (b) anything modern such as vehicles, machinery, "
         "electric lights, modern clothing or lettering. Animals, fire, water, weather, rock and darkness are all fine. "
         "Motion blur is fine. Do not judge what animal it is or whether the setting matches anything.")
    try:
        p = mr.api(f"https://api.replicate.com/v1/models/{mr.VLM}/predictions",
                   {"input": {"prompt": q, "image_input": [uri], "temperature": 0, "max_completion_tokens": 120}}, wait=True)
        out = p.get("output"); txt = "".join(out) if isinstance(out, list) else str(out)
        m = re.search(r"\{.*?\}", txt, re.S)
        v = json.loads(m.group()) if m else {"ok": True, "reason": "unparsed"}
        return bool(v.get("ok", True)), str(v.get("reason", ""))[:120]
    except Exception as e:
        return True, f"audit skipped ({type(e).__name__})"


def build(a):
    tmp = tempfile.mkdtemp(prefix="moment-")
    if a.trim_start > 0:
        trimmed = os.path.join(tmp, "take.mp4")
        run(["ffmpeg", "-v", "error", "-ss", f"{a.trim_start:.2f}", "-i", a.take, "-c:v", "libx264", "-crf", "16",
             "-c:a", "aac", "-b:a", "256k", "-y", trimmed])
        a.take = trimmed
    if a.scene:
        bad = audit_frames(a.take, a.scene, tmp)
        if bad and not a.force:
            sys.exit("REJECTED by frame audit: " + "; ".join(f"{t}s {why}" for t, why in bad))
    t_peak, t_close, ratio, t_motion = analyse(a.take, tmp)
    take_len = duration(a.take)
    report = {"take": os.path.basename(a.take), "takeSeconds": round(take_len, 2), "soundPeak": round(t_peak, 2),
              "headMotionAtPeak": round(ratio, 2), "biggestMotion": round(t_motion, 2),
              "moment_close": round(t_close, 2), "synced": ratio >= SYNC_HEAD}
    if not report["synced"] and not a.force:
        print(json.dumps(report, indent=1)); sys.exit("REJECTED: sound and motion do not meet")

    verse_al = json.load(open(a.verse_align)); fact_al = json.load(open(a.fact_align))
    v_len, f_len = duration(a.verse), duration(a.fact)
    ext_len = duration(a.extend) if a.extend else 0.0
    footage = take_len + ext_len
    t_verse = t_close + 0.5                                 # a breath after the jaws shut
    # The fact and the close sit on the dark after the footage ends, so the verse
    # is read over the animal and nothing after it is ever a still.
    t_fact = max(t_verse + v_len + 0.9, footage + 0.4)
    t_cta = t_fact + f_len + 0.8
    total = t_cta + 3.6
    dark = max(0.0, total - footage)
    report.update({"verseStart": round(t_verse, 2), "footage": round(footage, 2), "factStart": round(t_fact, 2),
                   "ctaStart": round(t_cta, 2), "total": round(total, 2), "darkTail": round(dark, 2),
                   "verseOverrunsFootage": round(max(0.0, t_verse + v_len - footage), 2)})

    # Overlays: hook until just before the moment, verse lines on their word times,
    # the fact with its reference, then the close.
    overlays = []   # (png, start, end)
    hook = card(a.hook, os.path.join(tmp, "hook.png"), SANS, 58)
    overlays.append((hook, 0.0, max(0.4, t_peak - 0.25)))
    for i, (text, s, e) in enumerate(phrases(verse_al)):
        png = card(text, os.path.join(tmp, f"v{i}.png"), SERIF, 66)
        nxt = phrases(verse_al)[i + 1][1] if i + 1 < len(phrases(verse_al)) else v_len + 0.4
        overlays.append((png, t_verse + s, t_verse + nxt))
    ref = card(a.ref + "  ·  BSB", os.path.join(tmp, "ref.png"), SANS, 34, y=SAFE_BOTTOM - 60)
    overlays.append((ref, t_verse + 0.3, t_fact - 0.1))
    fact = card(a.fact_text, os.path.join(tmp, "fact.png"), SANS, 50, sub=a.fact_ref)
    overlays.append((fact, t_fact, t_cta - 0.2))
    cta = close_card(a.cta, os.path.join(tmp, "cta.png"))
    overlays.append((cta, t_cta, total))

    # Video: the take, the chained take if there is one, and then a fade into the
    # dark for whatever the footage does not cover. Nothing is looped or held.
    ins = ["-i", a.take]
    filt = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1[t0];"
    if a.extend:
        ins += ["-i", a.extend]
        filt += (f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1[t1];"
                 f"[t0][t1]concat=n=2:v=1:a=0[foot];")
    else:
        filt += "[t0]null[foot];"
    if dark > 0.05:
        fade = min(1.2, dark)
        ins += ["-f", "lavfi", "-t", f"{dark + 0.3:.2f}", "-i", f"color=c=black:s={W}x{H}:r={FPS}"]
        filt += (f"[foot]fade=t=out:st={footage - fade:.2f}:d={fade:.2f}[footf];"
                 f"[{2 if a.extend else 1}:v]setsar=1[blk];[footf][blk]concat=n=2:v=1:a=0[v0];")
        vin = "[v0]"
    else:
        vin = "[foot]"
    idx = ins.count("-i")
    prev = vin
    for i, (png, s, e) in enumerate(overlays):
        ins += ["-loop", "1", "-i", png]
        filt += (f"[{idx + i}:v]format=rgba,fade=t=in:st={s:.2f}:d=0.35:alpha=1,fade=t=out:st={max(e - 0.3, s):.2f}:d=0.3:alpha=1[o{i}];"
                 f"{prev}[o{i}]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'[m{i}];")
        prev = f"[m{i}]"
    filt += f"{prev}trim=duration={total:.2f},format=yuv420p[vout];"

    # Audio: the take's own sound, its tail looped softly under the extension, the
    # reading with a little of the room on it, gently held under by nothing that
    # would crush the moment. Loudness for phones.
    ai = ins.count("-i")
    ins += ["-i", a.verse, "-i", a.fact]
    if a.extend:
        filt += (f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a0];"
                 f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a1];"
                 f"[a0][a1]concat=n=2:v=0:a=1,asplit=2[nat][tailsrc];")
    else:
        filt += f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asplit=2[nat][tailsrc];"
    tail_start = max(0.0, footage - 2.5)
    filt += (f"[tailsrc]atrim=start={tail_start:.2f},asetpts=PTS-STARTPTS,aloop=loop=-1:size=120000,"
             f"adelay={int(footage * 1000)}|{int(footage * 1000)},volume=0.4,atrim=duration={total:.2f}[tail];"
             f"[nat]apad=whole_dur={total:.2f},atrim=duration={total:.2f}[natp];"
             f"[natp][tail]amix=inputs=2:duration=first:normalize=0[amb];"
             f"[{ai}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
             f"aecho=0.8:0.55:38|61:0.14|0.09,adelay={int(t_verse * 1000)}|{int(t_verse * 1000)},apad=whole_dur={total:.2f},atrim=duration={total:.2f}[vv];"
             f"[{ai + 1}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
             f"aecho=0.8:0.55:38|61:0.14|0.09,adelay={int(t_fact * 1000)}|{int(t_fact * 1000)},apad=whole_dur={total:.2f},atrim=duration={total:.2f}[ff];"
             f"[vv][ff]amix=inputs=2:duration=first:normalize=0,volume=1.6[voice];"
             f"[amb][voice]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.0:LRA=9[aout]")
    run(["ffmpeg", "-v", "error", *ins, "-filter_complex", filt, "-map", "[vout]", "-map", "[aout]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-y", a.out])
    report["out"] = a.out; report["outSeconds"] = round(duration(a.out), 2)
    json.dump(report, open(os.path.splitext(a.out)[0] + ".report.json", "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("take", "verse", "verse_align", "fact", "fact_align", "hook", "ref", "fact_ref", "fact_text", "cta", "out"):
        p.add_argument("--" + k.replace("_", "-"), required=True)
    p.add_argument("--force", action="store_true", help="assemble even if a gate fails")
    p.add_argument("--extend", default="", help="a second take chained from the first's last frame")
    p.add_argument("--trim-start", type=float, default=0.0, help="drop this many seconds from the take's opening")
    p.add_argument("--scene", default="", help="scene text for the frame audit; empty skips it")
    args = p.parse_args(); args.extend = args.extend or None
    build(args)
