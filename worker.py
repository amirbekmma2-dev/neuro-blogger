from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

import config
from db import counts, kv_get, kv_set
from pipeline import is_busy, run_generation
from schedule import (
    TASHKENT,
    due_slot,
    format_slots,
    hours_from_insights,
    next_slot,
    now_tashkent,
    parse_slots,
    slots_to_str,
)

logger = logging.getLogger(__name__)


def _admin_chat() -> int:
    return next(iter(config.ADMIN_USER_IDS))


async def _learned_slots() -> list[tuple[int, int]] | None:
    raw = await kv_get("learned_slots")
    slots = parse_slots(raw)
    return slots or None


async def _refresh_algorithm() -> list[tuple[int, int]] | None:
    last = await kv_get("learned_at")
    now = now_tashkent()
    if last:
        try:
            prev = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - prev).total_seconds() < 20 * 3600:
                return await _learned_slots()
        except ValueError:
            pass
    try:
        from instagram import fetch_video_insights

        rows = await asyncio.to_thread(fetch_video_insights, 24)
        learned = hours_from_insights(rows)
        if learned:
            await kv_set("learned_slots", slots_to_str(learned))
            await kv_set("learned_at", now.isoformat())
            return learned
    except Exception:
        logger.exception("insights learn failed — keep research slots")
    await kv_set("learned_at", now.isoformat())
    return await _learned_slots()


async def _sleep_until(when) -> None:
    while True:
        config.reload_env()
        if not config.AUTO_POST:
            return
        remain = (when - datetime.now(timezone.utc)).total_seconds()
        if remain <= 0:
            return
        await asyncio.sleep(min(30, max(1, remain)))


async def _polish_once(bot: Bot, chat: int) -> None:
    if await kv_get("profile_polished") == "1":
        return
    try:
        from grok_api import ensure_character
        from instagram import polish_profile

        face = await ensure_character()
        notes = await asyncio.to_thread(polish_profile, face)
        await kv_set("profile_polished", "1")
        await bot.send_message(chat, "Profil professional:\n" + ", ".join(notes))
        logger.info("profile polished: %s", notes)
    except Exception as exc:
        logger.exception("polish profile")
        try:
            await bot.send_message(chat, f"Profil: {exc}")
        except Exception:
            pass


async def auto_loop(bot: Bot) -> None:
    await asyncio.sleep(40)
    chat = _admin_chat()
    await _polish_once(bot, chat)
    learned = await _refresh_algorithm()
    nxt = next_slot(learned=learned)
    logger.info(
        "auto loop on: %s/day, next %s Tashkent, slots %s",
        config.POSTS_PER_DAY,
        nxt.astimezone(TASHKENT).strftime("%H:%M"),
        format_slots(learned) if learned else "research-default",
    )
    try:
        slot_txt = format_slots(learned) if learned else "07:40 09:10 12:20 14:40 17:20 19:00 20:30 22:10"
        await bot.send_message(
            chat,
            "Avtopilot yoqildi: 30s o'zbek sayohat, professional akaunt.\n"
            f"Toshkent peak: {slot_txt}\n"
            f"Keyingi post: {nxt.astimezone(TASHKENT).strftime('%d.%m %H:%M')} (Toshkent)\n"
            f"Kuniga {config.POSTS_PER_DAY} ta. Tunda yozmaydi.",
        )
    except Exception:
        logger.exception("auto hello")

    while True:
        try:
            config.reload_env()
            if not config.AUTO_POST:
                await asyncio.sleep(30)
                continue
            stats = await counts()
            if stats.get("posted_today", 0) >= config.POSTS_PER_DAY:
                logger.info("daily cap reached")
                learned = await _refresh_algorithm()
                end = now_tashkent().replace(hour=23, minute=59, second=0, microsecond=0)
                tomorrow = next_slot(learned=learned, after=end)
                await _sleep_until(tomorrow.astimezone(timezone.utc))
                continue
            if is_busy():
                await asyncio.sleep(20)
                continue
            learned = await _learned_slots()
            due = due_slot(learned=learned)
            if due is None:
                nxt = next_slot(learned=learned)
                logger.info("sleep until peak %s", nxt.isoformat())
                await _sleep_until(nxt.astimezone(timezone.utc))
                continue
            logger.info("auto cycle peak %s", due.isoformat())
            await run_generation(bot, chat, None, auto_publish=True)
        except Exception:
            logger.exception("auto cycle failed")
            try:
                await bot.send_message(chat, "Avtopilot xato. 10 daqiqadan keyin yana.")
            except Exception:
                pass
            await asyncio.sleep(10 * 60)
            continue
        await asyncio.sleep(90)
