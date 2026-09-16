"""Moment candidate scoring, ranking, and format-aware selection.

The score blends objective signals (speech energy, creator-face visibility,
dialogue payoff) with research-weighted signals (current viral patterns).
Selection respects a quality floor and, for a countdown, orders weakest -> strongest.
"""
import re, logging

# Comedy/reaction markers that correlate with viral clip selection.
_HYPERE = re.compile(r"\b(oh my god|oh my|bro|what|why|no|let's go|go now|can (die|do|feel)|\*\*|f\*\*k|die now)\b", re.I)
_CHAOSE = re.compile(r"\b(what|whoa|help|stop|crazy|unreal|bro|no way)\b", re.I)

def _speech_rate(words):
    if not words:
        return 0.0
    d = max(words[-1]["end"] - words[0]["start"], 0.01)
    return len(words) / d

def _energy_metrics(words):
    if not words:
        return 0.0, 0.0
    es = [w.get("energy", 0.0) for w in words]
    return sum(es)/len(es), max(es)

def score_candidate(plan, weights=None):
    """plan: dict(id, source, t0, t1, kind, words, face_hits, face_center, viral_tags)."""
    weights = weights or {
        "comedy": .30, "reaction_intensity": .20, "creator_focus": .15,
        "energy": .13, "payoff": .10, "standalone": .07, "viral_signal": .05}
    words = plan.get("words", [])
    text = " ".join(w["text"] for w in words)
    rate = _speech_rate(words)
    mean_e, max_e = _energy_metrics(words)
    dur = max(words[-1]["end"] - words[0]["start"], 1.0) if words else 10.0

    comedy = float(bool(_HYPERE.search(text)))
    chaos = float(bool(_CHAOSE.search(text)) and rate > 2.4)
    reaction = min(1.0, 0.5 * (1.0 if comedy else 0.0) + 0.5 * (min(1.0, max_e * 3)))
    focus = float(plan.get("face_hits", 0.5)) or 0.0
    energy = min(1.0, max(mean_e * 2.0, rate / 5.0))
    payoff = 0.0
    if words:
        third = len(words) // 3
        tail = words[-third:] if third else words
        avg_tail = sum(w["energy"] for w in tail) / len(tail)
        payoff = min(1.0, max(0.0, avg_tail - mean_e) * 4)
    standalone = 1.0 if (words and words[0]["start"] <= 2.0) else 0.7

    viral = 0.0
    vt = (plan.get("viral_tags") or [])
    if vt:
        viral = min(1.0, len([t for t in vt if t.lower() in text.lower()]) * 0.6)

    subs = {"comedy": round(comedy,3), "reaction_intensity": round(reaction,3),
            "creator_focus": round(focus,3), "energy": round(energy,3),
            "payoff": round(payoff,3), "standalone": round(standalone,3),
            "viral_signal": round(viral,3)}
    total = sum(subs[k] * weights[k] for k in subs)
    return round(total, 3), subs

def rank_moments(plans, weights=None):
    """Return plans sorted best-first with score + subscores attached."""
    out = []
    for p in plans:
        score, subs = score_candidate(p, weights)
        out.append({**p, "score": score, "subscores": subs})
    out.sort(key=lambda x: -x["score"])
    return out

def assign_countdown(ranked, n, max_same_source=2):
    """Format-aware selection for a countdown: enforce quality floor, spread
    sources, then order weakest -> strongest (so #1 is the real payoff).

    Plans carrying an explicit 'editorial_rank' (a human/curator call - the
    funniest/strongest clip is a judgment, not a metric) win over auto-ranking.

    Returns list of plans with 'rank' and 'card_label' set, ordered by rank 5..1.
    """
    editorial = [p for p in ranked if p.get("editorial_rank")]
    if editorial and len(editorial) >= n:
        for p in editorial:
            p["rank"] = int(p["editorial_rank"])
            p["card_label"] = f"#{p['rank']}"
            p["special_last"] = (p["rank"] == 1)
        editorial.sort(key=lambda x: -x["rank"])
        return editorial[:n]
    floor = 0.30  # creator focus floor
    pool = []
    per_src = {}
    for p in ranked:
        if p["subscores"].get("creator_focus", 0.0) < floor:
            continue
        src = p.get("src")
        if per_src.get(src, 0) >= max_same_source:
            continue
        pool.append(p)
        per_src[src] = per_src.get(src, 0) + 1
        if len(pool) >= n:
            break
    if len(pool) < n:
        logging.warning("Only %d candidates cleared the floor; selecting what exists.", len(pool))
    pool.sort(key=lambda x: x["score"])          # weakest first
    selected = pool[:n]
    for i, p in enumerate(selected):
        p["rank"] = n - i                         # strongest gets #1
        p["card_label"] = f"#{n - i}"
        p["special_last"] = (i == len(selected) - 1)
    # ordered by rank descending for timeline: #5, #4, ..., #1
    selected.sort(key=lambda x: -x["rank"])
    return selected