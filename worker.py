from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

import config
from db import counts, kv_get, kv_set, next_ready_post, slot_already_handled
from pipeline import is_busy, publish_post, run_generation
from schedule import (
    TASHKENT,
    format_slots,
    late_slot,
    hours_from_insights,
    next_slot,
    now_tashkent,
    parse_slots,
    prep_slot,
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
    await asyncio.sleep(8)
    chat = _admin_chat()
    # Never block posting on IG polish / 2FA / insights.
    asyncio.create_task(_polish_once(bot, chat))
    asyncio.create_task(_refresh_algorithm())
    learned = await _learned_slots()
    due = due_slot(learned=learned)
    nxt = due or next_slot(learned=learned)
    lead = int(getattr(config, "PREP_MINUTES", 30) or 30)
    logger.info(
        "auto loop on: %s/day, prep -%s min, next %s Tashkent",
        config.POSTS_PER_DAY,
        lead,
        nxt.astimezone(TASHKENT).strftime("%H:%M"),
    )
    try:
        slot_txt = format_slots(learned) if learned else "07:40 09:10 12:20 14:40 17:20 19:00 20:30 22:00"
        await bot.send_message(
            chat,
            "Avtopilot 24/7: 8 ta 30s 9:16 sayohat Reel/kun.\n"
            f"Toshkent: {slot_txt}\n"
            f"Video slotdan {lead} daqiqa oldin tayyor, chiqish aniq vaqtda.\n"
            f"Keyingi: {nxt.astimezone(TASHKENT).strftime('%d.%m %H:%M')}",
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
            lead = int(getattr(config, "PREP_MINUTES", 30) or 30)
            if stats.get("posted_today", 0) >= config.POSTS_PER_DAY:
                logger.info("daily cap reached")
                learned = await _refresh_algorithm()
                end = now_tashkent().replace(hour=23, minute=59, second=0, microsecond=0)
                tomorrow = next_slot(learned=learned, after=end)
                prep_at = tomorrow - timedelta(minutes=lead)
                await _sleep_until(prep_at.astimezone(timezone.utc))
                continue
            if is_busy():
                await asyncio.sleep(20)
                continue
            learned = await _learned_slots()
            now = now_tashkent()

            ready = await next_ready_post()
            if ready and ready.get("scheduled_for"):
                try:
                    slot = datetime.fromisoformat(str(ready["scheduled_for"]).replace("Z", "+00:00"))
                    if slot.tzinfo is None:
                        slot = slot.replace(tzinfo=TASHKENT)
                    slot = slot.astimezone(TASHKENT)
                except ValueError:
                    slot = now
                if now < slot:
                    logger.info("ready #%s, wait until %s", ready["id"], slot.isoformat())
                    await _sleep_until(slot.astimezone(timezone.utc))
                    continue
                logger.info("publish #%s slot %s", ready["id"], slot.strftime("%H:%M"))
                await publish_post(bot, chat, int(ready["id"]))
                await asyncio.sleep(5)
                continue

            late = late_slot(learned=learned, now=now, grace_min=45)
            if late is not None and not await slot_already_handled(late.isoformat()):
                logger.info("late catch-up %s", late.strftime("%H:%M"))
                await run_generation(
                    bot,
                    chat,
                    None,
                    auto_publish=True,
                    scheduled_for=late.isoformat(),
                )
                await asyncio.sleep(5)
                continue

            prep = prep_slot(learned=learned, now=now, lead_min=lead)
            if prep is not None:
                key = prep.isoformat()
                if await slot_already_handled(key):
                    logger.info("prep slot %s already has reel, wait publish", prep.strftime("%H:%M"))
                    await _sleep_until(prep.astimezone(timezone.utc))
                    continue
                logger.info("prep %s (post at %s)", now.strftime("%H:%M"), prep.strftime("%H:%M"))
                await run_generation(
                    bot, chat, None, auto_publish=False, scheduled_for=key
                )
                await asyncio.sleep(5)
                continue

            nxt = next_slot(learned=learned, after=now)
            prep_at = nxt - timedelta(minutes=lead)
            logger.info("sleep until prep %s for slot %s", prep_at.isoformat(), nxt.strftime("%H:%M"))
            await _sleep_until(prep_at.astimezone(timezone.utc))
        except Exception:
            logger.exception("auto cycle failed")
            try:
                await bot.send_message(chat, "Avtopilot xato. 10 daqiqadan keyin yana.")
            except Exception:
                pass
            await asyncio.sleep(10 * 60)
