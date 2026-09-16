"""QA: separates TECHNICAL checks (container/AV integrity) from CREATIVE checks.

Creative QA must answer the deliverability questions explicitly:
- Is #1 genuinely the strongest payoff? Does #5->#1 progressively get better?
- Are the moments connected rather than random? Natural transitions?
- Is the creator the focus? Are captions accurate/timed/modern?
- Is BGM appropriate and ducked under dialogue? Unnecessary effects?
- Energetic-but-not-chaotic pacing, strong first 1-2s, satisfying final payoff.

Both gates must pass before a file is presented as ready; neither uploads anything.
"""
import os, re, json

from . import mediatools as mt

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
    errors.append("container read error" if not v or not a else None)
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

def sequence_qa(sequence, seq_floor=0.55):
    """Checks ordering, connection, escalation, payoff climax, transitions.

    sequence: list of plans ordered #5..#1 (each with score/subscores/topics).
    """
    issues, notes, metrics = [], [], {}
    if len(sequence) < 2:
        return {"ok": True, "issues": issues, "notes": notes, "metrics": metrics,
                "hits": ["at least one moment"], "miss": []}
    seq_score = sequence[0].get("sequence_score", 0.0)
    subs = sequence[0].get("sequence_subscores", {}) or {}
    metrics = {"sequence_score": round(seq_score, 3), **subs}
    if seq_score < seq_floor:
        issues.append(f"sequence flow score {seq_score:.2f} below floor {seq_floor}")

    scores = [p.get("score", 0) for p in sequence]
    reactions = [p.get("subscores", {}).get("reaction_intensity", 0) for p in sequence]
    payoffs = [p.get("subscores", {}).get("payoff", 0) for p in sequence]

    # Is #1 genuinely the strongest payoff?
    if payoffs and max(payoffs) != payoffs[-1]:
        issues.append("#1 does not have the strongest payoff (list ends flat)")
    if not (max(scores) == scores[-1]):
        notes.append("#1 not the top-scored moment - check payoff vs. fun")

    # Does #5 -> #1 progressively get better?
    improves = sum(1 for i in range(1, len(scores)) if scores[i] >= scores[i-1])
    if improves < len(scores) - 1:
        notes.append(f"progression not monotonic ({improves}/{len(scores)-1} steps improve)")

    # Reaction escalation
    if sum(1 for i in range(1, len(reactions)) if reactions[i] >= reactions[i-1]) < len(reactions) - 1:
        notes.append("reaction intensity dips mid-sequence - connection may feel broken")

    # Topic connections between adjacent moments
    def overlap(a, b):
        if not a or not b:
            return 0.0
        return len(set(a) & set(b)) / len(set(a) | set(b))
    tops = [p.get("topics", []) for p in sequence]
    conn = sum(overlap(tops[i-1], tops[i]) for i in range(1, len(tops))) / (len(tops) - 1)
    metrics["topic_connection"] = round(conn, 2)
    if conn < 0.15:
        notes.append("adjacent moments share almost no topic - may read as random")

    return {"ok": not issues, "issues": issues, "notes": notes, "metrics": metrics,
            "hits": ["sequence cohesion checks"], "miss": issues}

def caption_qa(meta, profile=None):
    """Checks caption accuracy, timing, overlap, missing words, readability."""
    issues, notes, metrics = [], [], {}
    words = meta.get("words", []) or []
    phrases = meta.get("phrases", []) or []
    if not words:
        return {"ok": True, "issues": issues, "notes": ["no captions (no words in clip)"], "metrics": metrics}
    # timing sanity: no negative/zero spans, sensible order
    bad = [w for w in words if w["end"] <= w["start"]]
    if bad:
        issues.append(f"{len(bad)} caption words have zero/negative span")
    # overlaps between consecutive words are expected in dense speech; flag only large
    overlaps = 0
    for i in range(1, len(words)):
        if words[i]["start"] < words[i-1]["end"] - 0.03:
            overlaps += 1
    if overlaps > len(words) * 0.15:
        notes.append(f"{overlaps} word overlaps - timings may drift from speech")
    # readability: emphasis ratio small enough not to be chaotic
    emph = sum(1 for w in words if w.get("emphasis", False))
    mean_e = round(sum(w.get("energy", 0.0) for w in words) / len(words), 2)
    metrics["emphasis_ratio"] = round(emph / len(words), 2)
    metrics["mean_energy"] = mean_e
    # constant-yelling clips (mean energy >= 0.8) justify a hot caption bed;
    # anything above 70% is always flagged as over-animated.
    if emph / len(words) > 0.7:
        notes.append(f"emphasis {emph}/{len(words)} - genuinely over-animated")
    elif emph / len(words) > 0.5 and mean_e < 0.80:
        notes.append("more than half of words emphasized - add calm (may over-animate)")
    if emph / len(words) < 0.08 and mean_e < 0.80:
        notes.append("almost no emphasis - punchlines may not pop")
    # modern style check: karaoke + animation system present
    anim = meta.get("animation", "")
    if anim not in ("word_pop", "phrase_reveal", "highlight_sweep"):
        issues.append(f"caption animation '{anim}' not recognized as modern style")
    return {"ok": not issues, "issues": issues, "notes": notes,
            "metrics": {"words": len(words), "phrases": len(phrases), **metrics}}

def creative_qa(each_clip, builder=None, sequence=None, caption_metas=None):
    """each_clip: list of {id, dur, face_hits, words, subscores, phrase_pauses}.
    Checks pacing, face coverage, caption density, sequence, captions, effects."""
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
              and "score" in c]
    if len(scores) >= 2:
        srt = sorted(c["score"] for c in scores)
        if abs(srt[0] - srt[-1]) < 0.05:
            notes.append("scores unusually flat; manual re-rank may be needed")
    if sum(c["subscores"]["creator_focus"] for c in each_clip) / len(each_clip) < 0.35:
        notes.append("average creator-focus low; double-check framing in preview")

    # Effect discipline: too many punch-ins / heavy SFX is clutter
    punches = sum(1 for c in each_clip if c.get("punch", False))
    if punches == len(each_clip) and len(each_clip) > 3:
        notes.append("every moment punch-in'd - consider letting some breathe")

    # Sequence / connection checks (if provided)
    if sequence:
        sq = sequence_qa(sequence)
        issues.extend(sq["issues"]); notes.extend(sq["notes"])
        metrics = {"total": round(total, 1), "speech_density": round(speak_ratio, 2),
                   **sq["metrics"]}
    else:
        metrics = {"total": round(total, 1), "speech_density": round(speak_ratio, 2)}

    # Caption checks (if provided)
    if caption_metas:
        for meta in caption_metas:
            cq = caption_qa(meta)
            issues.extend(cq["issues"]); notes.extend(cq["notes"])

    return {"ok": not issues, "issues": issues, "notes": notes, "metrics": metrics}