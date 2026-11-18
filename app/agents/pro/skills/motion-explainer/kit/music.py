# Synthesizes a soft ambient music bed + whooshes, mixes with voice clips per timing.json -> out/audio.wav
import json, numpy as np, soundfile as sf, subprocess, os
from scipy.signal import butter, sosfilt

SR = 48000
H = os.path.dirname(os.path.abspath(__file__))
T = json.load(open(os.path.join(H, "src/timing.json"), encoding="utf-8"))
N = int(T["total"] * SR)
rng = np.random.default_rng(7)

def lp(x, f, o=2): return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)
def bp(x, lo, hi): return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)
def midi(m): return 440 * 2 ** ((m - 69) / 12)

bpm = 96; beat = 60 / bpm; bar = 4 * beat
# Am - F - C - G (voicings)
chords = [[57, 60, 64, 69], [53, 57, 60, 65], [55, 60, 64, 67], [55, 59, 62, 67]]
roots = [45, 41, 48, 43]
music = np.zeros(N)
t_all = np.arange(N) / SR

# pad
nb = int(np.ceil(T["total"] / bar)) + 1
for b in range(nb):
    s0 = int(b * bar * SR); L = int(bar * 1.15 * SR)
    if s0 >= N: break
    L = min(L, N - s0); t = np.arange(L) / SR
    env = np.minimum(1, t / 0.6) * np.minimum(1, (bar * 1.15 - t) / 0.5)
    sig = np.zeros(L)
    for m in chords[b % 4]:
        f = midi(m)
        for d in (-0.08, 0.08):
            ph = 2 * np.pi * f * (1 + d / 100) * t
            sig += 0.5 * np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
    music[s0:s0 + L] += sig * env * 0.035
    # sub bass
    f = midi(roots[b % 4] - 12)
    bl = np.minimum(1, t / 0.05) * np.exp(-t * 0.6)
    music[s0:s0 + L] += np.sin(2 * np.pi * f * t) * bl * 0.10
# plucks (8ths arpeggio)
eighth = beat / 2
k = 0
pat = [0, 2, 1, 3, 2, 1, 3, 2]
while k * eighth < T["total"]:
    b = int(k * eighth / bar)
    m = chords[b % 4][pat[k % 8]] + 12
    s0 = int(k * eighth * SR); L = min(int(0.6 * SR), N - s0)
    t = np.arange(L) / SR
    f = midi(m)
    note = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 7) * np.minimum(1, t / 0.004)
    music[s0:s0 + L] += note * (0.030 if k % 2 == 0 else 0.020)
    k += 1
# soft hat/shaker on offbeats
noise = rng.standard_normal(N)
shaker = hp(noise, 7000)
hat = np.zeros(N)
k = 0
while k * eighth < T["total"]:
    if k % 2 == 1:
        s0 = int(k * eighth * SR); L = min(int(0.08 * SR), N - s0)
        hat[s0:s0 + L] += shaker[s0:s0 + L] * np.exp(-np.arange(L) / SR * 60)
    k += 1
music += hat * 0.012
# fades
music *= np.minimum(1, t_all / 1.0) * np.minimum(1, (T["total"] - t_all) / 2.0)
music = lp(music, 9000)

# whooshes at scene changes
sfx = np.zeros(N)
for s in T["scenes"][1:]:
    c = int((s["start"] - 0.05) * SR); L = int(0.55 * SR)
    a = max(0, c - int(0.35 * SR)); seg = rng.standard_normal(L)
    tt = np.arange(L) / L
    env = np.sin(np.pi * tt) ** 2
    lo = 300 + 2500 * tt
    w = bp(seg, 400, 3500) * env
    e = min(N, a + L)
    sfx[a:e] += w[: e - a] * 0.05

# voice
voice = np.zeros((N, 2))
for s in T["scenes"]:
    p = os.path.join(H, "public/voice/proc", s["id"] + ".wav")
    if not os.path.exists(p): continue
    v, sr = sf.read(p)
    assert sr == SR
    if v.ndim == 1: v = np.stack([v, v], 1)
    s0 = int(s["start"] * SR); e = min(N, s0 + len(v))
    voice[s0:e] += v[: e - s0]

# ducking: music lower under voice
venv = np.abs(voice).mean(1)
venv = lp(venv, 4)
duck = 1 - 0.45 * np.clip(venv / (venv.max() * 0.25 + 1e-9), 0, 1)
bed = (music * 0.5 + sfx * 0.8) * duck
mix = voice * 1.0 + np.stack([bed, bed], 1)
peak = np.abs(mix).max()
mix = mix / peak * 0.89
sf.write(os.path.join(H, "out/audio_raw.wav"), mix, SR)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(H, "out/audio_raw.wav"), "-af", "loudnorm=I=-14:TP=-1.0:LRA=9", "-ar", "48000", os.path.join(H, "out/audio.wav")], check=True)
print("ok", T["total"])
