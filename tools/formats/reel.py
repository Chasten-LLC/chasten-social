"""
"Stop on your verse": a 1080 x 1920 reel. One of the app's photos drifts in
slowly; a line at the top says to hold the screen; inside a paper card the
verse changes every few frames, too fast to read, so whoever holds the screen
stops on one. Only the words in the card change, never the whole frame, so the
reel does not strobe. Every verse is a whole BSB verse set in real type.

    render(out_mp4, verses, photo_path, music_path)
"""

import os
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from . import common as c

FPS = 30
HOLD = 5                      # frames each verse stays up (six a second)
PUSH = 0.07                   # how far the photo drifts in over the reel
CARD = (90, 600, 990, 1200)
CARD_R = 44


def ffmpeg_bin():
    exe = None if os.environ.get("CHASTEN_FFMPEG") == "imageio" else shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
    except ImportError:
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "imageio-ffmpeg"])
        import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def tall_crop(photo_path, focus_x=0.5, w=c.RW, h=c.RH, margin=PUSH):
    """A 9:16 slice of a landscape photo, a little larger than the frame so the
    drift never runs out of picture."""
    im = Image.open(photo_path).convert("RGB")
    sw, sh = im.size
    cw = int(round(sh * w / h))
    x0 = int(round(min(max(focus_x * sw - cw / 2, 0), sw - cw)))
    im = im.crop((x0, 0, x0 + cw, sh))
    big = (int(w * (1 + margin)), int(h * (1 + margin)))
    return im.resize(big, Image.LANCZOS)


def _card_layer(verse, ref):
    x0, y0, x1, y1 = CARD
    cw, ch = x1 - x0, y1 - y0
    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size, lines = c.fit(verse, "serif-md", cw - 150, ch - 210, 62, 36, leading=1.32)
    f = c.font("serif-md", size)
    pitch = size * 1.32
    block = len(lines) * pitch + 70
    top = (ch - block) / 2
    bottom = c.text_block(d, lines, f, cw / 2, top, pitch, c.INK)
    c.draw_tracked(d, (cw / 2, bottom + 60), ref.upper(), c.font("sans-sb", 29), c.GOLD, 3.0, anchor="ms")
    return layer


def _static_overlay(hook, note):
    im = Image.new("RGBA", (c.RW, c.RH), (0, 0, 0, 0))
    # the card's paper and shadow never change; only its words do
    im.alpha_composite(c.drop_shadow((c.RW, c.RH), CARD, CARD_R, blur=34, alpha=0.35, offset=(0, 18)))
    x0, y0, x1, y1 = CARD
    paper = c.paper((x1 - x0, y1 - y0), seed=3, vignette=0.0)
    im.paste(paper, (x0, y0), c.rounded_mask(paper.size, CARD_R))
    text = Image.new("RGBA", (c.RW, c.RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(text)
    hf = c.font("serif-b", 78)
    for i, line in enumerate(hook):
        d.text((c.RW / 2, 352 + i * 94), line, font=hf, fill=(255, 255, 255, 255), anchor="ms")
    d.text((c.RW / 2, 1290), note, font=c.font("hand-b", 58), fill=(255, 236, 200, 255), anchor="ms")
    im.alpha_composite(c.shadow_layer(text, 18, 0.75))
    im.alpha_composite(text)
    wm = c.wordmark("white", 190, 0.75)
    im.alpha_composite(wm, ((c.RW - wm.width) // 2, 1380))
    return im


def render(out_mp4, verses, photo_path, music_path=None, focus_x=0.5, music_start=0.0,
           hook=("Hold the screen to", "stop on a verse"), note="every one of these is true"):
    """verses: [(text, ref)] in the order they flash. Returns the mp4 path."""
    silent = out_mp4 + ".video.mp4"
    seconds = encode_video(silent, verses, photo_path, focus_x, hook, note)
    if music_path:
        add_music(silent, music_path, out_mp4, seconds, music_start)
        os.remove(silent)
    else:
        os.replace(silent, out_mp4)
    return out_mp4


def encode_video(silent, verses, photo_path, focus_x=0.5,
                 hook=("Hold the screen to", "stop on a verse"), note="every one of these is true"):
    """The picture alone. Returns its length in seconds."""
    bg = tall_crop(photo_path, focus_x)
    ys = np.linspace(0, 1, c.RH)[:, None, None]
    veil = 0.22 + 0.30 * np.clip(1 - ys / 0.32, 0, 1) + 0.25 * np.clip((ys - 0.62) / 0.38, 0, 1)
    static = _static_overlay(hook, note)
    cards = [_card_layer(t, r) for t, r in verses]
    x0, y0 = CARD[0], CARD[1]
    n = len(verses) * HOLD
    os.makedirs(os.path.dirname(os.path.abspath(silent)), exist_ok=True)
    proc = subprocess.Popen([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{c.RW}x{c.RH}", "-r", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                             "-movflags", "+faststart", silent], stdin=subprocess.PIPE)
    bw, bh = bg.size
    for i in range(n):
        s = 1 + PUSH * (1 - i / max(1, n - 1))          # drift in: start wide, end close
        cw, ch = min(c.RW * s, bw), min(c.RH * s, bh)
        left, top = max(0.0, (bw - cw) / 2), max(0.0, (bh - ch) * 0.45)
        frame = bg.resize((c.RW, c.RH), Image.BICUBIC, box=(left, top, left + cw, top + ch))
        arr = np.asarray(frame, dtype=np.float32) * (1 - veil) + 8 * veil
        frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        frame.alpha_composite(static)
        frame.alpha_composite(cards[i // HOLD], (x0, y0))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed while encoding the reel")
    return n / FPS


def add_music(silent, music_path, out_mp4, seconds, start=0.0, fade=0.35):
    """Lay a stretch of the track under the picture, evened out to -16 LUFS,
    with a short fade at each end so the loop back to the start is soft."""
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", silent, "-i", music_path,
                    "-filter_complex", f"[1:a]atrim={start:.3f}:{start + seconds:.3f},asetpts=PTS-STARTPTS,"
                    f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.12,afade=t=out:st={seconds - fade:.3f}:d={fade},"
                    "aformat=sample_rates=48000:channel_layouts=stereo[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    return out_mp4


def still(out_jpg, verse, ref, photo_path, focus_x=0.5, hook=("Hold the screen to", "stop on a verse"),
          note="every one of these is true"):
    """One frame, for previews and the reel's cover."""
    bg = tall_crop(photo_path, focus_x).resize((c.RW, c.RH), Image.LANCZOS)
    ys = np.linspace(0, 1, c.RH)[:, None, None]
    veil = 0.22 + 0.30 * np.clip(1 - ys / 0.32, 0, 1) + 0.25 * np.clip((ys - 0.62) / 0.38, 0, 1)
    arr = np.asarray(bg, dtype=np.float32) * (1 - veil) + 8 * veil
    frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    frame.alpha_composite(_static_overlay(hook, note))
    frame.alpha_composite(_card_layer(verse, ref), (CARD[0], CARD[1]))
    return c.save(frame, out_jpg)


def cover(out_jpg, photo_path, focus_x=0.5, hook=("Hold the screen to", "stop on a verse"),
          note="every one of these is true"):
    """The reel's cover for the grid: the same frame, its card naming the game."""
    bg = tall_crop(photo_path, focus_x).resize((c.RW, c.RH), Image.LANCZOS)
    ys = np.linspace(0, 1, c.RH)[:, None, None]
    veil = 0.22 + 0.30 * np.clip(1 - ys / 0.32, 0, 1) + 0.25 * np.clip((ys - 0.62) / 0.38, 0, 1)
    arr = np.asarray(bg, dtype=np.float32) * (1 - veil) + 8 * veil
    frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    frame.alpha_composite(_static_overlay(hook, note))
    x0, y0, x1, y1 = CARD
    card = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    f = c.font("serif-b", 92)
    d.text((card.width / 2, card.height / 2 - 40), "Stop on", font=f, fill=c.INK, anchor="ms")
    d.text((card.width / 2, card.height / 2 + 66), "your verse", font=f, fill=c.INK, anchor="ms")
    d.text((card.width / 2, card.height / 2 + 158), "hold the screen to try", font=c.font("hand-b", 54), fill=c.GOLD, anchor="ms")
    frame.alpha_composite(card, (x0, y0))
    return c.save(frame, out_jpg)
