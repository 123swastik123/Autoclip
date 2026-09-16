"""QA: separates TECHNICAL checks (container/AV integrity) from CREATIVE checks
(pacing, face coverage, captions, format honesty). Both gates must pass before a
file is presented as ready; neither uploads anything."""
import os, re
from . import mediatools as mt
from .format import build_directives

# ---------------- Technical ----------------
TECH_MIN = {
    "min_height": 1920, "min_width": 1080, "min_fps": 29.9, "max_fps": 30.1,
    "min_duration": 8, "max_duration": 60, "min_audio_channels": 2,
    "sample_rate": 48000,
}

def tech_qa(path, plan=None):
    found = {}
    r = mt.run(["ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,bit_rate",
                "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
                "-of", "json", path], allow_fail=True)
    if r.returncode != 0:
        return {"ok": False, "errors": [f"ffprobe failed: {r.stderr[-300:]}"]}
    import json
    try:
        data = json.loads(r.stdout)
    except Exception as e:
        return {"ok": False, "errors": [f"bad probe json: {e}"]}
    fmt = data["format"]
    dur = float(fmt.get("duration", 0) or 0)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    fps = float(v["r_frame_rate"].split("/")[0]) / float(v["r_frame_rate"].split("/")[1]) if v and v.get("r_frame_rate", "0/1") != "0/1" else 0
    found["duration"] = round(dur, 2)
    found["size_mb"] = round(float(fmt.get("size", 0)) / 1e6, 1)
    found["video"] = (v or {}).get("codec_name"), (v or {}).get("width"), (v or {}).get("height"), round(fps, 2)
    found["audio"] = (a or {}).get("codec_name"), (a or {}).get("channels"), (a or {}).get("sample_rate")
    errors = []
    errors.append(f"container read error" if not v or not a else None)
    if v:
        if v["codec_name"] not in ("h264", "av1", "vp9"):
            errors.append(f"video codec {v['codec_name']} may not be Short-safe")
        if int(v["width"]) < TECH_MIN["min_width"] or int(v["height"]) < TECH_MIN["min_height"]:
            errors.append("vertical resolution below 1080x1920")
    if fps and not (TECH_MIN["min_fps"] <= fps <= TECH_MIN["max_fps"]):
        errors.append(f"fps {fps} off target 30")
    if not (TECH_MIN["min_duration"] <= dur <= TECH_MIN["max_duration"]):
        errors.append(f"duration {dur:.1f}s outside Short ideal")
    if a:
        if a["codec_name"] not in ("aac", "opus", "mp3"):
            errors.append(f"audio codec {a['codec_name']}")
        if int(a["channels"]) < TECH_MIN["min_audio_channels"]:
            errors.append("expected stereo audio")
        if int(a["sample_rate"]) != TECH_MIN["sample_rate"]:
            errors.append("expected 48kHz audio")
    errors = [e for e in errors if e]
    try:  # loudness spot check
        rl = mt.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                     "ebur128=peak=true", "-f", "null", "NUL"], allow_fail=True)
        ms = re.findall(r"I:\s*(-?[0-9.]+).+?Tpeak:\s*(-?[0-9.]+)", rl.stderr)
        if ms:
            lobe, peak = float(ms[0][0]), float(ms[0][1])
            found["loudness"] = {"integrated": round(lobe, 1), "true_peak": round(peak, 2)}
            if not (-17 <= lobe <= -11):
                errors.append(f"integrated loudness {lobe} off -14 target")
            if peak > -1.0:
                errors.append(f"true peak {peak} > -1 dbTP")
    except Exception as e:
        errors.append(f"loudness check failed: {e}")
    return {"ok": not errors, "errors": errors, "found": found}

# ---------------- Creative ----------------
CREATIVE_MIN = {"face_hits": 0.30, "min_words": 8, "max_pause_inside": 2.4}

def creative_qa(each_clip, builder=None):
    """each_clip: list of {id, dur, face_hits, words, subscores, phrase_pauses}.
    Checks pacing, face coverage, caption density, silence holes, format logic."""
    issues, notes = [], []
    if not each_clip:
        issues.append("no clips to QA")
        return {"ok": False, "issues": issues, "notes": notes}

    total = sum(c["dur"] for c in each_clip)
    if not (12 <= total <= 45):
        issues.append(f"total runtime {total:.1f}s outside 12-45s band")

    speak_ratio = sum(min(1.0, c["words"] / max(6, c["dur"] * 3)) for c in each_clip) / len(each_clip)
    if speak_ratio < 0.55:
        issues.append(f"low speech density ({speak_ratio:.0%}) - likely long silent gaps")

    for c in each_clip:
        if c.get("face_hits", 0) < CREATIVE_MIN["face_hits"]:
            issues.append(f"{c['id']}: face visible only {c['face_hits']:.0%} - creator may be off-frame")
        if c.get("max_pause", 0) > CREATIVE_MIN["max_pause_inside"]:
            issues.append(f"{c['id']}: dead gap {c['max_pause']:.1f}s inside clip")
        if c.get("words", 0) < CREATIVE_MIN["min_words"]:
            notes.append(f"{c['id']}: very few words, may not land caption-forward")

    scores = [c for c in each_clip if isinstance(c.get("subscores"), dict)
              and "score" in c["subscores"]]
    if len(scores) >= 2:
        srt = sorted(c["subscores"]["score"] for c in scores)
    else:
        srt = []
    if len(srt) >= 2 and abs(srt[0] - srt[-1]) < 0.05:
        notes.append("scores unusually flat; manual re-rank may be needed")
    if sum(c["subscores"]["creator_focus"] for c in each_clip) / len(each_clip) < 0.35:
        notes.append("average creator-focus low; double-check framing in preview")

    return {"ok": not issues, "issues": issues, "notes": notes,
            "metrics": {"total": round(total, 1), "speech_density": round(speak_ratio, 2)}}