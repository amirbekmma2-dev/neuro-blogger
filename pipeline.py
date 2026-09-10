from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from config import AUTO_POST, CHARACTER_FILE, VIDEO_RESOLUTION, VIDEO_TOTAL_DURATION, VOICE_ID
from db import create_post, get_post, list_posts, update_post
from grok_api import (
    GrokError,
    ensure_character,
    generate_thirty_second_video,
    invent_script,
    next_video_path,
    parse_beats,
)
from instagram import InstagramError, post_reel, waiting_for_code
from keyboards import preview_kb
from media import prepare_reel
from persona import load_persona

logger = logging.getLogger(__name__)

_busy = asyncio.Lock()


def is_busy() -> bool:
    return _busy.locked()


async def _recent_ideas() -> list[str]:
    rows = await list_posts(16)
    out = []
    for p in rows:
        if p.get("idea"):
            out.append(p["idea"])
    return out


async def run_generation(
    bot: Bot,
    chat_id: int,
    topic: str | None = None,
    *,
    auto_publish: bool | None = None,
) -> int | None:
    publish = AUTO_POST if auto_publish is None else auto_publish
    if _busy.locked():
        await bot.send_message(chat_id, "Allaqachon boshqa reel yasayapman.")
        return None
    async with _busy:
        post_id = await create_post(topic, "generating")
        try:
            await bot.send_message(chat_id, f"#{post_id} {VIDEO_TOTAL_DURATION}s sayohat reel: ssenariy…")
            script = await invent_script(topic, avoid=await _recent_ideas())
            await update_post(
                post_id,
                idea=script["idea"],
                hook=script["hook"],
                video_prompt=script["video_prompt"],
                caption=script["caption"],
            )

            await bot.send_message(chat_id, f"#{post_id} yuz…")
            face = await ensure_character()

            await bot.send_message(
                chat_id,
                f"#{post_id} Grok 3×10s = {VIDEO_TOTAL_DURATION}s {VIDEO_RESOLUTION}, yuz qulflangan. Bir necha daqiqa.",
            )
            raw_path = next_video_path(post_id)
            p = load_persona()
            await generate_thirty_second_video(
                parse_beats(script["video_prompt"]),
                raw_path,
                reference_image=face,
                voice_id=p.get("voice_id") or VOICE_ID,
            )

            await bot.send_message(chat_id, f"#{post_id} Reels yig'ish…")
            reel = await asyncio.to_thread(prepare_reel, raw_path)
            await update_post(post_id, video_path=str(reel), status="ready")

            note = script["caption"]
            extra = "Avtonom: hozir Instagramga chiqaman." if publish else "Tekshirib ✅ bos."
            await bot.send_video(
                chat_id,
                video=FSInputFile(reel),
                caption=f"#{post_id} {script['idea']}\n\n{note}\n\n{extra}"[:1024],
                reply_markup=None if publish else preview_kb(post_id),
            )
            if publish:
                await _publish(bot, chat_id, post_id)
            return post_id
        except GrokError as exc:
            logger.exception("generation grok")
            await update_post(post_id, status="failed", error=str(exc))
            await bot.send_message(chat_id, f"#{post_id} Grok:\n{exc}")
        except Exception as exc:
            logger.exception("generation failed")
            await update_post(post_id, status="failed", error=str(exc))
            await bot.send_message(chat_id, f"#{post_id} xato:\n{exc}")
        return post_id


async def _publish(bot: Bot, chat_id: int, post_id: int) -> None:
    post = await get_post(post_id)
    if not post:
        return
    path = Path(post["video_path"] or "")
    if not path.exists():
        await bot.send_message(chat_id, f"#{post_id} fayl yo'q")
        return
    await bot.send_message(chat_id, f"#{post_id} Instagramga chiqyapti…")
    try:
        media_id = await asyncio.to_thread(post_reel, path, post["caption"] or "")
        await update_post(post_id, status="posted", ig_media_id=media_id)
        handle = load_persona().get("ig_handle") or ""
        link = f"https://www.instagram.com/{handle}/" if handle else ""
        await bot.send_message(chat_id, f"#{post_id} chiqdi.\n{media_id}\n{link}")
    except InstagramError as exc:
        await update_post(post_id, error=str(exc))
        extra = "\nInstagram kod so'radi — shu yerga yoz." if waiting_for_code else ""
        await bot.send_message(chat_id, f"Instagram: {exc}{extra}")
    except Exception as exc:
        logger.exception("publish failed")
        await update_post(post_id, error=str(exc))
        await bot.send_message(chat_id, f"#{post_id} post xato:\n{exc}")


async def publish_post(bot: Bot, chat_id: int, post_id: int) -> None:
    post = await get_post(post_id)
    if not post:
        await bot.send_message(chat_id, "Post topilmadi")
        return
    if post["status"] == "posted":
        await bot.send_message(chat_id, "Bu allaqachon chiqqan")
        return
    await _publish(bot, chat_id, post_id)


async def regenerate_video(bot: Bot, chat_id: int, post_id: int) -> None:
    post = await get_post(post_id)
    if not post:
        await bot.send_message(chat_id, "Post topilmadi")
        return
    if _busy.locked():
        await bot.send_message(chat_id, "Bandman")
        return
    async with _busy:
        try:
            await update_post(post_id, status="generating")
            await bot.send_message(chat_id, f"#{post_id} yangi {VIDEO_TOTAL_DURATION}s dublyaj…")
            face = CHARACTER_FILE if CHARACTER_FILE.exists() else await ensure_character()
            raw_path = next_video_path(post_id)
            p = load_persona()
            await generate_thirty_second_video(
                parse_beats(post["video_prompt"] or ""),
                raw_path,
                reference_image=face,
                voice_id=p.get("voice_id") or VOICE_ID,
            )
            reel = await asyncio.to_thread(prepare_reel, raw_path)
            await update_post(post_id, video_path=str(reel), status="ready")
            await bot.send_video(
                chat_id,
                video=FSInputFile(reel),
                caption=f"#{post_id} yangi dublyaj\n\n{post['caption']}",
                reply_markup=None if AUTO_POST else preview_kb(post_id),
            )
            if AUTO_POST:
                await _publish(bot, chat_id, post_id)
        except Exception as exc:
            logger.exception("regen failed")
            await update_post(post_id, status="failed", error=str(exc))
            await bot.send_message(chat_id, f"#{post_id} regen xato:\n{exc}")
