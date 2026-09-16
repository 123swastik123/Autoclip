"""9:16 editing: prep -> reframe (face-follow) -> punch-ins -> karaoke captions ->
countdown cards / title / SFX / BGM (ducked) -> final assembly -> loudness normalize."""
import os, subprocess
from . import config, mediatools as mt
from . import captions as capgen
from . import music as musicgen

def _p(t):  # project media path
    return os.path.join(config.media_dir(), t)

def prep(plan, out_id):
    src = plan.get("src_path") or _p(plan["src"])
    out = _p(f"{out_id}_prep.mp4")
    if os.path.exists(out):
        os.remove(out)
    mt.prep_cut(src, plan["t0"], plan["t1"], out, fps=config.FPS_OUT)
    return out

def reframe(prep_path, plan, out_id):
    """Face-following reframe to 1080x1920. Returns (video_path, face_stats).

    Landscape sources: crop box center linearly interpolates from the face's first-half
    to second-half median position so the creator stays framed while moving.
    """
    out = _p(f"{out_id}_reframed.mp4")
    if plan["kind"] == "portrait":
        vf = ("scale=1080:1920:flags=lanczos,"
              "crop=1040:1856:(in_w-1040)/2+(in_w/2)*0.02*sin(t*0.6):(in_h-1856)/2,"
              "scale=1080:1920:flags=lanczos,format=yuv420p")
    else:
        dur = mt.ffprobe_dur(prep_path) or (plan.get("t1", 10) - plan.get("t0", 0))
        track = mt.face_track(prep_path, sample_step=0.5)
        hits = float(len([t for t in track if t[1] is not None])) / max(1, len(track))
        sel = [x for _t, x, _a in track if x is not None] or [0.5]
        half = max(1, len(sel) // 2)
        part0, part1 = sel[:half], sel[half:]
        x0 = float(sorted(part0)[len(part0) // 2])
        x1 = float(sorted(part1)[len(part1) // 2]) if part1 else x0
        plan["face_stats"] = {"cx0": round(x0, 3), "cx1": round(x1, 3),
                              "hits": round(hits, 3), "area": round(max([a for _t,_x,a in track if _x is not None] or [0]), 3)}
        w, h = 405, 720
        maxx = 1280 - w
        xr = f"(({x0}+({x1}-{x0})*t/{dur:.3f}))*{maxx}+0.02*{maxx}*sin(t*0.5)"
        xc = f"if(lt({xr},0),0,if(gt({xr},{maxx}),{maxx},{xr}))"
        vf = (f"crop={w}:{h}:'{xc}':0,scale=1080:1920:flags=lanczos,"
              "crop=1040:1876:(in_w-1040)/2+(in_w/2)*0.01*sin(t*0.5):(in_h-1876)/2,"
              "scale=1080:1920:flags=lanczos,format=yuv420p")
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", prep_path,
            "-vf", vf, "-r", str(config.FPS_OUT), "-c:v", "libx264", "-preset", "fast",
            "-crf", "17", out])
    return out, plan.get("face_stats")

def _zoom_expr(tin, rz, z):
    """Zoom factor z(t): 1 -> z ramping over rz seconds starting at tin, then hold."""
    zt = f"(1+({z}-1)*((t-{tin})/{rz}))"
    return f"if(lt(t,{tin}),1,if(lt(t,{tin}+{rz}),{zt},{z}))"

def add_punch(input_path, plan, out_id):
    """Single punch-in on the reaction peak (highest-energy word). Returns path."""
    punch = plan.get("punch")
    if not punch:
        return input_path
    tin = round(punch["tin"], 3); z = punch.get("z", 1.14); rz = 0.26
    cx, cy = 0.5, 0.5
    fs = plan.get("face_stats") or {}
    if "cx0" in fs:
        c0 = fs["cx0"]; c1 = fs.get("cx1", fs["cx0"])
        dur = max(float(plan.get("t1", tin + 5) - plan.get("t0", 0)), 0.1)
        cx = c0 + (c1 - c0) * min(1.0, tin / dur)
    out = _p(f"{out_id}_punch.mp4")
    Z = _zoom_expr(tin, rz, z)
    x = f"({cx}*iw-iw/'{Z}'/2)"
    y = f"({cy}*ih-ih/'{Z}'/2)"
    vf = (f"crop=iw/'{Z}':ih/'{Z}':{x}:{y},"
          "scale=1080:1920:flags=lanczos,format=yuv420p")
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", input_path,
            "-vf", vf, "-r", str(config.FPS_OUT), "-c:v", "libx264", "-preset", "fast",
            "-crf", "17", out])
    return out

def burn_karaoke(input_path, prep_path, words, emphasis, cap_profile, out_id):
    """Burn word-pop captions; keep aligned audio from prep with tiny edge fades."""
    ass = _p(f"{out_id}_cap.ass")
    meta = _p(f"{out_id}_cap.json")
    capgen.make(words, cap_profile, emphasis, out_ass=ass, out_meta=meta)
    out = _p(f"{out_id}_capped.mp4")
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    dur = mt.ffprobe_dur(input_path) or 0
    aout = max(0.0, dur - 0.20)
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", input_path, "-i", prep_path,
            "-map", "0:v", "-map", "1:a",
            "-vf", f"subtitles='{ass_esc}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", f"afade=t=in:st=0:d=0.08,afade=t=out:st={aout:.2f}:d=0.20", out])
    return out

# ---------------- SFX & cards ----------------
def make_sfx():
    who = _p("whoosh.wav")
    boom = _p("boom.wav")
    for f in (who, boom):
        if os.path.exists(f) and os.path.getsize(f) < 1000:
            os.remove(f)  # stale/partial generation from an earlier run
    if not os.path.exists(who):
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "anoisesrc=colour=white:r=48000:d=0.6:a=0.55",
                "-af", "highpass=f=500,lowpass=f=2600,afade=t=in:st=0:d=0.12,afade=t=out:st=0.42:d=0.18",
                "-ac", "2", who])
    # boom: low-frequency thud (tone + pink noise thump), 0.9s - primitives only
    # (custom aeval expressions are a parsing hazard in -af graphs)
    if not os.path.exists(boom):
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=58:sample_rate=48000:duration=0.9",
                "-f", "lavfi", "-i", "anoisesrc=colour=pink:sample_rate=48000:duration=0.35:a=0.7",
                "-filter_complex",
                ("[0:a]afade=t=in:st=0:d=0.03,afade=t=out:st=0.55:d=0.35,lowpass=f=90[tone];"
                 "[1:a]lowpass=f=140,afade=t=out:st=0.02:d=0.30[thud];"
                 "[tone][thud]amix=inputs=2:duration=longest:normalize=0,"
                 "dynaudnorm=f=200:g=15,volume=1.6,atrim=0:0.9,aresample=48000,"
                 "aformat=channel_layouts=stereo[boom]"),
                "-map", "[boom]", "-ac", "2", boom])
    return who, boom

def _card_ass(number, dur, special, out_ass):
    style = ("TStack, Arial Black, 210, &H00FFFFFF, &H000000FF, &H00000000, &H00000000, "
             "-1, 0, 0, 0, 100, 100, 8, 0, 1, 10, 5, 5, 5, 880, 1")
    sub = ("TSub, Arial Black, 78, &H00FFD200, &H000000FF, &H00000000, &H00000000, "
           "-1, 0, 0, 0, 100, 100, 2, 0, 1, 7, 3, 2, 5, 880, 1")
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
           "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding\n"
           f"Style: {style}\nStyle: {sub}\n\n[Events]\n"
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    pop = "{\\fscx250\\fscy250\\t(0,300,110,110)\\t(320,620,100,100)}"
    ev = f"Dialogue: 0,0:00:00.10,0:00:{int(dur*10):02d}.00,TStack,,0,0,0,,{pop}{number}"
    lines = [hdr, ev]
    if special:
        lines.append(f"Dialogue: 0,0:00:00.42,0:00:{int(dur*10):02d}.00,TSub,,0,0,0,,{{\\fad(200,120)}}THE BEST ONE")
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def make_card(number, dur, special, bg_src, out_id, boom):
    bg = _p(f"{out_id}_card_bg.png")
    ass = _p(f"{out_id}_card.ass")
    out = _p(f"{out_id}_card.mp4")
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.3", "-i", bg_src,
            "-frames:v", "1", bg])
    _card_ass(number, dur, special, ass)
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", bg, "-i", boom,
            "-map", "0:v", "-map", "1:a",
            "-vf", (f"scale=1080:1920:flags=lanczos,boxblur=22:2,eq=brightness=-0.30:contrast=1.10,"
                    f"subtitles='{ass_esc}'"),
            "-t", str(round(dur + 0.25, 2)), "-r", str(config.FPS_OUT),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", "adelay=80|80,apad=pad_dur=1.0,atrim=0:" + str(round(dur + 0.25, 2)),
            out])
    return out

def make_title(bg_src, hook, out_id="title_raw"):
    """Fast hook title card (~1.6s) - instant readable payoff text."""
    bg = _p(f"{out_id}_bg.png")
    ass = _p(f"{out_id}.ass")
    out = _p(f"{out_id}.mp4")
    who, _boom = make_sfx()
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.5", "-i", bg_src,
            "-frames:v", "1", bg])
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
           "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding\n"
           f"Style: Hook, Arial Black, 120, &H00FFFFFF, &H000000FF, &H00000000, &H00000000, "
           f"-1, 0, 0, 0, 100, 100, 2, 0, 1, 9, 5, 5, 5, 300, 1\n"
           f"Style: Sub, Arial Black, 84, &H00FFD200, &H000000FF, &H00000000, &H00000000, "
           f"-1, 0, 0, 0, 100, 100, 2, 0, 1, 7, 3, 2, 5, 300, 1\n\n[Events]\n"
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev1 = "Dialogue: 0,0:00:00.10,0:00:01.55,Hook,,0,0,0,,{\\fscx150\\fscy150\\t(0,220,100,100)}TOP 5 FUNNIEST"
    ev2 = "Dialogue: 0,0:00:00.28,0:00:01.55,Sub,,0,0,0,,{\\fad(120,60)}IShowSpeed MOMENTS"
    with open(ass, "w", encoding="utf-8") as f:
        f.write("\n".join([hdr, ev1, ev2]) + "\n")
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    dur = hook.get("title_seconds", 1.6)
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", bg, "-i", who,
            "-map", "0:v", "-map", "1:a",
            "-vf", (f"scale=1080:1920:flags=lanczos,boxblur=22:2,eq=brightness=-0.22:contrast=1.08,"
                    f"subtitles='{ass_esc}'"),
            "-t", str(dur), "-r", str(config.FPS_OUT),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", "afade=t=in:st=0:d=0.08", out])
    return out

# ---------------- assembly ----------------
def assemble(clip_paths, out_file, hook, whoosh_at=None, music_profile=None):
    """Concat + timebase-normalize + BGM (sidechain-ducked under dialogue) + loudnorm.

    music_profile: music_trend block from research. If disabled, no music added.
    """
    lst = _p("concat_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
    merged = _p("merged.mp4")
    if os.path.exists(merged):
        os.remove(merged)
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", lst, "-c", "copy", merged])
    who, _boom = make_sfx()
    inputs = ["-i", merged]

    if music_profile and music_profile.get("enabled", True):
        bgm = musicgen.make_bgm(music_profile)
        if os.path.exists(bgm):
            inputs += ["-i", bgm]
            vol = float(music_profile.get("bed_volume", 0.42))
            dck_t = float(music_profile.get("duck_threshold", 0.06))
            dck_r = float(music_profile.get("duck_ratio", 10.0))
            fade_in = music_profile.get("fade_in_ms", 300)
            fade_out = music_profile.get("fade_out_ms", 600)
            # sidechaincompress: music is ducked while dialogue is loud
            chain = (f"[1:a]volume={vol}[mus];"
                     f"[mus][0:a]sidechaincompress=threshold={dck_t}:ratio={dck_r}:"
                     f"attack=40:release=300[duck];"
                     f"[duck]afade=t=in:st=0:d={fade_in/1000:.2f},afade=t=out:st=4:d={fade_out/1000:.2f}[musf];"
                     f"[0:a][musf]amix=inputs=2:duration=first:normalize=0,"
                     f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
            inputs += ["-filter_complex", chain]
        else:
            flt = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
            inputs += ["-filter_complex", flt]
    else:
        flt = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
        if whoosh_at:
            inputs += ["-i", who]
            delay = int(max(0, whoosh_at) * 1000)
            flt = (f"[1:a]adelay={delay}|{delay},volume=0.5[w];"
                   "[0:a][w]amix=inputs=2:duration=first:normalize=0,"
                   "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
        inputs += ["-filter_complex", flt]

    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + inputs +
           ["-map", "0:v", "-map", "[aout]",
            "-vf", "fps=30,settb=AVTB,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out_file])
    return out_file