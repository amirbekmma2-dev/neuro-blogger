from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from config import CHARACTER_FILE, VIDEO_DURATION, VIDEO_RESOLUTION, VOICE_ID
from db import create_post, get_post, update_post
from grok_api import (
    GrokError,
    ensure_character,
    generate_video,
    invent_script,
    next_video_path,
)
from instagram import InstagramError, post_reel, waiting_for_code
from keyboards import preview_kb
from media import prepare_reel
from persona import load_persona

logger = logging.getLogger(__name__)

_busy = asyncio.Lock()


def is_busy() -> bool:
    return _busy.locked()


async def run_generation(bot: Bot, chat_id: int, topic: str | None = None) -> None:
    if _busy.locked():
        await bot.send_message(chat_id, "Уже генерирую другой ролик. Дождись.")
        return
    async with _busy:
        post_id = await create_post(topic, "generating")
        try:
            await bot.send_message(chat_id, f"#{post_id} 1/4 сценарий…")
            script = await invent_script(topic)
            await update_post(
                post_id,
                idea=script["idea"],
                hook=script["hook"],
                video_prompt=script["video_prompt"],
                caption=script["caption"],
            )

            await bot.send_message(chat_id, f"#{post_id} 2/4 лицо персонажа…")
            face = await ensure_character()

            await bot.send_message(
                chat_id,
                f"#{post_id} 3/4 видео в Grok Imagine ({VIDEO_RESOLUTION}, {VIDEO_DURATION}с). Минуты.",
            )
            raw_path = next_video_path(post_id)
            p = load_persona()
            voice = p.get("voice_id") or VOICE_ID
            await generate_video(
                script["video_prompt"],
                raw_path,
                reference_image=face,
                voice_id=voice,
            )

            await bot.send_message(chat_id, f"#{post_id} 4/4 сборка Reels…")
            reel = await asyncio.to_thread(prepare_reel, raw_path)
            await update_post(post_id, video_path=str(reel), status="ready")

            caption = (
                f"#{post_id} {script['idea']}\n\n"
                f"{script['caption']}\n\n"
                f"Жми ✅ только если ролик ок. Сам в ленту не уйдёт."
            )
            await bot.send_video(
                chat_id,
                video=FSInputFile(reel),
                caption=caption[:1024],
                reply_markup=preview_kb(post_id),
            )
        except GrokError as exc:
            logger.exception("generation grok")
            await update_post(post_id, status="failed", error=str(exc))
            await bot.send_message(chat_id, f"#{post_id} Grok не смог:\n{exc}")
        except Exception as exc:
            logger.exception("generation failed")
            await update_post(post_id, status="failed", error=str(exc))
            await bot.send_message(chat_id, f"#{post_id} ошибка:\n{exc}")


async def publish_post(bot: Bot, chat_id: int, post_id: int) -> None:
    post = await get_post(post_id)
    if not post:
        await bot.send_message(chat_id, "Пост не найден")
        return
    if post["status"] == "posted":
        await bot.send_message(chat_id, "Этот уже опубликован")
        return
    path = Path(post["video_path"] or "")
    if not path.exists():
        await bot.send_message(chat_id, "Файл видео пропал, сгенерируй заново")
        return
    await bot.send_message(chat_id, f"#{post_id} публикую в Instagram…")
    try:
        media_id = await asyncio.to_thread(post_reel, path, post["caption"] or "")
        await update_post(post_id, status="posted", ig_media_id=media_id)
        handle = load_persona().get("ig_handle") or ""
        link = f"https://www.instagram.com/{handle}/" if handle else ""
        await bot.send_message(
            chat_id,
            f"#{post_id} выложено.\nMedia ID: {media_id}\n{link}",
        )
    except InstagramError as exc:
        await update_post(post_id, error=str(exc))
        extra = ""
        if waiting_for_code:
            extra = "\nПришли код из письма/приложения ответом."
        await bot.send_message(chat_id, f"Instagram: {exc}{extra}")
    except Exception as exc:
        logger.exception("publish failed")
        await update_post(post_id, error=str(exc))
        await bot.send_message(chat_id, f"Публикация упала:\n{exc}")


async def regenerate_video(bot: Bot, chat_id: int, post_id: int) -> None:
    post = await get_post(post_id)
    if not post:
        await bot.send_message(chat_id, "Пост не найден")
        return
    if _busy.locked():
        await bot.send_message(chat_id, "Уже занят другим роликом")
        return
    async with _busy:
        try:
            await update_post(post_id, status="generating")
            await bot.send_message(chat_id, f"#{post_id} новое видео по тому же сценарию…")
            face = CHARACTER_FILE if CHARACTER_FILE.exists() else await ensure_character()
            raw_path = next_video_path(post_id)
            p = load_persona()
            await generate_video(
                post["video_prompt"] or "",
                raw_path,
                reference_image=face,
                voice_id=p.get("voice_id") or VOICE_ID,
            )
            reel = await asyncio.to_thread(prepare_reel, raw_path)
            await update_post(post_id, video_path=str(reel), status="ready")
            await bot.send_video(
                chat_id,
                video=FSInputFile(reel),
                caption=f"#{post_id} новый дубль\n\n{post['caption']}",
                reply_markup=preview_kb(post_id),
            )
        except Exception as exc:
            logger.exception("regen failed")
            await update_post(post_id, status="failed", error=str(exc))
            await bot.send_message(chat_id, f"#{post_id} реген не вышел:\n{exc}")
