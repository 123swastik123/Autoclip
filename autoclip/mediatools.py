"""FFmpeg / yt-dlp / whisper / face-analysis helpers (thin, composable)."""
import subprocess, sys, os, re
from .config import YTDLP_JS_RUNTIME

def run(cmd, allow_fail=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not allow_fail and r.returncode != 0:
        raise RuntimeError(f"CMD FAIL: {subprocess.list2cmdline(cmd)}\n{r.stderr[-3000:]}")
    return r

def ffprobe_dur(p):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None

def stream_info(p):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
             "-of", "json", p])
    return r.stdout

def prep_cut(src, t0, t1, out, crf=17, fps=None):
    pref = []
    if fps:
        pref = ["-r", str(fps)]
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", str(t0), "-to", str(t1), "-i", src,
         "-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-pix_fmt", "yuv420p"] + pref +
        ["-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000", out])
    return out

def extract_audio(src, out_wav, rate=16000):
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
         "-vn", "-ac", "1", "-ar", str(rate), out_wav])
    return out_wav

def silence_edges(path, noise_db=-35, d=0.45):
    """Return (head_sil, tail_sil, holes) or None for unknown."""
    r = run(["ffmpeg", "-hide_banner", "-i", path,
             "-af", f"silencedetect=noise={noise_db}dB:d={d}", "-f", "null", "NUL"],
            allow_fail=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", r.stderr)]
    if not starts:
        return None
    dur = ffprobe_dur(path) or 0
    sil = [(s, e if len(ends) > i else dur) for i, s in enumerate(starts)]
    head = sil[0][1] if sil and sil[0][0] < 0.6 else 0.0
    tail = (dur - sil[-1][0]) if sil and dur - sil[-1][1] < 0.4 else 0.0
    holes = [(s, e) for s, e in sil if 0.6 < s < (dur - 0.4) and (e - s) >= d]
    return {"head": max(0.0, head), "tail": max(0.0, tail), "holes": holes}

def whisper_words(wav, model="base.en", beam=1, language="en"):
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _info = m.transcribe(wav, beam_size=beam, language=language,
                               vad_filter=True, word_timestamps=True)
    words = []
    for s in segs:
        for w in (s.words or []):
            words.append({"start": w.start, "end": w.end, "text": w.word,
                          "energy": round(1.0 / (1.0 + max(0.01, w.end - w.start)), 3)})
    return words

def face_center(path, sample_step=1.0):
    """Return (avg_center_x_fraction, hit_rate, face_area_fraction) for a video."""
    track = face_track(path, sample_step)
    xs, areas = [], []
    for _t, x, area in track:
        if x is not None:
            xs.append(x); areas.append(area)
    n = len(track) or 1
    return (float(sum(xs)/len(xs)) if xs else 0.5,
            (len(xs) / n) if n else 0.0,
            (float(sum(areas)/len(areas)) if areas else 0.0))

def face_track(path, sample_step=1.0):
    """Sample creator-face x-fraction over time. Returns [(t, x, area)] for each sample
    (x None when no face). Useful for face-following crops on landscape footage."""
    import cv2
    det = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                             "haarcascade_frontalface_default.xml"))
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps * sample_step)))
    out, i = [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            faces = det.detectMultiScale(gray, 1.12, 5, minSize=(int(gray.shape[1]*0.06),)*2)
            if len(faces):
                x, y, fw, fh = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)[0]
                out.append((i / fps, (x + fw/2) / gray.shape[1], (fw * fh) / (gray.shape[0] * gray.shape[1])))
            else:
                out.append((i / fps, None, 0.0))
        i += 1
    cap.release()
    return out

# ---------------- yt-dlp (JS runtime required for full DASH formats) ----------------
def ytdlp(args):
    return run(["uv", "run", "--python", "3.12", "--with", "yt-dlp", "yt-dlp",
                "--no-warnings", f"--js-runtimes", YTDLP_JS_RUNTIME] + args)

def list_formats(video_id):
    r = ytdlp(["-F", f"https://www.youtube.com/watch?v={video_id}"])
    return r.stdout

def download_section(video_id, t0, t1, out, height=720):
    fmt = "bv*[height<=%d]+ba/b" % height
    r = ytdlp(["-f", fmt, f"--download-sections", f"*{int(t0)}-{int(t1)}",
               "--merge-output-format", "mp4", "-o", out,
               f"https://www.youtube.com/watch?v={video_id}"])
    return out, r.returncode == 0

def download_captions(video_id, output_base):
    r = ytdlp(["--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*",
               "--sub-format", "vtt", "-o", output_base,
               f"https://www.youtube.com/watch?v={video_id}"])
    return r.returncode == 0