"""Format / pattern analysis: research profile + request -> concrete edit directives.

Keeps a single AutoClip quality bar while letting the researched trend shape the
editing language (captions, pacing, countdown presentation, SFX, selection weights).
"""
from . import research

def build_directives(request):
    req_fmt = request.get("format", "moment")
    n = request.get("count") or 5
    b = research.load()
    cap = dict(b["caption_trend"])
    ed = dict(b["edit_trend"])
    cd = dict(b["countdown_trend"])

    # Only apply countdown language if the request (or fallback) asks for it.
    countdown = req_fmt == "countdown"
    if countdown and n:
        cd["n"] = n

    # Research-driven selection weights
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
        "weights": weights,
        "quality_floor": {
            "min_face_hits": 0.3,       # >=30% of sampled frames must show creator face
            "min_clip_seconds": 6,
            "max_clip_seconds": 24,
            "max_silence_hole": 2.6,    # longest acceptable dead-audio gap inside a clip
        },
        "hook": {
            "title_seconds": 1.6,
            "max_before_first_payoff": 2.5,
        },
    }