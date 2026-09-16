"""Central configuration. Paths are project-scoped; media is always gitignored."""
import os

# Media/cache lives outside the repo by default so nothing heavy is ever committed.
DEFAULT_MEDIA_DIR = os.path.join(os.environ.get("TEMP", "."), "opencode", "autoclip")

def media_dir():
    return os.environ.get("AUTOCLIP_MEDIA", DEFAULT_MEDIA_DIR)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
RESEARCH = os.path.join(DATA, "research")
STATE = os.path.join(DATA, "state")
TEMPLATES = os.path.join(PROJECT, "templates")
DOCS = os.path.join(PROJECT, "docs")

FPS_OUT = 30
W_OUT, H_OUT = 1080, 1920

# YouTube section download needs the node runtime to solve signatures (PO tokens).
YTDLP_JS_RUNTIME = "node"

PYTHON = "python"