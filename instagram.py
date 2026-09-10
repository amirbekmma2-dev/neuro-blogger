from __future__ import annotations

import logging
import threading
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired

import config
from config import SESSION_FILE, reload_env

logger = logging.getLogger(__name__)

_code_event = threading.Event()
_code_value = ""
waiting_for_code = False
code_prompt = ""


class InstagramError(RuntimeError):
    pass


def submit_code(code: str) -> None:
    global _code_value, waiting_for_code
    _code_value = code.strip()
    waiting_for_code = False
    _code_event.set()


def _wait_code(prompt: str, timeout: int = 300) -> str:
    global waiting_for_code, code_prompt, _code_value
    waiting_for_code = True
    code_prompt = prompt
    _code_value = ""
    _code_event.clear()
    logger.info("waiting instagram code: %s", prompt)
    ok = _code_event.wait(timeout=timeout)
    waiting_for_code = False
    if not ok or not _code_value:
        raise InstagramError("Код Instagram не пришёл за 5 минут")
    return _code_value


def _challenge_handler(username: str, choice) -> str:
    kind = "почты" if str(choice) in {"0", "ChoiceEmail", "email"} else "телефона"
    return _wait_code(f"Instagram просит код с {kind} для @{username}. Пришли цифры сюда.")


def get_client() -> Client:
    reload_env()
    user = config.IG_USERNAME
    password = config.IG_PASSWORD
    if not user or not password:
        raise InstagramError("Нет IG_USERNAME / IG_PASSWORD")
    cl = Client()
    cl.delay_range = [1, 3]
    cl.set_locale("en_US")
    cl.set_timezone_offset(5 * 3600)
    cl.challenge_code_handler = _challenge_handler

    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            sid = (cl.sessionid or "").strip() or (cl.settings.get("authorization_data") or {}).get("sessionid")
            if sid:
                cl.login_by_sessionid(sid)
            else:
                cl.login(user, password)
            cl.get_timeline_feed()
            logger.info("instagram session ok")
            return cl
        except Exception as exc:
            logger.warning("session failed (%s), fresh login", exc)

    try:
        cl.login(user, password)
    except TwoFactorRequired:
        code = _wait_code("Instagram 2FA. Пришли код из приложения/SMS.")
        cl.login(user, password, verification_code=code)
    except ChallengeRequired:
        code = _wait_code("Instagram challenge. Пришли код с почты.")
        try:
            cl.challenge_resolve(auto=False)
        except Exception:
            cl.login(user, password, verification_code=code)

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(SESSION_FILE)
    logger.info("instagram logged in, session saved")
    return cl


def post_reel(video_path: Path, caption: str) -> str:
    if not video_path.exists():
        raise InstagramError(f"Нет файла {video_path}")
    cl = get_client()
    media = cl.clip_upload(str(video_path), caption=caption)
    media_id = getattr(media, "id", None) or getattr(media, "pk", None) or str(media)
    logger.info("reel posted %s", media_id)
    return str(media_id)


def account_info() -> dict:
    cl = get_client()
    info = cl.account_info()
    return {
        "username": info.username,
        "full_name": info.full_name,
        "biography": getattr(info, "biography", "") or "",
        "media_count": info.media_count,
        "follower_count": getattr(info, "follower_count", None),
        "following_count": getattr(info, "following_count", None),
        "is_private": getattr(info, "is_private", None),
    }


PROFESSIONAL_NAME = "Motiv | Vaqt sayohati"
PROFESSIONAL_BIO = (
    "Vaqt mashinasi · AI sayohatchi\n"
    "O'tmish va kelajak • har kuni 8 Reel\n"
    "Yunoniston · Misr · SSSR · 2100\n"
    "📍 Toshkent"
)


def polish_profile(avatar: Path | None = None) -> list[str]:
    """Make the account public creator, set name/bio/avatar. Idempotent."""
    cl = get_client()
    notes: list[str] = []
    try:
        cl.account_set_public()
        notes.append("public")
    except Exception as exc:
        notes.append(f"public skip: {exc}")
        logger.warning("account_set_public: %s", exc)

    try:
        cl.account_convert_to_creator(should_show_category=True)
        notes.append("creator")
    except Exception as exc:
        notes.append(f"creator skip: {exc}")
        logger.warning("convert_to_creator: %s", exc)

    info = cl.account_info()
    old_bio = getattr(info, "biography", "") or ""
    old_name = getattr(info, "full_name", "") or ""
    if old_name != PROFESSIONAL_NAME or "Vaqt mashinasi" not in old_bio:
        try:
            cl.account_edit(full_name=PROFESSIONAL_NAME, biography=PROFESSIONAL_BIO)
            notes.append("bio")
        except Exception as exc:
            notes.append(f"bio skip: {exc}")
            logger.warning("account_edit: %s", exc)
    else:
        notes.append("bio ok")

    first_time = "Vaqt mashinasi" not in old_bio
    if first_time and avatar and Path(avatar).exists() and Path(avatar).stat().st_size > 1000:
        try:
            cl.account_change_picture(Path(avatar))
            notes.append("avatar")
        except Exception as exc:
            notes.append(f"avatar skip: {exc}")
            logger.warning("account_change_picture: %s", exc)
    return notes


def fetch_video_insights(limit: int = 24) -> list[dict]:
    cl = get_client()
    return cl.insights_media_feed_all(
        post_type="VIDEO",
        time_frame="THREE_MONTHS",
        data_ordering="VIDEO_VIEW_COUNT",
        count=limit,
        sleep=1,
    )
