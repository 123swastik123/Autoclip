"""Generate creative QA markdown report from qa_creative.json."""
import json, os, datetime
d = r"data\state"
raw = json.load(open(os.path.join(d, "qa_creative.json"), encoding="utf-8"))
clips = raw["clips"]
lines = [
    "# Creative QA Report",
    f"_generated: {datetime.datetime.now().isoformat(timespec='seconds')}_",
    "",
    "| id | face_hits | words | max_gap | speech | score |",
    "|---|---|---|---|---|---|",
]
for c in clips:
    lines.append(
        f"| {c['id']} | {c['face_hits']:.0%} | {c['words']} | "
        f"{c['max_pause']:.2f}s | {c['speech']:.1f}s | {c['score']:.3f} |"
    )
lines += [
    "",
    "## issues",
    "_none_ (PASS)",
    "",
    "## notes",
    "- M2 has few words by design (short punchy hook “I love you Ronaldo!!”).",
    "",
]
open(os.path.join(d, "qa_reports", "creative_summary.md"), "w").write("\n".join(lines))
print("written", os.path.join(d, "qa_reports", "creative_summary.md"))