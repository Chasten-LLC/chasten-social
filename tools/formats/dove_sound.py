"""
The traveling dove's sound: harp music under the whole flight, recorded
wingbeats that follow the dove across each slide (louder as it crosses, panned
with it, fading at the edges), and a soft flutter as it lands. Ric heard it on
2026-10-08 and wanted it every Sunday ("the music was so good").

The audio is made once and kept in studio/audio (see its README for licences):
dove-harp.mp3 is ElevenLabs music, dove-wings.mp3 and dove-landing.mp3 are
ElevenLabs sound effects. Never synthesize wingbeats in code: Ric judged those
"terrible".

Each slide is its own video in an Instagram carousel, so the mix is cut into one
slice per slide and muxed into that slide's MP4, in Instagram's format: AAC 128k
at 48 kHz, no edit list, moov first.
"""

import json
import math
import os
import subprocess
import wave

import numpy as np

from . import common as c
from .reel import ffmpeg_bin
from .traveling import FPS

AUDIO = os.path.join(c.ROOT, "studio", "audio")
MUSIC = os.path.join(AUDIO, "dove-harp.mp3")
MUSIC_START = 0.19      # the first harp note
WINGS = os.path.join(AUDIO, "dove-wings.mp3")
LANDING = os.path.join(AUDIO, "dove-landing.mp3")
WINGS_DB = -3.0         # the wingbeats against the music: clearly there, the music still in front
SR = 48000
SPF = SR // FPS         # audio samples per video frame


def _load(path, start=0.0, channels=1):
    raw = subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-ss", str(start), "-i", path, "-f", "f32le",
                          "-ac", str(channels), "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.float32).astype(np.float64)
    return a.reshape(-1, channels) if channels > 1 else a


def _write_wav(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def _visible(rel):
    a = min(1.0, max(0.0, (rel + 150) / 200))          # entering at the left edge
    b = min(1.0, max(0.0, (c.W + 150 - rel) / 200))    # leaving at the right edge
    return a * b


def _pan(rel):
    p = max(-0.85, min(0.85, rel / c.W * 2 - 1))
    return math.cos((p + 1) * math.pi / 4), math.sin((p + 1) * math.pi / 4)


def _rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def mix(rows):
    """The whole flight's audio, stereo, one row of (rel_x, flying) per slide."""
    lengths = [len(r) * SPF for r in rows]
    total = sum(lengths)
    steady = _load(WINGS)[int(0.08 * SR):int(3.25 * SR)]
    landing = _load(LANDING)
    xf = int(0.06 * SR)
    bed = steady.copy()
    while len(bed) < 12 * SR:  # the steady take looped with short crossfades
        ramp = np.linspace(0, 1, xf)
        bed = np.concatenate([bed[:-xf], bed[-xf:] * (1 - ramp) + steady[:xf] * ramp, steady[xf:]])

    wings = np.zeros((total, 2))
    offset = 0
    for k, row in enumerate(rows):
        L = lengths[k]
        tf = (np.arange(len(row)) + 0.5) * SPF
        ts = np.arange(L)
        g = np.interp(ts, tf, [_visible(rel) if flying else 0.0 for rel, flying in row])
        g = np.convolve(g, np.ones(480) / 480, mode="same")  # 10 ms smoothing
        p = np.interp(ts, tf, [max(-0.85, min(0.85, rel / c.W * 2 - 1)) for rel, _ in row])
        src = bed[int(k * 0.37 * SR):int(k * 0.37 * SR) + L].copy()
        fade = min(L, int(0.06 * SR))
        src[:fade] *= np.linspace(0, 1, fade)
        wings[offset:offset + L, 0] += src * g * np.cos((p + 1) * np.pi / 4)
        wings[offset:offset + L, 1] += src * g * np.sin((p + 1) * np.pi / 4)
        if k == len(rows) - 1:  # touchdown
            f_land = next((i for i, (_, fl) in enumerate(row) if not fl), len(row) - 1)
            gl, gr = _pan(row[f_land][0])
            i0 = offset + max(0, int((f_land / FPS - 0.12) * SR))
            s = landing * (0.5 / (np.abs(landing).max() + 1e-9)) * np.abs(steady).max()
            s = s[:max(0, offset + L - i0)]
            wings[i0:i0 + len(s), 0] += s * gl
            wings[i0:i0 + len(s), 1] += s * gr
        offset += L

    music = _load(MUSIC, MUSIC_START, channels=2)[:total]
    if len(music) < total:
        music = np.vstack([music, np.zeros((total - len(music), 2))])
    fade = min(total, SR)
    music[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
    music[:240] *= np.linspace(0, 1, 240)[:, None]

    heard = wings[np.abs(wings).max(1) > 0.02 * (np.abs(wings).max() + 1e-12)]
    if len(heard):
        wings *= 10 ** ((_rms_db(music[:min(total, 10 * SR)]) + WINGS_DB - _rms_db(heard)) / 20)
    return music + wings, lengths


def add(out_dir, rows, work_dir):
    """Mix, bring to -16 LUFS, and mux one slice into each slide's MP4 (1.mp4, 2.mp4, ...)."""
    os.makedirs(work_dir, exist_ok=True)
    full, lengths = mix(rows)
    raw = os.path.join(work_dir, "dove-mix-raw.wav")
    _write_wav(raw, full / max(1.0, np.abs(full).max() / 0.98))
    ff = ffmpeg_bin()
    m1 = subprocess.run([ff, "-hide_banner", "-i", raw, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                         "-f", "null", "-"], capture_output=True, text=True).stderr
    meas = json.loads(m1[m1.rindex("{"):m1.rindex("}") + 1])
    af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
          f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:"
          f"offset={meas['target_offset']}:linear=true")
    norm = os.path.join(work_dir, "dove-mix.wav")
    subprocess.run([ff, "-loglevel", "error", "-y", "-i", raw, "-af", af, "-ar", str(SR), norm], check=True)
    with wave.open(norm) as w:
        final = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2) / 32767.0

    offset = 0
    for k, L in enumerate(lengths):
        seg = np.zeros((L, 2))
        got = final[offset:offset + L]
        seg[:len(got)] = got
        edge = 240  # 5 ms: no click where Instagram loops a slide
        seg[:edge] *= np.linspace(0, 1, edge)[:, None]
        seg[-edge:] *= np.linspace(1, 0, edge)[:, None]
        wav = os.path.join(work_dir, f"dove-{k + 1}.wav")
        _write_wav(wav, seg)
        video = os.path.join(out_dir, f"{k + 1}.mp4")
        tmp = os.path.join(work_dir, f"dove-{k + 1}.mp4")
        subprocess.run([ff, "-loglevel", "error", "-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", str(SR), "-ac", "2",
                        "-use_editlist", "0", "-movflags", "+faststart", tmp], check=True)
        os.replace(tmp, video)
        offset += L
    return meas["input_i"]
