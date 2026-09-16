"""Research stage: current viral Shorts / formats / creator signal.

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
    },
    "edit_trend": {
        "max_silence_before_cut": 0.5,
        "hook_seconds": 2.5,
        "runtime_ideal": (20, 45),
        "punch_ins": True,
        "face_follow": True,
        "silence_trim": True,
        "sfx": ["whoosh", "boom"],
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
    },
}

def _path():
    os.makedirs(RESEARCH, exist_ok=True)
    return os.path.join(RESEARCH, "builder.json")

def record_findings(findings: dict, extra_notes: list[str] = None) -> dict:
    """Merge live research notes into the current builder (idempotent-ish)."""
    builder = load(raw=True)
    for k in ("caption_trend", "edit_trend", "countdown_trend", "creator_signal"):
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
        builder = dict(DEFAULTS, window_time=datetime.date.today().isoformat())
    return builder

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
        f"- Emphasis color: {b['caption_trend']['emphasis_color']}",
        "",
        "## Edit trend",
        f"- Silence trim threshold: {b['edit_trend']['max_silence_before_cut']}s",
        f"- Ideal runtime: {b['edit_trend']['runtime_ideal']}s",
        f"- SFX: {', '.join(b['edit_trend']['sfx'])}",
        "",
        "## Countdown trend",
        f"- N={b['countdown_trend']['n']}, card {b['countdown_trend']['card_seconds']}s, "
        f"last card {b['countdown_trend']['last_card_seconds']}s special={b['countdown_trend']['number_special_last']}",
        "",
        "## Creator signal",
    ]
    for note in b["creator_signal"]["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"

def save_report():
    path = os.path.join(RESEARCH, "research_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_markdown())
    return path