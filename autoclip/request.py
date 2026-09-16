"""Intent + format detection from a freeform user request.

Recognizes content FORMAT as first-class: "top 5", "countdown", "trend",
"reaction", "story" etc. The format drives the whole edit language.
"""
import re

COUNTDOWN_RE = re.compile(r"\b(top|best)\s*(\d{1,2})\b|\bcountdown\b|\brank(?:ing)?\b|\blist\b", re.I)
TREND_RE = re.compile(r"\b(trend(?:ing)?|viral|current|latest)\b", re.I)
HOOK_RE = re.compile(r"\b(hook|clips?|moments?|highlights?|funniest|best)\b", re.I)
FORMAT_KINDS = ("countdown", "trend", "moment", "reaction", "story")

def detect_creator(text):
    """Best-effort creator name. Lowercases/dedupes known aliases."""
    aliases = {
        "ishowspeed": "IShowSpeed", "speed": "IShowSpeed", "iwantclips": "IShowSpeed",
        "mrbeast": "MrBeast", "ksihad": "KSI",
    }
    low = text.lower()
    for k, v in aliases.items():
        if k in low:
            return v, k
    return None, None

def detect_format(text, topic_hint=None):
    """Return (format_kind, count, opts)."""
    low = text.lower()
    m = COUNTDOWN_RE.search(low)
    if m:
        n = 0
        for g in m.groups():
            if g and g.isdigit():
                n = int(g)
        return "countdown", (n or 5), {"ranking": True}
    if TREND_RE.search(low):
        return "trend", None, {"auto_pick": True}
    if re.search(r"\breact(?:ion)?\b", low):
        return "reaction", None, {}
    if re.search(r"\bstory\b|vlog", low):
        return "story", None, {}
    return "moment", None, {}

def parse(text):
    """Full parse -> Request dict."""
    creator, _alias = detect_creator(text)
    fmt, count, opts = detect_format(text)
    # Topic = the noun phrase after the format phrase (e.g. "funniest moments")
    topic = None
    m = re.search(r"(?:funniest|funny|best|moments|clips|moments?)\b(.{0,60})", text, re.I)
    if m and m.group(1).strip():
        topic = m.group(1).strip().strip(".,;:") or None
    if not topic:
        m = re.search(r"top\s*\d+\s+(.+)", text, re.I)
        if m:
            topic = m.group(1).strip()
    return {
        "raw": text,
        "creator": creator,
        "format": fmt,
        "count": count,
        "opts": opts,
        "topic": topic,
        "summary": f"{fmt}/{count} about {topic or 'best moments'} by {creator or 'unknown'}",
    }

if __name__ == "__main__":
    for t in [
        "IShowSpeed", "IShowSpeed - Top 5 funniest moments",
        "IShowSpeed - latest viral format", "IShowSpeed - do the current trending format",
        "MrBeast — Top 10 most expensive things",
    ]:
        print(parse(t))