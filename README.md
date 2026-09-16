# AutoClip

Research-first YouTube Short generator. Turns a creator + brief into a trend-aware,
professionally edited 9:16 short with karaoke captions, countdown presentation,
punch-ins, SFX, and a two-gate QA (technical + creative).

**Never uploads anything.** The pipeline stops at preview/QA; publishing only happens
after explicit user approval.

## Pipeline

```
USER REQUEST
  -> intent + FORMAT detection            (autoclip/request.py)
  -> viral/trend RESEARCH                 (research notes -> data/research/builder.json)
  -> FORMAT/pattern analysis              (autoclip/format.py)
  -> creator viral research               (notes in builder.json)
  -> source discovery                     (agent + yt-dlp)
  -> moment candidate extraction          (whisper scan + verification)
  -> scoring + ranking + selection        (autoclip/candidates.py)
  -> targeted section downloads           (autoclip/mediatools.py)
  -> 9:16 edit: reframe/punch/cards       (autoclip/edit.py)
  -> karaoke captions                     (autoclip/captions.py)
  -> TECHNICAL + CREATIVE QA              (autoclip/qa.py)
  -> preview -> USER APPROVAL
  -> upload ONLY on explicit "upload"
```

Research happens **before** expensive downloads; only needed sections are downloaded.
The video style is driven by current research, never one hardcoded "best" look.

## CLI

```
autoclip parse "<creator - Top 5 ...>"     # intent/format/topic detection
autoclip research                          # print/save trend research report
autoclip transcribe clip.mp4 words.json    # word-timestamps for a cut clip
autoclip run manifest.json --out out.mp4   # render + technical QA
autoclip qa file.mp4                       # run both QA gates
```

## Running (Windows, no global deps)

```
uv run --python 3.12 --with faster-whisper --with "opencv-python<5" --with yt-dlp -- python -m autoclip.cli <cmd>
```

Media/cache is kept outside the repo (gitignored); only code + research notes are
committed. Secrets never enter the repo.

## Rules of the road

- Creator is always the primary visual focus (face-follow reframing).
- Moments are verified against real footage/transcription; timestamps are never invented.
- Creative QA and technical QA are separate gates; both must pass before "ready".
- Format/countdown presentation must match the brief (e.g. a real #5..#1 countdown).