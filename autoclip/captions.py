"""Karaoke-style caption engine (trend-aware).

Word-by-word pop captions: words of a phrase appear sequentially and accumulate,
the currently-spoken word pops in bigger, emphasis words are larger + colored,
positioned center-lower-third with safe margins for mobile.

Run via libass `subtitles=` burn. Also emits a JSON word map for QA.
"""
import os, json

SHOUTS = {
    "OH", "MY", "GOD", "WHAT", "NOW", "LET'S", "LET", "GO", "LOVE", "BRO",
    "CAN", "DIE", "MANCHUNA", "RONALDO", "Y'ALL", "HERE", "SLEPT", "CAMERAS",
    "NAME", "WORD", "BEAUTIFUL", "F*CK", "INDIA", "AGAIN", "CHECK", "THIS",
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
            f"Style: KWord,{profile.get('font','Arial Black')},{profile.get('size',92)},&H00FFFFFF,&H000000FF,"
            f"&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,7,3,2,{profile.get('margin_v',460)},1\n"
            f"Style: KEmp,{profile.get('font','Arial Black')},105,&H00{profile.get('emphasis_color','FFD200')[1:]},"
            f"&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,7,3,2,{profile.get('margin_v',460)-14},1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

def make(words, profile, emphasis=(), out_ass=None, out_meta=None):
    """words: [{'start','end','text','energy'}]. Returns (ass_path, meta)."""
    cap = profile
    emph = {w.upper() for w in emphasis} | {w.upper() for w in SHOUTS if w.upper() in SHOUTS}
    pop_ms = cap.get("pop_ms", 130)
    up = cap.get("uppercase", True)
    phrases = group_words(words, cap.get("words_per_line", 5))
    meta = {"phrases": [], "words": []}
    events = []
    for phrase in phrases:
        ph = [w["text"].upper() if up else w["text"] for w in phrase]
        end = max(w["end"] for w in phrase) + 0.15
        meta["phrases"].append({"text": " ".join(ph), "start": phrase[0]["start"], "end": end})
        for w in phrase:
            txt = w["text"].upper() if up else w["text"]
            is_e = txt.upper() in emph
            if is_e:
                ev = (f"Dialogue: 0,{_ts(w['start'])},{_ts(end)},KEmp,,0,0,0,,"
                      f"{{\\fad({int(pop_ms)},0)}}{{\\fscx128\\fscy128\\t(0,{pop_ms},120,120)}}{_esc(txt)}")
            else:
                ev = (f"Dialogue: 0,{_ts(w['start'])},{_ts(end)},KWord,,0,0,0,,"
                      f"{{\\fad({int(pop_ms)},0)}}{{\\fscx120\\fscy120\\t(0,{pop_ms},100,100)}}{_esc(txt)}")
            events.append(ev)
            meta["words"].append({"text": txt, "start": w["start"], "end": w["end"],
                                  "emphasis": is_e, "energy": w.get("energy", 0.0)})
    data = header(cap) + "\n".join(events) + "\n"
    if out_ass:
        with open(out_ass, "w", encoding="utf-8") as f:
            f.write(data)
    if out_meta:
        with open(out_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
    return data, meta