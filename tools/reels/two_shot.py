#!/usr/bin/env python3
"""The Two-Shot: two separate clips of the creature, admired, the verse read
over them. Nothing chained, nothing waits for a peak.

Timeline: the hook sits in the top third while the first clip opens; the
reading starts a breath later and its words appear phrase by phrase in the
same band; a hard cut to the second clip at the first clip's end; the fact
follows the reading; the picture fades to dark and the close sits on it.

    python tools/reels/two_shot.py --clips a.mp4 b.mp4 --verse narr.mp3 \
        --verse-align align.json --fact fact.mp3 --fact-align fact.json \
        --hook "..." --ref "Jonah 1:17 · BSB" --fact-text "..." --fact-ref "Jonah 2:1" \
        --cta "Read Jonah 2 in Chasten" --out reel.mp4 [--bed bed.mp3]
"""
import argparse, json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moment as mo

W, H = mo.W, mo.H
BAND_Y, REF_Y = 230, 440            # the top third belongs to the words
T_VERSE = 2.4                       # the reading starts here, no matter what
NAT_GAIN, DUCK, BED_GAIN = 0.9, 0.32, 0.3


def build(a):
    tmp = tempfile.mkdtemp(prefix="twoshot-")
    lens = [mo.duration(c) for c in a.clips]
    footage = sum(lens)
    v_align = json.load(open(a.verse_align)); f_align = json.load(open(a.fact_align))
    v_len, f_len = mo.duration(a.verse), mo.duration(a.fact)
    t_verse = T_VERSE
    t_fact = t_verse + v_len + 0.8
    fact_end = t_fact + f_len
    fade_at = max(footage - 0.7, fact_end + 0.3) if fact_end + 0.3 <= footage - 0.7 else footage - 0.7
    t_cta = max(footage, fact_end + 0.6) + 0.3
    total = t_cta + 3.4
    report = {"clips": [os.path.basename(c) for c in a.clips], "clipSeconds": [round(x, 2) for x in lens],
              "footage": round(footage, 2), "verseStart": t_verse, "verseEnd": round(t_verse + v_len, 2),
              "factStart": round(t_fact, 2), "factEnd": round(fact_end, 2), "ctaStart": round(t_cta, 2),
              "total": round(total, 2), "factOnDark": fact_end > footage}

    overlays = []
    hook = mo.card(a.hook, os.path.join(tmp, "hook.png"), mo.SERIF, 64, y=BAND_Y)
    overlays.append((hook, 0.0, t_verse - 0.25))
    ph = mo.phrases(v_align)
    for i, (text, s, e) in enumerate(ph):
        png = mo.card(text, os.path.join(tmp, f"v{i}.png"), mo.SERIF, 64, y=BAND_Y)
        nxt = ph[i + 1][1] if i + 1 < len(ph) else e + 0.9
        overlays.append((png, t_verse + s, t_verse + nxt))
    ref = mo.card(a.ref, os.path.join(tmp, "ref.png"), mo.SANS, 34, fill=(255, 255, 255, 215), y=REF_Y)
    overlays.append((ref, t_verse + 0.3, t_fact - 0.15))
    fact = mo.card(a.fact_text, os.path.join(tmp, "fact.png"), mo.SERIF, 64, sub=a.fact_ref, y=BAND_Y)
    overlays.append((fact, t_fact, t_cta - 0.2))
    cta = mo.close_card(a.cta, os.path.join(tmp, "cta.png"))
    overlays.append((cta, t_cta, total))

    ins = []
    for c in a.clips: ins += ["-i", c]
    ins += ["-i", a.verse, "-i", a.fact]
    if a.bed: ins += ["-i", a.bed]
    first_png = ins.count("-i")
    for png, _, _ in overlays: ins += ["-loop", "1", "-framerate", "24", "-i", png]
    n = len(a.clips)
    fc = []
    for i in range(n):
        fc.append(f"[{i}:v]fps=24,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v{i}]")
    fc.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    fc.append(f"[vc]fade=t=out:st={fade_at:.2f}:d=0.7,tpad=stop_mode=add:stop_duration={total - footage + 1:.2f}:color=black[vb]")
    prev = "vb"
    for k, (_, s, e) in enumerate(overlays):
        fc.append(f"[{prev}][{first_png + k}:v]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'[o{k}]"); prev = f"o{k}"
    fc.append(f"[{prev}]trim=duration={total:.2f},setpts=PTS-STARTPTS[vout]")
    # the clips' own sound, cross-faded at the cut, quieter under the reading
    native = a.native != "none"
    if native:
        keep = n if a.native == "both" else 1
        for i in range(keep):
            fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        cross = "[a0]"
        for i in range(1, keep):
            fc.append(f"{cross}[a{i}]acrossfade=d=0.5:c1=tri:c2=tri[ax{i}]"); cross = f"[ax{i}]"
        nat_end = footage if keep == n else lens[0]
        fc.append(f"{cross}volume='if(between(t,{t_verse:.2f},{fact_end + 0.3:.2f}),{DUCK},{NAT_GAIN})':eval=frame,"
                  f"afade=t=out:st={nat_end - 0.8:.2f}:d=0.8,apad=whole_dur={total:.2f},atrim=duration={total:.2f}[nat]")
    fc.append(f"[{n}:a]aecho=0.8:0.55:38|61:0.14|0.09,adelay={int(t_verse * 1000)}|{int(t_verse * 1000)},"
              f"apad=whole_dur={total:.2f},atrim=duration={total:.2f}[vv]")
    fc.append(f"[{n + 1}:a]aecho=0.8:0.55:38|61:0.14|0.09,adelay={int(t_fact * 1000)}|{int(t_fact * 1000)},"
              f"apad=whole_dur={total:.2f},atrim=duration={total:.2f}[ff]")
    mix = ("[nat]" if native else "") + "[vv][ff]"; k = 3 if native else 2
    if a.bed:
        fc.append(f"[{n + 2}:a]aresample=48000,aformat=channel_layouts=stereo,volume={BED_GAIN},afade=t=in:d=1.5,"
                  f"volume='if(between(t,{t_verse:.2f},{fact_end + 0.3:.2f}),0.45,1)':eval=frame,"
                  f"apad=whole_dur={total:.2f},atrim=duration={total:.2f},afade=t=out:st={total - 1.6:.2f}:d=1.6[bd]")
        mix += "[bd]"; k += 1
    fc.append(f"{mix}amix=inputs={k}:normalize=0,loudnorm=I=-14:TP=-1.0:LRA=9[aout]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + ins + ["-filter_complex", ";".join(fc),
           "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
           "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    report["seconds"] = round(mo.duration(a.out), 2)
    json.dump(report, open(a.out + ".report.json", "w"), indent=1)
    print(json.dumps(report))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="+", required=True)
    for k in ("verse", "verse-align", "fact", "fact-align", "hook", "ref", "fact-text", "fact-ref", "cta", "out"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--bed")
    ap.add_argument("--native", choices=["both", "first", "none"], default="both",
                    help="keep the clips' own sound: both clips, only the first, or none (bed only)")
    build(ap.parse_args())
