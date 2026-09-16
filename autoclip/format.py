"""Format / pattern analysis: research profile + request -> concrete edit directives.

Keeps a single AutoClip quality bar while letting the researched trend shape the
editing language (captions, pacing, countdown presentation, music, sequence,
selection weights).
"""
from . import research

SEQUENCE_WEIGHTS = {
    "escalation": 0.30,
    "topic_connection": 0.25,
    "reaction_escalation": 0.20,
    "energy_escalation": 0.15,
    "payoff_climax": 0.10,
}

def build_directives(request):
    req_fmt = request.get("format", "moment")
    n = request.get("count") or 5
    b = research.load()
    cap = dict(b["caption_trend"])
    ed = dict(b["edit_trend"])
    cd = dict(b["countdown_trend"])
    mus = dict(b.get("music_trend", {}))
    seq = dict(b.get("sequence_trend", {}))

    # Only apply countdown language if the request (or fallback) asks for it.
    countdown = req_fmt == "countdown"
    if countdown and n:
        cd["n"] = n

    # Research-driven selection weights (individual moment quality)
    weights = {
        "comedy": 0.30,
        "reaction_intensity": 0.20,
        "creator_focus": 0.15,
        "energy": 0.13,
        "payoff": 0.10,
        "standalone": 0.07,
        "viral_signal": 0.05,
    }

    return {
        "format": req_fmt,
        "countdown": cd,
        "caption": cap,
        "edit": ed,
        "music": mus,
        "sequence": seq,
        "sequence_weights": dict(SEQUENCE_WEIGHTS),
        "weights": weights,
        "quality_floor": {
            "min_face_hits": 0.3,       # >=30% of sampled frames must show creator face
            "min_clip_seconds": 6,
            "max_clip_seconds": 24,
            "max_silence_hole": 2.6,    # longest acceptable dead-audio gap inside a clip
            "min_sequence_score": 0.55, # ordering/connection/flow must clear this
        },
        "hook": {
            "title_seconds": 1.6,
            "max_before_first_payoff": 2.5,
        },
    }