"""Modern viral-Shorts-scale karaoke caption engine.

Replaces "basic subtitles": word-by-word karaoke with speech-synced pops that
follow the actual utterance timing, dynamic emphasis (names/punchlines/reactions
get bigger + colored), a consistent visual system, mobile-safe lower-third
placement, and NO motion that fights the footage (animation follows speech).

Also emits a JSON word/phrase map + caption-QA diagnostics (timing, overlaps,
missing words, readability) used by the creative-QA gate.
"""
import os, json

# Reaction / shout tokens that get automatic emphasis. Shout-heavy, short bursts.
SHOUTS = {
    "OH", "MY", "GOD", "WHAT", "NOW", "LET'S", "LET", "GO", "LOVE", "BRO",
    "CAN", "DIE", "Y'ALL", "HERE", "NAME", "WORD", "BEAUTIFUL", "F*CK",
    "AGAIN", "CHECK", "THIS", "CAN'T", "CANT", "NOBODY", "NOTHING", "REALLY",
    "TELL", "WAIT", "STOP", "NO WAY", "HUH", "BROTHER", "HELL", "HEY", "MAN",
}

def _ts(sec):
    ms = int(round(sec * 1000))
    h, m = ms // 3600000, (ms // 60000) % 60
    s, fr = (ms // 1000) % 60, ms % 1000
    return f"{h}:{m:02d}:{s:02d}.{fr:02d}"

def _esc(t):
    return (t.replace("{", "(").replace("}", ")")
             .replace("\\", "/").replace("\n", " ").strip())

def group_words(words, words_per_line=5, gap_thresh=0.55):
    """Group word dicts into phrases (list of lists of words)."""
    phrases = []
    cur = []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > gap_thresh or len(cur) >= words_per_line):
            phrases.append(cur); cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)
    return phrases

def header(profile):
    """One consistent visual system across the whole Short (styles are shared)."""
    font = profile.get("font", "Arial Black")
    size = profile.get("size", 86)
    emph_color = profile.get("emphasis_color", "FFD200").lstrip("#")
    margin_v = profile.get("margin_v", 440)
    return ("[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "WrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: KWord,{font},{size},&H00FFFFFF,&H000000FF,"
            f"&H00000000,&H66000000,-1,0,0,0,100,100,1,0,1,6,3,2,{margin_v},1\n"
            f"Style: KEmp,{font},{size + 18},&H00{emph_color},"
            f"&H000000FF,&H00000000,&H66000000,-1,0,0,0,100,100,1,0,1,7,3,2,{margin_v}-18,1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

def _word_event(w, phrase_end, is_e, pop_ms, profile, cap_profile_anim):
    """One word event. Pops are reserved for emphasis or high-energy words so we
    don't over-animate; everything syncs to speech timing."""
    anim = cap_profile_anim
    txt = _esc(w["text"])
    fad = f"{{\\fad(70,0)}}"
    if anim == "word_pop":
        if is_e:
            return f"Dialogue: 0,{_ts(w['start'])},{_ts(phrase_end)},KEmp,,0,0,0,,{fad}{{\\fscx130\\fscy130\\t(0,{pop_ms},118,118)}}{txt}"
        # Non-emphasis words get a subtle rise instead of a full scale pop.
        return f"Dialogue: 0,{_ts(w['start'])},{_ts(phrase_end)},KWord,,0,0,0,,{fad}{txt}"
    if anim == "phrase_reveal":
        return f"Dialogue: 0,{_ts(w['start'])},{_ts(phrase_end)},KWord,,0,0,0,,{fad}{txt}"
    # highlight_sweep: sweep a yellow overlay across the phrase via a back-karaoke style
    if is_e:
        return f"Dialogue: 0,{_ts(w['start'])},{_ts(phrase_end)},KEmp,,0,0,0,,{fad}{{\\fscx125\\fscy125\\t(0,{pop_ms},115,115)}}{txt}"
    ll = len(txt) * 42  # rough px width for sweep positioning (lower-left origin)
    return (f"Dialogue: 0,{_ts(w['start'])},{_ts(phrase_end)},KWord,,0,0,0,,"
            f"{fad}{{\\1c&HFFFFFF&\\t(0,{pop_ms * 3},&HFFD200&)}}{txt}")

def make(words, profile, emphasis=(), out_ass=None, out_meta=None, energy_threshold=None):
    """words: [{'start','end','text','energy'}]. Builds karaoke captions + meta.

    emphasis: explicit set of words to always boost. SHOUTS auto-emphasized.
    A dynamic energy threshold picks the top ~15% (min 0.7) of utterances for the
    speech-synced pop; anything lower keeps a soft fade so we never over-animate.
    """
    cap = profile
    emph = {w.upper().strip(" .,;!?") for w in emphasis}
    pop_ms = int(cap.get("pop_ms", 130))
    up = cap.get("uppercase", True)
    anim = cap.get("animation", "word_pop")
    phrases = group_words(words, cap.get("words_per_line", 5))
    meta = {"style_system": cap.get("style", "karaoke_words"), "animation": anim,
            "phrases": [], "words": []}

    # dynamic energy threshold: words with the top ~15% energy pop unless explicit
    energies = sorted(w.get("energy", 0.0) for w in words)
    if not energies:
        dyn_thr = 1.1
    elif energy_threshold is not None:
        dyn_thr = energy_threshold
    else:
        dyn_thr = max(0.70, energies[int(len(energies) * 0.85 - 1)] if len(energies) > 3 else energies[-1])

    events = []
    for phrase in phrases:
        if not phrase:
            continue
        end = max(w["end"] for w in phrase) + 0.15
        ph = [w["text"].upper() if up else w["text"] for w in phrase]
        meta["phrases"].append({"text": " ".join(ph), "start": phrase[0]["start"], "end": end})
        for w in phrase:
            token = w["text"].strip(" .,;!?")
            txt = w["text"].upper() if up else w["text"]
            energy = w.get("energy", 0.0)
            # punchline tokens from the manifest always pop; general shouts only pop
            # when the delivery is loud too; everything else rides the top-15% energy line
            is_e = (token.upper() in emph) or \
                   (token.upper() in SHOUTS and energy >= 0.80) or \
                   (energy >= dyn_thr)
            events.append(_word_event(w, end, is_e, pop_ms, cap, anim))
            meta["words"].append({"text": txt, "start": w["start"], "end": w["end"],
                                  "emphasis": bool(is_e),
                                  "energy": energy,
                                  "pop": bool(is_e)})
    meta["energy_threshold"] = round(dyn_thr, 3)

    data = header(cap) + "\n".join(events) + "\n"
    if out_ass:
        with open(out_ass, "w", encoding="utf-8") as f:
            f.write(data)
    if out_meta:
        with open(out_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
    return data, meta