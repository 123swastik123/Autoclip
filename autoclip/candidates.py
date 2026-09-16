"""Moment candidate scoring, ranking, and format-aware selection.

The score blends objective signals (speech energy, creator-face visibility,
dialogue payoff) with research-weighted signals (current viral patterns).
Selection respects a quality floor and, for a countdown, orders weakest -> strongest.

NEW: Sequence scoring evaluates ordering, connection, and escalation across moments.
"""
import re, logging, itertools
from collections import Counter

# Comedy/reaction markers that correlate with viral clip selection.
_HYPERE = re.compile(r"\b(oh my god|oh my|bro|what|why|no|let's go|go now|can (die|do|feel)|\*\*|f\*\*k|die now)\b", re.I)
_CHAOSE = re.compile(r"\b(what|whoa|help|stop|crazy|unreal|bro|no way)\b", re.I)

# Topic/connection keywords for sequence bridging
_TOPIC_CLUSTERS = {
    "ronaldo": ["ronaldo", "cr7", "cristiano", "meet", "hotel", "sleep", "portugal"],
    "india": ["india", "indian", "mumbai", "delhi", "chaos", "street", "traffic"],
    "reaction": ["die", "cant", "unreal", "crazy", "insane", "bro", "what", "how"],
    "chaos": ["fuck", "shit", "damn", "wild", "crazy", "mad", "insane"],
    "fan_interaction": ["fan", "name", "manchuna", "brother", "love", "hug", "meet"],
    "celebration": ["win", "goal", "champion", "trophy", "celebration", "party"],
}

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

def _detect_topics(text):
    """Detect which topic clusters are present in text."""
    text_lower = text.lower()
    topics = set()
    for cluster, keywords in _TOPIC_CLUSTERS.items():
        if any(kw in text_lower for kw in keywords):
            topics.add(cluster)
    return topics

def _topic_overlap(topics_a, topics_b):
    """Jaccard similarity between topic sets."""
    if not topics_a or not topics_b:
        return 0.0
    return len(topics_a & topics_b) / len(topics_a | topics_b)

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
    return round(total, 3), subs, _detect_topics(text)

def rank_moments(plans, weights=None):
    """Return plans sorted best-first with score + subscores + topics attached."""
    out = []
    for p in plans:
        score, subs, topics = score_candidate(p, weights)
        out.append({**p, "score": score, "subscores": subs, "topics": list(topics)})
    out.sort(key=lambda x: -x["score"])
    return out

def score_sequence(sequence, seq_weights=None):
    """Score a candidate sequence for ordering quality, connection, escalation.
    
    sequence: list of plans in order #5 -> #4 -> #3 -> #2 -> #1
    Returns (total_score, subscores_dict)
    """
    seq_weights = seq_weights or {
        "escalation": 0.30,        # scores should generally increase
        "topic_connection": 0.25,  # adjacent moments share topics
        "reaction_escalation": 0.20,  # reaction intensity increases
        "energy_escalation": 0.15,    # energy increases
        "payoff_climax": 0.10,        # #1 has highest payoff
    }
    
    n = len(sequence)
    if n < 2:
        return 0.0, {}
    
    scores = [p.get("score", 0) for p in sequence]
    reactions = [p.get("subscores", {}).get("reaction_intensity", 0) for p in sequence]
    energies = [p.get("subscores", {}).get("energy", 0) for p in sequence]
    payoffs = [p.get("subscores", {}).get("payoff", 0) for p in sequence]
    topics_list = [set(p.get("topics", [])) for p in sequence]
    
    # 1. Escalation: scores should generally trend upward
    escalation_score = 0.0
    for i in range(1, n):
        if scores[i] > scores[i-1]:
            escalation_score += 1.0
        elif scores[i] == scores[i-1]:
            escalation_score += 0.5
    escalation_score /= (n - 1)
    
    # 2. Topic connection: adjacent moments share topics
    topic_conn_score = 0.0
    for i in range(1, n):
        topic_conn_score += _topic_overlap(topics_list[i-1], topics_list[i])
    topic_conn_score /= (n - 1)
    
    # 3. Reaction escalation: reaction intensity should increase
    reaction_esc_score = 0.0
    for i in range(1, n):
        if reactions[i] > reactions[i-1]:
            reaction_esc_score += 1.0
        elif reactions[i] == reactions[i-1]:
            reaction_esc_score += 0.5
    reaction_esc_score /= (n - 1)
    
    # 4. Energy escalation
    energy_esc_score = 0.0
    for i in range(1, n):
        if energies[i] > energies[i-1]:
            energy_esc_score += 1.0
        elif energies[i] == energies[i-1]:
            energy_esc_score += 0.5
    energy_esc_score /= (n - 1)
    
    # 5. Payoff climax: #1 should have highest payoff
    payoff_climax_score = 1.0 if payoffs[-1] == max(payoffs) else 0.0
    # Bonus if payoff steadily increases
    payoff_increasing = all(payoffs[i] >= payoffs[i-1] for i in range(1, n))
    if payoff_increasing:
        payoff_climax_score = min(1.0, payoff_climax_score + 0.2)
    
    subs = {
        "escalation": round(escalation_score, 3),
        "topic_connection": round(topic_conn_score, 3),
        "reaction_escalation": round(reaction_esc_score, 3),
        "energy_escalation": round(energy_esc_score, 3),
        "payoff_climax": round(payoff_climax_score, 3),
    }
    total = sum(subs[k] * seq_weights[k] for k in subs)
    return round(total, 3), subs

def find_best_sequence(ranked, n, seq_weights=None, max_same_source=2):
    """Find the best ordered sequence of n moments from ranked candidates.
    
    Evaluates all valid combinations/permutations and scores them for sequence quality.
    Returns the best sequence ordered #5 -> #4 -> #3 -> #2 -> #1.
    """
    floor = 0.30
    # Filter by quality floor
    pool = [p for p in ranked if p["subscores"].get("creator_focus", 0.0) >= floor]
    
    # Limit pool size for combinatorial explosion
    if len(pool) > 12:
        pool = pool[:12]
    
    best_seq = None
    best_score = -1.0
    best_subs = {}
    
    # From itertools import
    from itertools import combinations, permutations

    distinct_src = len({p.get("src") for p in pool})
    src_lim = max_same_source if distinct_src > 1 else len(pool)
    
    for combo in combinations(pool, n):
        # Check source diversity (skip when the whole pool is one source)
        src_counts = Counter(p.get("src") for p in combo)
        if any(v > src_lim for v in src_counts.values()):
            continue
        
        # Try all permutations (orderings) of this combination
        for perm in permutations(combo):
            seq_score, subs = score_sequence(list(perm), seq_weights)
            if seq_score > best_score:
                best_score = seq_score
                best_seq = list(perm)
                best_subs = subs
    
    if best_seq is None:
        # Fallback: simple weakest-to-strongest
        pool.sort(key=lambda x: x["score"])
        best_seq = pool[:n]
        best_score, best_subs = score_sequence(best_seq, seq_weights)
        logging.warning("Sequence optimization failed; using fallback ordering")
    
    # Assign ranks: weakest gets #5, strongest gets #1
    for i, p in enumerate(best_seq):
        p["rank"] = n - i
        p["card_label"] = f"#{n - i}"
        p["special_last"] = (i == len(best_seq) - 1)
        p["sequence_score"] = best_score
        p["sequence_subscores"] = best_subs
    
    # Return ordered by rank descending for timeline: #5, #4, ..., #1
    best_seq.sort(key=lambda x: -x["rank"])
    return best_seq

def assign_countdown(ranked, n, max_same_source=2, seq_weights=None):
    """Format-aware selection for a countdown with sequence optimization.
    
    If editorial ranks provided, use those. Otherwise optimize for sequence quality.
    """
    editorial = [p for p in ranked if p.get("editorial_rank")]
    if editorial and len(editorial) >= n:
        for p in editorial:
            p["rank"] = int(p["editorial_rank"])
            p["card_label"] = f"#{p['rank']}"
            p["special_last"] = (p["rank"] == 1)
        editorial.sort(key=lambda x: -x["rank"])
        return editorial[:n]
    
    # Use sequence optimization
    return find_best_sequence(ranked, n, seq_weights, max_same_source)