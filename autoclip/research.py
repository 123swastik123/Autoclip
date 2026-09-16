"""Research stage: current viral Shorts / formats / creator signal + background music trends.

Consumes research notes (produced by live web research) and compiles them into a
structured Builder profile that downstream stages read. Nothing is hardcoded as
"the one true style" - the research determines the edit language.

The CLI itself does not browse; the orchestrating agent performs web searches and
records findings via `record_findings()`. `load()` returns the current profile.
"""
import json, os, datetime
from .config import RESEARCH

DEFAULTS = {
    "window_time": datetime.date.today().isoformat(),
    "caption_trend": {
        "style": "karaoke_words",          # word-by-word highlight
        "font": "Arial Black",
        "color": "white",
        "outline": "black",
        "size": 92,
        "pos": "center_lower_third",
        "margin_v": 460,
        "words_per_line": 5,
        "emphasis_color": "#FFD200",
        "pop_ms": 130,
        "uppercase": True,
        "animation": "word_pop",           # word_pop, phrase_reveal, highlight_sweep
        "highlight_style": "bold_scale",   # bold_scale, color_shift, underline
        "emphasis_words": [],              # auto-detected + manual
        "safe_zone_margin": 0.15,          # 15% from edges
    },
    "edit_trend": {
        "max_silence_before_cut": 0.5,
        "hook_seconds": 2.5,
        "runtime_ideal": (20, 45),
        "punch_ins": True,
        "face_follow": True,
        "silence_trim": True,
        "sfx": ["whoosh", "boom"],
        "transition_style": "hard_cut",    # hard_cut, smooth_slide, zoom_punch
        "pacing": "energetic",             # energetic, breathing, mixed
    },
    "music_trend": {
        "enabled": True,
        "style": "lofi_hiphop",            # lofi_hiphop, phonk, synthwave, ambient, trending_sound
        "volume_duck_db": -18,             # duck level during speech
        "fade_in_ms": 300,
        "fade_out_ms": 500,
        "use_trending": True,              # try to use current trending sounds
        "copyright_safe": True,            # prefer royalty-free / library
        "match_creator": True,             # adapt to creator's usual vibe
        "track_per_moment": False,         # one track whole video or per-moment
        "build_ups": True,                 # use music builds for escalation
    },
    "countdown_trend": {
        "n": 5,
        "card_seconds": 1.1,
        "card_animation": "number_pop",
        "gradient": True,
        "number_special_last": True,
        "last_card_seconds": 1.6,
        "rank_label": "none",
    },
    "creator_signal": {
        "weight_bonus": [],
        "notes": [],
        "typical_music": [],               # creator's usual music style
        "common_topics": [],               # recurring themes for connection scoring
    },
    "sequence_trend": {
        "require_escalation": True,        # #5->#1 must escalate
        "topic_threads": True,             # prefer thematic connections
        "reaction_escalation": True,       # reaction intensity should increase
        "context_bridges": True,           # look for contextual links
        "max_gap_between": 2.0,            # max dead air between moments
    },
}

def _path():
    os.makedirs(RESEARCH, exist_ok=True)
    return os.path.join(RESEARCH, "builder.json")

def record_findings(findings: dict, extra_notes: list[str] = None) -> dict:
    """Merge live research notes into the current builder (idempotent-ish)."""
    builder = load(raw=True)
    for k in ("caption_trend", "edit_trend", "music_trend", "countdown_trend", 
              "creator_signal", "sequence_trend"):
        if k in findings and isinstance(findings[k], dict):
            builder[k].update(findings[k])
    if extra_notes:
        builder["creator_signal"]["notes"].extend(extra_notes)
    builder["window_time"] = findings.get("window_time", builder.get("window_time"))
    os.makedirs(RESEARCH, exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(builder, f, indent=1)
    return builder

def load(raw=False):
    if os.path.exists(_path()):
        with open(_path(), "r", encoding="utf-8") as f:
            builder = json.load(f)
    else:
        builder = {}
    # deep-merge defaults so new research sections are always present
    merged = json.loads(json.dumps(DEFAULTS))
    merged.update(builder)
    for k, v in builder.items():
        if isinstance(v, dict) and isinstance(DEFAULTS.get(k), dict):
            merged[k] = {**DEFAULTS[k], **v}
    merged["window_time"] = builder.get("window_time", merged.get("window_time"))
    return merged

def report_markdown():
    """Render the research profile as a readable report (also committed to repo)."""
    b = load()
    lines = [
        "# AutoClip Trend Research Report",
        "",
        f"Analysis window: {b['window_time']}",
        "",
        "## Caption trend",
        f"- Style: {b['caption_trend']['style']} ({b['caption_trend']['pos']})",
        f"- Font: {b['caption_trend']['font']} size {b['caption_trend']['size']}",
        f"- Animation: {b['caption_trend']['animation']}",
        f"- Emphasis color: {b['caption_trend']['emphasis_color']}",
        f"- Highlight: {b['caption_trend']['highlight_style']}",
        "",
        "## Edit trend",
        f"- Silence trim threshold: {b['edit_trend']['max_silence_before_cut']}s",
        f"- Ideal runtime: {b['edit_trend']['runtime_ideal']}s",
        f"- SFX: {', '.join(b['edit_trend']['sfx'])}",
        f"- Transition: {b['edit_trend']['transition_style']}",
        f"- Pacing: {b['edit_trend']['pacing']}",
        "",
        "## Music trend",
        f"- Enabled: {b['music_trend']['enabled']}",
        f"- Style: {b['music_trend']['style']}",
        f"- Duck: {b['music_trend']['volume_duck_db']}dB",
        f"- Trending: {b['music_trend']['use_trending']}",
        f"- Copyright safe: {b['music_trend']['copyright_safe']}",
        f"- Build-ups: {b['music_trend']['build_ups']}",
        "",
        "## Sequence trend",
        f"- Require escalation: {b['sequence_trend']['require_escalation']}",
        f"- Topic threads: {b['sequence_trend']['topic_threads']}",
        f"- Reaction escalation: {b['sequence_trend']['reaction_escalation']}",
        f"- Context bridges: {b['sequence_trend']['context_bridges']}",
        "",
        "## Creator signal",
    ]
    for note in b["creator_signal"]["notes"]:
        lines.append(f"- {note}")
    if b["creator_signal"]["typical_music"]:
        lines.append(f"- Typical music: {', '.join(b['creator_signal']['typical_music'])}")
    if b["creator_signal"]["common_topics"]:
        lines.append(f"- Common topics: {', '.join(b['creator_signal']['common_topics'])}")
    return "\n".join(lines) + "\n"

def save_report():
    path = os.path.join(RESEARCH, "research_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_markdown())
    return path