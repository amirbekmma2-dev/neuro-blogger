from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

from aiogram import Bot

import config
from db import counts
from pipeline import is_busy, run_generation

logger = logging.getLogger(__name__)


def _admin_chat() -> int:
    return next(iter(config.ADMIN_USER_IDS))


async def auto_loop(bot: Bot) -> None:
    await asyncio.sleep(40)
    chat = _admin_chat()
    logger.info(
        "auto loop on: every %s min, max %s/day, 15s uzbek",
        config.AUTO_INTERVAL_MINUTES,
        config.POSTS_PER_DAY,
    )
    try:
        await bot.send_message(
            chat,
            "Avtopilot yoqildi: 15s o'zbek reels, o'zi yozadi va Instagramga chiqaradi. "
            f"Kuniga {config.POSTS_PER_DAY} ta, ~{config.AUTO_INTERVAL_MINUTES} daqiqada bir.",
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
                await asyncio.sleep(30 * 60)
                continue
            if is_busy():
                await asyncio.sleep(20)
                continue
            logger.info("auto cycle %s", datetime.now(timezone.utc).isoformat())
            await run_generation(bot, chat, None, auto_publish=True)
        except Exception:
            logger.exception("auto cycle failed")
            try:
                await bot.send_message(chat, "Avtopilot xato. 10 daqiqadan keyin yana.")
            except Exception:
                pass
            await asyncio.sleep(10 * 60)
            continue
        jitter = random.randint(-15, 20)
        wait = max(45, config.AUTO_INTERVAL_MINUTES + jitter) * 60
        logger.info("auto sleep %ss", wait)
        await asyncio.sleep(wait)
