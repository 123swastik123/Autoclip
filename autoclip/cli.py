"""AutoClip CLI.

Usage:
  autoclip parse "<request>"                 -> intent/format/topic detection
  autoclip research                          -> show current trend research report
  autoclip research --refresh-notes          -> (agent hook) re-emit canned notes
  autoclip run   <manifest.json> [--out x.mp4] [--qa-only]
  autoclip qa    <file.mp4>

The heavy research + candidate extraction steps (web search, whisper verification,
face checks) are run by the orchestrating agent; the CLI executes the deterministic
build + QA parts against a manifest.
"""
import argparse, json, os, sys
from . import request as request_mod
from . import research as research_mod
from . import format as format_mod
from . import candidates as candidates_mod
from . import qa as qa_mod

def cmd_parse(args):
    r = request_mod.parse(args.text)
    print(json.dumps(r, indent=2))

def cmd_research(args):
    if args.refresh_notes:
        t = ("CARRIER_SIGNAL 2026: IShowSpeed viral moments center on Ronaldo/World Cup "
             "fanaticism (meeting Ronaldo, hotels, airports) plus high-energy IRL chaos; "
             "portrait 9:16 originals outperform re-edited landscape clips.")
        research_mod.record_findings({}, extra_notes=[t])
    print(research_mod.report_markdown())
    print("\n(saved to)", research_mod.save_report())

def cmd_qa(args):
    tec = qa_mod.tech_qa(args.file)
    print("TECHNICAL:", "PASS" if tec["ok"] else "FAIL")
    for e in tec["errors"]:
        print("  -", e)
    print(json.dumps(tec.get("found", {}), indent=2))

def cmd_transcribe(args):
    from . import mediatools as mt
    words = mt.whisper_words(args.video)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"video": args.video, "words": words}, f, indent=1)
    print(f"{len(words)} words -> {args.out}")

def cmd_creative_qa(args):
    from . import mediatools as mt, candidates as cand
    from . import config, qa as qa_mod
    import os, datetime
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    fmt = format_mod.build_directives(manifest["request"])
    clips = []
    seq_ordered = []
    for p in manifest["plans"]:
        r = p.get("editorial_rank") or p.get("rank")
        vid = os.path.join(config.media_dir(), f"M{r}_capped.mp4" if r is not None else f"{p['id']}_capped.mp4")
        if not os.path.exists(vid):
            vid = os.path.join(config.media_dir(), f"{p['id']}_capped.mp4")
        cx, hits, area = mt.face_center(vid, sample_step=0.4)
        words = p.get("words", [])
        dur = (words[-1]["end"] - words[0]["start"]) if words else 0
        gaps = [words[i + 1]["start"] - words[i]["end"] for i in range(len(words) - 1)]
        maxg = round(max(gaps), 2) if gaps else 0.0
        score, subs, topics = cand.score_candidate(p, fmt["weights"])
        clips.append({"id": p["id"], "dur": round(p["t1"] - p["t0"], 2), "face_hits": round(hits, 2),
                      "words": len(words), "max_pause": maxg, "speech": round(dur, 1),
                      "score": score, "subscores": subs, "punch": bool(p.get("punch")),
                      "topics": list(topics)})
        p["score"], p["subscores"], p["topics"] = score, subs, list(topics)
        seq_ordered.append(p)
        print(f"{p['id']:4s} face_hits={hits*100:3.0f}% area={area*100:3.0f}%  max_gap={maxg:.2f}s  "
              f"words={len(words):3d}  score={score}")
        # caption meta check
        cap_file = os.path.join(config.media_dir(), f"M{r}_cap.json" if r is not None else f"{p['id']}_cap.json")
        if not os.path.exists(cap_file):
            cap_file = os.path.join(config.media_dir(), f"{p['id']}_cap.json")

    # order plans #5..#1 for sequence assessment
    seq_ordered.sort(key=lambda p: -(p.get("editorial_rank") or p.get("rank") or 0))
    seq_score, seq_subs = cand.score_sequence(seq_ordered, fmt.get("sequence_weights"))
    for q in seq_ordered:
        q["sequence_score"] = seq_score
        q["sequence_subscores"] = seq_subs
    seq_res = qa_mod.sequence_qa(seq_ordered, seq_floor=fmt["quality_floor"].get("min_sequence_score", 0.55))
    print("SEQUENCE:", "PASS" if not seq_res["issues"] else "FAIL",
          json.dumps(seq_res["metrics"]))
    for i in seq_res["issues"]:
        print("  ISSUE:", i)
    for n in seq_res["notes"]:
        print("  note:", n)

    caption_metas = []
    for p in clips:
        r = next((q for q in seq_ordered if q["id"] == p["id"]), p)
        cap_file = os.path.join(config.media_dir(), f"M{r.get('editorial_rank') or r.get('rank')}_cap.json")
        if os.path.exists(cap_file):
            try:
                caption_metas.append(json.load(open(cap_file, encoding="utf-8")))
            except Exception:
                pass

    res = qa_mod.creative_qa(clips, sequence=seq_ordered, caption_metas=caption_metas)
    os.makedirs(os.path.join("data", "state"), exist_ok=True)
    with open(os.path.join("data", "state", "qa_creative.json"), "w", encoding="utf-8") as f:
        json.dump({"clips": clips, "creative": res, "sequence": seq_res,
                   "ts": datetime.datetime.now().isoformat(timespec="seconds")}, f, indent=1)
    print("CREATIVE QA:", "PASS" if res["ok"] else "FAIL")
    for i in res["issues"]:
        print("  ISSUE:", i)
    for n in res["notes"]:
        print("  note:", n)
    return res

def cmd_run(args):
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    req = manifest["request"]
    fmt = format_mod.build_directives(req)
    ranked = candidates_mod.rank_moments(manifest["plans"], fmt["weights"])
    sel = candidates_mod.assign_countdown(ranked, fmt["countdown"]["n"],
                                          seq_weights=fmt.get("sequence_weights"))
    print(f"Selected {len(sel)} moments ordered #5.. #1")
    for p in sel:
        print(f"  M{p.get('id')} rank#{p['rank']} score={p['score']} src={p.get('src')}")
    if sel:
        seq_score, seq_subs = candidates_mod.score_sequence(sel, fmt.get("sequence_weights"))
        for p in sel:
            p["sequence_score"] = seq_score
            p["sequence_subscores"] = seq_subs
        print(f"  sequence_score={seq_score:.3f} "
              f"escalation={seq_subs.get('escalation')} topic_conn={seq_subs.get('topic_connection')} "
              f"reaction_esc={seq_subs.get('reaction_escalation')} payoff_climax={seq_subs.get('payoff_climax')}")

    from . import edit as edit_mod
    import datetime
    nc = fmt["countdown"]
    out_dir = os.path.dirname(os.path.abspath(args.out)) or ""
    os.makedirs(out_dir, exist_ok=True)
    hook = fmt["hook"]
    # render moments first so the #1 climax can back the title card
    built = {p["id"]: _build_one(p, fmt, i) for i, p in enumerate(sel)}
    last = sel[-1]
    title = edit_mod.make_title(built[last["id"]][1], hook)
    clips = [title]
    for p in sel:
        card, clip = built[p["id"]]
        clips.append(card); clips.append(clip)
    edit_mod.assemble(clips, args.out, hook, whoosh_at=None, music_profile=fmt.get("music"))
    print("rendered", args.out)

    tec = qa_mod.tech_qa(args.out)
    print("TECHNICAL QA:", "PASS" if tec["ok"] else "FAIL", json.dumps(tec.get("found", {}).get("duration")) if tec.get("found") else "")
    for e in tec["errors"]:
        print("  -", e)

    # creative QA (incl. sequence + captions) persisted automatically
    import subprocess
    r = subprocess.run([sys.executable, "-m", "autoclip.cli", "creative-qa", args.manifest],
                       capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr[-1500:])

def _build_one(p, fmt, i):
    """Render one moment: prep -> reframe -> punch -> karaoke -> return (card, clip)."""
    from . import edit as edit_mod
    out_id = f"M{p['rank']}"
    prep = edit_mod.prep(p, out_id)
    reframed, _face = edit_mod.reframe(prep, p, out_id)
    em = p.get("emphasis", [])
    cap_profile = fmt["caption"]
    words = p.get("words", [])
    if fmt["edit"].get("punch_ins") and words:
        peak = max(words, key=lambda w: w.get("energy", 0))
        p["punch"] = {"tin": peak["start"] + 0.05}
    punched = edit_mod.add_punch(reframed, p, out_id)
    capped = edit_mod.burn_karaoke(punched, prep, words, em, cap_profile, out_id)
    dur = fmt["countdown"]["last_card_seconds"] if p.get("special_last") \
        else fmt["countdown"]["card_seconds"]
    who, boom = edit_mod.make_sfx()
    card = edit_mod.make_card(p["card_label"], dur, p.get("special_last", False),
                              capped, out_id, boom)
    return card, capped

def main(argv=None):
    ap = argparse.ArgumentParser(prog="autoclip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse"); p.add_argument("text"); p.set_defaults(fn=cmd_parse)
    p = sub.add_parser("research"); p.add_argument("--refresh-notes", action="store_true"); p.set_defaults(fn=cmd_research)
    p = sub.add_parser("transcribe"); p.add_argument("video"); p.add_argument("out"); p.set_defaults(fn=cmd_transcribe)
    p = sub.add_parser("creative-qa"); p.add_argument("manifest"); p.set_defaults(fn=cmd_creative_qa)
    p = sub.add_parser("qa"); p.add_argument("file"); p.set_defaults(fn=cmd_qa)
    p = sub.add_parser("run"); p.add_argument("manifest"); p.add_argument("--out", default="autoclip_out.mp4"); p.set_defaults(fn=cmd_run)
    args = ap.parse_args(argv)
    args.fn(args)

if __name__ == "__main__":
    main()