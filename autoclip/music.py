"""Background music synthesis - 100% copyright-safe, mood-appropriate.

Viral-track research says: comedy = subtle, must NOT overpower dialogue; the bed
should support the edit. Since a trending copyrighted sound is high-risk, we
synthesize a royalty-free bed matching the researched style (lofi/ambient/etc).

Structure per style:
- pad: soft chord progression, detuned, slow tremolo -> lofi/ambient feel
- bass/thump: gentle kick for rhythm-driven styles (lofi/hiphop/phonk)
- hats: filtered noise ticks for phonk (sparse) 
Everything is generated once and cached in the media dir.
"""
import os, json, wave, struct, math
import numpy as np
from .config import media_dir

SR = 44100

STYLES = {
    "lofi_hiphop": {"bpm": 76, "chords": [[261.63, 329.63, 392.00, 493.88],   # Cmaj7-ish
                                          [220.00, 261.63, 329.63, 392.00],    # Am7-ish
                                          [174.61, 220.00, 261.63, 329.63],    # Fmaj7-ish
                                          [196.00, 246.94, 293.66, 392.00]],   # Gmaj-ish
                    "pad": "detuned", "kick": True, "hat": False,
                    "bass_root": [130.81, 110.00, 87.31, 98.00]},
    "phonk": {"bpm": 128, "chords": [[110.00, 164.81, 220.00, 329.63],   # low raw
                                     [98.00, 146.83, 196.00, 293.66]],
              "pad": "minor", "kick": True, "hat": True,
              "bass_root": [55.0, 49.0]},
    "synthwave": {"bpm": 100, "chords": [[130.81, 196.00, 261.63, 329.63],
                                         [116.54, 174.61, 233.08, 293.66]],
                  "pad": "bright", "kick": True, "hat": False,
                  "bass_root": [65.41, 58.27]},
    "ambient": {"bpm": 60, "chords": [[220.00, 329.63, 440.00, 554.37],
                                      [196.00, 293.66, 392.00, 493.88]],
                "pad": "detuned", "kick": False, "hat": False,
                "bass_root": [110.0, 98.0]},
}

def _tone(freq, dur, sr=SR, kind="sine"):
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    if kind == "detuned":
        return (np.sin(2*np.pi*freq*t) + 0.6*np.sin(2*np.pi*freq*1.002*t) * 0.6) * 0.5
    if kind == "bright":
        return np.sin(2*np.pi*freq*t) + 0.35*np.sin(2*np.pi*freq*2*t)
    if kind == "minor":
        return np.sin(2*np.pi*freq*t) * 0.7
    return np.sin(2*np.pi*freq*t)

def _env_attack_release(n, a=0.35, r=0.45):
    env = np.ones(n)
    ai = int(n * a); ri = int(n * r)
    env[:ai] = np.linspace(0, 1, ai)
    env[ri:] *= np.linspace(1, 0, n - ri)
    return env

def make_bgm(profile=None, out_path=None):
    """Render BGM to a wav. profile: music_trend from research builder."""
    profile = profile or {}
    style_name = profile.get("style", "lofi_hiphop")
    style = STYLES.get(style_name, STYLES["lofi_hiphop"])
    out_path = out_path or os.path.join(media_dir(), f"bgm_{style_name}.wav")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path

    bpm = style["bpm"]
    beats_per_bar = 4
    bar_sec = 4 * 60.0 / bpm
    total_bar = max(8, int((70.0 / bar_sec) + 1))   # cover a 60s Short with tail
    dur_total = bar_sec * total_bar
    n = int(dur_total * SR)
    mix = np.zeros((2, n))

    pad_amp = 0.16
    trem = 0.45 + 0.12 * np.sin(2 * np.pi * 0.5 * np.linspace(0, dur_total, n))
    for bar in range(total_bar):
        chord = style["chords"][bar % len(style["chords"])]
        s0 = int(bar * bar_sec * SR)
        for freq in chord:
            tone = _tone(freq, bar_sec * 1.15 + 0.5, kind="detuned")
            m = min(len(tone), n - s0)
            if m <= 0: continue
            seg = tone[:m] * _env_attack_release(m)[:m] * pad_amp
            mix[0, s0:s0+m] += seg
            mix[1, s0:s0+m] += seg
        # bass root pluck
        if bar % 2 == 0 and style.get("bass_root"):
            root = style["bass_root"][bar % len(style["bass_root"])]
            cont = _tone(root, bar_sec * 1.6, kind="sine") 
            m = min(len(cont), n - s0)
            if m > 0:
                seg = cont[:m] * _env_attack_release(m, a=0.05, r=0.5) * 0.22
                mix[0, s0:s0+m] += seg
                mix[1, s0:s0+m] += seg
        # kick
        if style.get("kick"):
            for beat in range(beats_per_bar):
                ts = int((bar * bar_sec + beat * (bar_sec / beats_per_bar)) * SR)
                if ts >= n: break
                kdur = 0.22
                kt = np.linspace(0, kdur, int(kdur * SR), endpoint=False)
                kick = np.sin(2 * np.pi * (130 * np.exp(-kt * 22) + 40) * kt) * np.exp(-kt * 26)
                m = min(len(kick), n - ts)
                mix[0, ts:ts+m] += kick[:m] * 0.42
                mix[1, ts:ts+m] += kick[:m] * 0.42
        # hats (phonk): sparse, offbeat
        if style.get("hat"):
            for beat in range(beats_per_bar * 2):
                ts = int((bar * bar_sec + beat * (bar_sec / (beats_per_bar * 2)) + bar_sec * 0.10) * SR)
                if ts >= n: break
                hdur = 0.05
                ht = np.linspace(0, hdur, int(hdur * SR), endpoint=False)
                hat = np.random.randn(len(ht)) * np.exp(-ht * 120)
                m = min(len(hat), n - ts)
                mix[0, ts:ts+m] += hat[:m] * 0.10
                mix[1, ts:ts+m] += hat[:m] * 0.10

    # simple one-pole lowpass to soften hats/pad brightness
    alpha = 0.25
    mix_l, mix_r = np.zeros(n), np.zeros(n)
    acc_l = acc_r = 0.0
    for i in range(n):
        acc_l = acc_l + alpha * (mix[0, i] - acc_l)
        acc_r = acc_r + alpha * (mix[1, i] - acc_r)
        mix_l[i], mix_r[i] = acc_l, acc_r
    mix = np.stack([mix_l, mix_r])

    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.30
    trem = np.stack([trem, trem])
    mix = mix * trem

    # fade in/out
    fi = int(0.3 * SR); fo = int(0.6 * SR)
    mix[:, :fi] *= np.linspace(0, 1, fi)
    mix[:, -fo:] *= np.linspace(1, 0, fo)

    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.T.tobytes())
    return out_path