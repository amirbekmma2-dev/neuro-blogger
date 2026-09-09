import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
VIDEO_DIR = DATA_DIR / "videos"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "neuro.db"
SESSION_FILE = DATA_DIR / "ig_session.json"
PERSONA_FILE = DATA_DIR / "persona.json"
CHARACTER_FILE = DATA_DIR / "character.jpg"
ENV_FILE = BASE_DIR / ".env"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_USER_IDS = {
    int(x) for x in os.getenv("ADMIN_USER_IDS", "1342016402").split(",") if x.strip().isdigit()
}

XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
XAI_BASE = "https://api.x.ai/v1"
LLM_MODEL = os.getenv("LLM_MODEL", "grok-4.6").strip()
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "grok-imagine-image-2.0").strip()
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "grok-imagine-video-1.5").strip()
VIDEO_DURATION = 15
VIDEO_RESOLUTION = os.getenv("VIDEO_RESOLUTION", "480p").strip()
VIDEO_ASPECT = "9:16"
VOICE_ID = os.getenv("VOICE_ID", "rex").strip()
AUTO_POST = os.getenv("AUTO_POST", "1").strip() not in {"0", "false", "no"}
AUTO_INTERVAL_MINUTES = int(os.getenv("AUTO_INTERVAL_MINUTES", "120"))
POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "8"))

IG_USERNAME = os.getenv("IG_USERNAME", "").strip()
IG_PASSWORD = os.getenv("IG_PASSWORD", "").strip()

WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "10000")


def reload_env() -> None:
    load_dotenv(ENV_FILE, override=True)
    global BOT_TOKEN, ADMIN_USER_IDS, XAI_API_KEY, LLM_MODEL, IMAGE_MODEL
    global VIDEO_MODEL, VIDEO_DURATION, VIDEO_RESOLUTION, VOICE_ID
    global AUTO_POST, AUTO_INTERVAL_MINUTES, POSTS_PER_DAY
    global IG_USERNAME, IG_PASSWORD, WEBHOOK_URL, WEBHOOK_PATH, WEBAPP_HOST, WEBAPP_PORT
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
    ADMIN_USER_IDS = {
        int(x) for x in os.getenv("ADMIN_USER_IDS", "1342016402").split(",") if x.strip().isdigit()
    }
    XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
    LLM_MODEL = os.getenv("LLM_MODEL", "grok-4.6").strip()
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "grok-imagine-image-2.0").strip()
    VIDEO_MODEL = os.getenv("VIDEO_MODEL", "grok-imagine-video-1.5").strip()
    VIDEO_DURATION = 15
    VIDEO_RESOLUTION = os.getenv("VIDEO_RESOLUTION", "480p").strip()
    VOICE_ID = os.getenv("VOICE_ID", "rex").strip()
    AUTO_POST = os.getenv("AUTO_POST", "1").strip() not in {"0", "false", "no"}
    AUTO_INTERVAL_MINUTES = int(os.getenv("AUTO_INTERVAL_MINUTES", "120"))
    POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "8"))
    IG_USERNAME = os.getenv("IG_USERNAME", "").strip()
    IG_PASSWORD = os.getenv("IG_PASSWORD", "").strip()
    WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
    WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
    WEBAPP_PORT = int(os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "10000")


def upsert_env(key: str, value: str) -> None:
    ENV_FILE.touch(exist_ok=True)
    os.chmod(ENV_FILE, 0o600)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    os.environ[key] = value
    reload_env()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def missing_setup() -> list[str]:
    reload_env()
    from grok_auth import grok_ready

    gaps = []
    if not BOT_TOKEN:
        gaps.append("BOT_TOKEN")
    if not grok_ready():
        gaps.append("Grok")
    if not IG_USERNAME or not IG_PASSWORD:
        gaps.append("Instagram")
    return gaps
