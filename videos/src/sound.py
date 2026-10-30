import os
import re
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import signal

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.environ.get("SOUND_ASSETS", os.path.join(ROOT, "sound_assets"))
FFMPEG = shutil.which("ffmpeg") or os.path.join(os.path.expanduser("~"), "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe")
SR = 48000
DURATION = 29.5
LOUDNESS = -14.0
TRUE_PEAK = -1.5

NOTES = {"G#3": 207.65, "G#4": 415.30, "B4": 493.88, "C#5": 554.37, "D#5": 622.25, "F#5": 739.99, "G#5": 830.61, "B5": 987.77, "C#6": 1108.73, "D#6": 1244.51, "F#6": 1479.98, "G#6": 1661.22}
ROLES = {"tick": -3.0, "ui": 1.0, "msg": 3.0, "bell": 0.0, "accent": 4.0, "drop": 6.0, "whoosh": -1.0, "soft": -6.0}
PEAK_LIMITS = {"accent": -3.0, "drop": -3.0, "msg": -5.0, "ui": -6.0, "tick": -7.0, "bell": -6.0, "whoosh": -7.0, "soft": -7.0}


def load(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def gain(db):
    return 10 ** (db / 20)


def level(audio):
    return 20 * np.log10(np.sqrt(np.mean(audio.astype(np.float64) ** 2)) + 1e-12)


def finished(out, fade=0.04):
    out = out.astype(np.float32)
    n = min(len(out), int(fade * SR))
    out[-n:] *= np.linspace(1, 0, n, dtype=np.float32)[:, None]
    return out / (np.abs(out).max() + 1e-9) * gain(-1)


cache = {}


def sfx(name):
    if name not in cache:
        cache[name] = finished(load(os.path.join(ASSETS, "sfx", f"{name}.wav")), fade=0.005)
    return cache[name]


def pitched(sample, semitones):
    if not semitones:
        return sample
    length = int(len(sample) / 2 ** (semitones / 12))
    source = np.arange(len(sample))
    target = np.linspace(0, len(sample) - 1, length)
    return np.stack([np.interp(target, source, sample[:, channel]) for channel in range(2)], axis=1).astype(np.float32)


def pluck(freq, decay=0.11, length=0.6):
    t = np.arange(int(length * SR)) / SR
    attack = 1 - np.exp(-t / 0.0015)
    noise = np.random.default_rng(int(freq)).standard_normal(len(t)) * np.exp(-t / 0.0015) * 0.08
    left = np.sin(2 * np.pi * freq * t) * np.exp(-t / decay)
    left += 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / (decay * 0.45))
    left += 0.12 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / (decay * 0.28))
    right = np.sin(2 * np.pi * (freq + 0.6) * t) * np.exp(-t / decay) + 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / (decay * 0.45))
    return finished(np.stack([left * attack + noise, right * attack + noise], axis=1))


def bell(freq, length=1.6):
    t = np.arange(int(length * SR)) / SR
    partials = [(1.0, 1.0, 0.55), (2.0, 0.35, 0.28), (3.01, 0.22, 0.14), (4.2, 0.12, 0.08)]
    mono = sum(amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / tau) for ratio, amp, tau in partials) * (1 - np.exp(-t / 0.002))
    return finished(np.stack([mono, np.roll(mono, 24)], axis=1), fade=0.3)


def bubble(f0=520, f1=1180, length=0.22):
    t = np.arange(int(length * SR)) / SR
    phase = 2 * np.pi * np.cumsum(f0 + (f1 - f0) * (1 - np.exp(-t / 0.018))) / SR
    mono = (np.sin(phase) + 0.18 * np.sin(2 * phase)) * (1 - np.exp(-t / 0.002)) * np.exp(-t / 0.055)
    return finished(np.stack([mono, np.roll(mono, 18)], axis=1))


def sub_boom(length=0.9):
    t = np.arange(int(length * SR)) / SR
    phase = 2 * np.pi * np.cumsum(34 + 26 * np.exp(-t / 0.18)) / SR
    mono = np.tanh(1.6 * np.sin(phase) * np.exp(-t / 0.32) * (1 - np.exp(-t / 0.003)))
    return finished(np.stack([mono, mono], axis=1), fade=0.25)


def glide(length, f0, f1):
    t = np.arange(int(length * SR)) / SR
    phase = 2 * np.pi * np.cumsum(f0 * (f1 / f0) ** (t / length)) / SR
    mono = (np.sin(phase) + 0.25 * np.sin(2 * phase)) * (t / length) ** 1.6
    return finished(np.stack([mono, mono], axis=1), fade=0.03)


def place(bus, x, at, db=0.0, anchor=0.0, pan=0.0):
    x = x * gain(db)
    if pan:
        angle = (pan + 1) * np.pi / 4
        x = x * np.array([np.cos(angle), np.sin(angle)], dtype=np.float32) * np.sqrt(2)
    start = int(round((at - anchor) * SR))
    lo, hi = max(0, start), min(len(bus), start + len(x))
    if hi > lo:
        bus[lo:hi] += x[lo - start: hi - start]


def tape_stop(source, src_start, length):
    n = int(length * SR)
    t = np.arange(n) / SR
    rate = (1 - t / length) ** 1.7
    position = src_start * SR + np.concatenate([[0.0], np.cumsum(rate)[:-1]])
    index = np.floor(position).astype(int)
    frac = (position - index)[:, None]
    out = source[index] * (1 - frac) + source[index + 1] * frac
    return out * np.linspace(1.0, 0.0, n, dtype=np.float32)[:, None] ** 0.4


def reverb_tail(chunk, seconds=2.4):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    sos = signal.butter(2, 5000, "low", fs=SR, output="sos")
    ir = np.stack([signal.sosfilt(sos, rng.standard_normal(n)) * np.exp(-t / (seconds / 6.9)) for _ in range(2)], axis=1)
    wet = np.stack([signal.fftconvolve(chunk[:, c], ir[:, c]) for c in range(2)], axis=1)
    return (wet / (np.abs(wet).max() + 1e-9)).astype(np.float32)


def lowpass_dip(bus, start, full, release, end, cutoff=520):
    sos = signal.butter(4, cutoff, "low", fs=SR, output="sos")
    i0, i3 = int(start * SR), int(end * SR)
    wet = signal.sosfiltfilt(sos, bus[i0:i3], axis=0).astype(np.float32)
    amount = np.zeros(i3 - i0, np.float32)
    a, b = int((full - start) * SR), int((release - start) * SR)
    amount[:a] = np.linspace(0, 1, a)
    amount[a:b] = 1
    amount[b:] = np.linspace(1, 0, i3 - i0 - b)
    bus[i0:i3] = bus[i0:i3] * (1 - amount[:, None]) + wet * amount[:, None]


def segment(bus, source, at, src, length, fade_in=0.0, fade_out=0.0):
    chunk = source[int(src * SR): int(src * SR) + int(length * SR)].copy()
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    if fi:
        chunk[:fi] *= np.sin(np.linspace(0, np.pi / 2, fi))[:, None]
    if fo:
        chunk[-fo:] *= np.cos(np.linspace(0, np.pi / 2, fo))[:, None]
    i0 = int(at * SR)
    bus[i0:i0 + len(chunk)] += chunk[: len(bus) - i0]


def onset_near(source, around, window, low_cut=None, high_cut=None):
    i0, i1 = int((around - window) * SR), int((around + window) * SR)
    mono = source[i0:i1].mean(axis=1)
    if high_cut:
        mono = signal.sosfilt(signal.butter(2, high_cut, "low", fs=SR, output="sos"), mono)
    if low_cut:
        mono = signal.sosfilt(signal.butter(2, low_cut, "high", fs=SR, output="sos"), mono)
    smooth = np.convolve(np.abs(mono), np.ones(240) / 240, mode="same")
    flux = np.maximum(0, np.diff(smooth, prepend=smooth[0]))
    return (i0 + int(np.argmax(flux))) / SR


def count_ticks(start, length, end_value, step):
    return [start + (1 - (1 - value / end_value) ** (1 / 3)) * length for value in range(step, end_value + 1, step)]


class Mix:
    def __init__(self, music):
        rms = np.sqrt(np.mean(music[np.abs(music).max(axis=1) > 1e-4] ** 2))
        self.music = (music * (gain(-20) / (rms + 1e-9))).astype(np.float32)
        self.fx = np.zeros_like(self.music)
        self.duck = np.zeros_like(self.music)
        self.log = []

    def cue(self, sample, at, role, anchor=0.0, trim=None, pitch=0.0, fade_out=0.0, pan=0.0, adjust=0.0, duck=False, measure_at=None):
        x = sample
        if trim:
            x = x[int(trim[0] * SR): int(trim[1] * SR)]
        x = pitched(x, pitch)
        if fade_out:
            n = min(len(x), int(fade_out * SR))
            x = x.copy()
            x[-n:] *= np.linspace(1, 0, n)[:, None]
        point = anchor if measure_at is None else measure_at
        before, after = (0.25, 0.15) if role == "whoosh" else (0.0, 0.12)
        own = level(x[int(max(0.0, point - before) * SR): int((point + after) * SR)])
        when = at - anchor + point
        local = level(self.music[int(max(0.0, when - before) * SR): int((when + after) * SR)])
        db = float(np.clip(min(max(local, -28.0), -16.0) + ROLES[role] + adjust - own, -45.0, 8.0))
        db = min(db, PEAK_LIMITS[role] - 20 * np.log10(np.abs(x).max() + 1e-12))
        place(self.fx, x, at, db, anchor=anchor, pan=pan)
        if duck:
            place(self.duck, x, at, db, anchor=anchor)
        self.log.append((round(at, 3), role, round(db, 1)))


def build_a():
    track = load(os.path.join(ASSETS, "music", "173.mp3"))
    beat = 0.51084
    first = 0.139
    logo = 27.1
    ending_offset = first + 188 * beat - logo
    main_offset = ending_offset - 132 * beat
    start = first + 3 * beat - main_offset
    splice = first + 48 * beat - main_offset
    music = np.zeros((int(DURATION * SR), 2), np.float32)
    segment(music, track, start, first + 3 * beat, splice + 0.015 - start, fade_in=0.004, fade_out=0.03)
    segment(music, track, splice - 0.015, splice - 0.015 + ending_offset, DURATION - splice, fade_in=0.03, fade_out=0.8)
    lowpass_dip(music, 7.95, 8.2, 8.62, 8.86)
    mix = Mix(music)
    cue = mix.cue

    cue(sfx("1464"), 0.0, "soft")
    notes = ["G#4", "B4", "C#5", "D#5", "F#5", "G#5", "B5"]
    steps = [0.06, 1.2, 2.25, 3.3, 4.35, 5.4, 6.32]
    for index, (note, at) in enumerate(zip(notes, steps)):
        cue(pluck(NOTES[note]), at, "ui", pan=-0.15 + index * 0.05)
        cue(sfx("1109"), at, "tick", adjust=-4)
    for at, name, anchor in [(8.1, "1489", 0.72), (11.25, "168", 0.313), (16.35, "1489", 0.72), (21.25, "168", 0.313), (25.5, "1489", 0.72)]:
        cue(sfx(name), at, "whoosh", anchor=anchor)
    cue(sfx("3005"), 8.1, "ui", adjust=-2)
    cue(sfx("772"), 8.85, "accent", anchor=0.505, adjust=-3)
    cue(sub_boom(), 8.85, "accent", adjust=-2, duck=True)
    for at in count_ticks(11.5, 1.2, 60, 3):
        cue(pluck(NOTES["D#6"], decay=0.025, length=0.12), at, "tick")
    cue(pluck(NOTES["G#5"]), 12.7, "ui")
    cue(sfx("3005"), 16.45, "ui", adjust=-2)
    cue(sfx("2569"), 16.72, "ui")
    for at, shift in [(16.95, 1.0), (18.12, 1.12)]:
        cue(bubble(520 * shift, 1180 * shift), at, "msg", duck=True)
    cue(sfx("1393"), 17.45, "soft", trim=(0.10, 0.70), fade_out=0.08, adjust=4)
    cue(sfx("1464"), 18.22, "soft", adjust=2)
    cue(sfx("3005"), 18.7, "ui", adjust=-3)
    cue(glide(1.0, 520, 1040), 19.0, "soft", measure_at=0.85)
    cue(sfx("1714"), 19.85, "whoosh", anchor=0.6, trim=(0.0, 2.2), fade_out=0.5, adjust=2)
    cue(sfx("2867"), 19.95, "msg", duck=True)
    for at, note in [(21.4, "B5"), (21.55, "D#6"), (21.65, "F#6"), (21.8, "G#6")]:
        cue(sfx("3005"), at, "ui", adjust=-3)
        cue(pluck(NOTES[note], decay=0.07, length=0.3), at, "tick")
    for at in [22.45, 22.75]:
        cue(sfx("2585"), at, "msg")
    for index, at in enumerate([23.05, 23.17, 23.29]):
        cue(sfx("3005"), at, "ui", pitch=index * 2, adjust=-3)
    cue(sfx("2357"), 23.85, "msg", duck=True)
    cue(sfx("3005"), 26.35, "accent", pitch=-2, adjust=-2)
    cue(sfx("3062"), 26.35, "soft", trim=(0.0, 1.4), fade_out=0.4, adjust=2)
    cue(sfx("2655"), logo, "accent", anchor=0.192, adjust=4)
    cue(sub_boom(), logo, "accent", adjust=2)
    cue(sfx("2352"), logo + 0.05, "soft", trim=(0.9, 3.0), fade_out=1.0)
    return mix, {"music_in": start, "splice": splice, "music_stop": logo}


def build_b():
    track = load(os.path.join(ASSETS, "music", "474.mp3"))
    hit_wall = 12.35
    music = np.zeros((int(DURATION * SR), 2), np.float32)
    segment(music, track, 0.0, 0.0, hit_wall, fade_in=0.004)
    stopped = tape_stop(track, hit_wall, 0.48)
    music[int(hit_wall * SR): int(hit_wall * SR) + len(stopped)] += stopped
    drop_src = onset_near(track, 63.47, 0.12, high_cut=150)
    offset = drop_src - 15.05
    end_src = onset_near(track, 26.958 + offset, 0.2, high_cut=150)
    end_at = end_src - offset
    segment(music, track, 13.40, 13.40 + offset, end_at + 0.2 - 13.40, fade_in=0.3, fade_out=0.06)
    tail = reverb_tail(track[int((end_src - 0.05) * SR): int((end_src + 0.2) * SR)]) * gain(-9)
    i0 = int((end_at + 0.12) * SR)
    music[i0:i0 + len(tail)] += tail[: len(music) - i0]
    mix = Mix(music)
    cue = mix.cue

    cue(sfx("1464"), 0.0, "soft")
    cue(pluck(NOTES["G#4"]), 0.75, "ui", pan=-0.2)
    cue(pluck(NOTES["D#5"]), 0.87, "ui", pan=0.2)
    cue(sfx("2625"), 3.15, "whoosh", anchor=0.488)
    for index, note in enumerate(["G#4", "B4", "C#5", "D#5", "F#5", "G#5"]):
        cue(pluck(NOTES[note], decay=0.09), 3.0 + index * 0.18, "ui", pan=-0.5 + index * 0.2, adjust=-1)
    cue(sfx("2352"), 2.95, "soft", trim=(0.8, 2.3), fade_out=0.5)
    cue(sfx("3005"), 3.2, "ui", adjust=-3)
    cue(sfx("2625"), 6.0, "whoosh", anchor=0.488, pitch=-2, adjust=-2)
    for at in [6.508, 8.117, 9.583, 16.158, 16.817, 18.358]:
        cue(sfx("168"), at + 0.25, "whoosh", anchor=0.313, adjust=-5)
        cue(sfx("3005"), at + 0.05, "ui", adjust=-3)
    for at, note in zip([7.217, 8.767, 10.317, 15.917, 17.517, 19.158], ["G#5", "B5", "C#6", "D#6", "F#6", "G#6"]):
        cue(bell(NOTES[note]), at, "bell")
        cue(sfx("1120"), at, "tick", adjust=-3)
    cue(sfx("2569"), 10.908, "ui", adjust=1)
    cue(sfx("1464"), 11.62, "soft", adjust=2)
    cue(sfx("2182"), hit_wall, "accent", anchor=0.07, adjust=2)
    cue(sfx("2070"), hit_wall, "accent", anchor=0.046, adjust=-2)
    cue(sub_boom(), hit_wall, "accent", adjust=-3)
    cue(pluck(NOTES["G#3"], decay=0.18, length=0.9), 12.958, "ui")
    cue(sfx("3005"), 13.40, "ui")
    cue(sfx("790"), 15.05, "whoosh", anchor=2.49 - 0.86, trim=(0.86, 2.58), adjust=-4)
    cue(bubble(), 14.383, "msg", duck=True)
    cue(sfx("2182"), 14.95, "accent", anchor=0.07, adjust=1)
    cue(sfx("2655"), 15.05, "drop", anchor=0.192)
    cue(sfx("3141"), 15.07, "accent", anchor=0.07, adjust=-2)
    cue(sub_boom(), 15.05, "accent", adjust=-4)
    cue(sfx("2867"), 15.358, "msg", duck=True)
    for at in [16.758, 17.817]:
        cue(sfx("1120"), at, "ui", adjust=-1)
        cue(pluck(NOTES["B5"], decay=0.08, length=0.4), at, "tick")
    for at in [19.208, 19.558]:
        cue(sfx("2585"), at, "msg")
    for index, at in enumerate([19.558, 19.808, 20.058, 20.308, 20.558]):
        cue(sfx("3005"), at, "ui", pitch=index * 2, adjust=-2)
    cue(sfx("1993"), 19.6, "soft", fade_out=0.3, adjust=2)
    cue(sfx("1464"), 20.208, "soft", adjust=3)
    cue(sfx("3005"), 21.408, "accent", pitch=-5, adjust=-2)
    cue(sfx("3062"), 21.45, "soft", trim=(0.0, 1.6), fade_out=0.5, adjust=3)
    cue(sfx("2352"), 21.5, "soft", trim=(0.9, 3.9), fade_out=1.0)
    cue(sfx("2625"), 23.0, "whoosh", anchor=0.488)
    cue(pluck(NOTES["G#3"], decay=0.2, length=0.9), 23.708, "ui", adjust=1)
    cue(sfx("3005"), 23.708, "ui", adjust=-4)
    cue(bell(NOTES["G#5"]), 24.008, "bell", adjust=1)
    cue(sfx("3005"), 24.008, "ui", adjust=-4)
    cue(sfx("1489"), 25.75, "whoosh", anchor=0.72, adjust=-2)
    cue(sfx("3005"), 26.308, "accent", pitch=-2, adjust=-2)
    cue(sfx("3062"), 26.308, "soft", trim=(0.0, 1.4), fade_out=0.4, adjust=2)
    cue(sfx("1492"), end_at, "whoosh", anchor=1.103, fade_out=0.1, adjust=-3)
    cue(sfx("2655"), end_at, "accent", anchor=0.192, adjust=4)
    cue(sub_boom(), end_at, "accent", adjust=2)
    return mix, {"wall": hit_wall, "drop": 15.05, "end": end_at}


BUILDERS = {"ad2a": build_a, "ad2b": build_b}


def mixdown(mix):
    env = np.abs(mix.duck).max(axis=1)
    attack, release = np.exp(-1 / (0.005 * SR)), np.exp(-1 / (0.28 * SR))
    smooth = np.zeros_like(env)
    value = 0.0
    for i, sample in enumerate(env):
        coeff = attack if sample > value else release
        value = coeff * value + (1 - coeff) * sample
        smooth[i] = value
    reduction = 1 - 0.32 * np.clip(smooth / (smooth.max() + 1e-9), 0, 1)
    return mix.music * reduction[:, None] + mix.fx


def measure(path):
    text = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    summary = text[text.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1)), float(re.search(r"Peak:\s+([-+]?[\d.]+) dBFS", summary).group(1))


def loudnorm_values(path, true_peak):
    text = subprocess.run([FFMPEG, "-hide_banner", "-i", path, "-af", f"loudnorm=I={LOUDNESS}:TP={true_peak}:LRA=11:print_format=summary", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    labels = [("I", "Input Integrated"), ("TP", "Input True Peak"), ("LRA", "Input LRA"), ("thresh", "Input Threshold"), ("offset", "Target Offset")]
    return {key: float(re.search(rf"{label}:\s+([-+]?[\d.]+)", text).group(1)) for key, label in labels}


def master(source, target, true_peak):
    limited = target + ".limited.wav"
    margin = 0.6
    measured = loudnorm_values(source, true_peak)
    kind = None
    for _ in range(5):
        ceiling = true_peak - (LOUDNESS - measured["I"]) - margin
        chain = f"aresample=192000,alimiter=limit={max(0.0625, min(1.0, gain(ceiling))):.5f}:attack=1:release=60:level=false,aresample={SR}"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", source, "-af", chain, "-c:a", "pcm_f32le", limited], check=True)
        values = loudnorm_values(limited, true_peak)
        chain = f"loudnorm=I={LOUDNESS}:TP={true_peak}:LRA=11:measured_I={values['I']}:measured_TP={values['TP']}:measured_LRA={values['LRA']}:measured_thresh={values['thresh']}:offset={values['offset']}:linear=true:print_format=summary,aresample={SR}"
        text = subprocess.run([FFMPEG, "-hide_banner", "-y", "-i", limited, "-af", chain, "-c:a", "pcm_s24le", target], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        kind = re.search(r"Normalization Type:\s+(\w+)", text).group(1)
        if kind == "Linear":
            break
        measured = values
        margin += 0.5
    os.remove(limited)
    return kind


def write_wav(path, audio):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", path], input=audio.astype(np.float32).tobytes(), check=True)


def qc_image(audio, marks, path, title):
    width, height = 1800, 260
    image = Image.new("RGB", (width, height + 40), (16, 16, 20))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 14)
    peaks = np.abs(audio).max(axis=1)
    per = len(peaks) // width
    for x in range(width):
        h = peaks[x * per:(x + 1) * per].max() * (height - 20)
        draw.line([(x, height / 2 - h / 2), (x, height / 2 + h / 2)], fill=(110, 180, 255))
    for second in range(0, int(DURATION) + 1):
        x = second / DURATION * width
        draw.line([(x, 0), (x, height)], fill=(45, 45, 55))
        draw.text((x + 2, height + 4), str(second), font=font, fill=(170, 170, 170))
    for at, label in marks:
        x = at / DURATION * width
        draw.line([(x, 0), (x, height)], fill=(255, 200, 80))
        draw.text((x + 3, 4), label, font=font, fill=(255, 220, 120))
    draw.text((8, height + 20), title, font=font, fill=(255, 255, 255))
    image.save(path)


def main(plan):
    if plan not in BUILDERS:
        raise SystemExit(f"unknown plan: {plan} (ad2a, ad2b)")
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "qc"), exist_ok=True)
    mix, info = BUILDERS[plan]()
    raw = os.path.join(ROOT, "out", f"{plan}_mix_raw.wav")
    final = os.path.join(ROOT, "out", f"{plan}_mix.wav")
    write_wav(raw, mixdown(mix))
    video = os.path.join(ROOT, "out", f"{plan}_h.mp4")
    output = os.path.join(ROOT, "out", f"{plan}_h_sound.mp4")
    target_peak = TRUE_PEAK
    for _ in range(4):
        kind = master(raw, final, target_peak)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", video, "-i", final, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", str(SR), "-shortest", "-movflags", "+faststart", output], check=True)
        integrated, true_peak = measure(output)
        if true_peak <= -1.0:
            break
        target_peak -= true_peak + 1.3
    marks = [(value, key) for key, value in info.items()]
    qc_image(load(final), marks, os.path.join(ROOT, "qc", f"sound_{plan}.png"), f"{plan}  {integrated} LUFS  true peak {true_peak} dBFS  {kind}")
    print(output, "LUFS", integrated, "TP", true_peak, kind, {key: round(value, 3) for key, value in info.items()})


if __name__ == "__main__":
    for name in sys.argv[1:]:
        main(name)
