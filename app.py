from __future__ import annotations

import asyncio
import logging
import sys

from aiohttp import web
from aiogram.types import Update

import config
from bot import bot, dp, setup_dispatcher
from config import BOT_TOKEN, reload_env
from db import init_db

logger = logging.getLogger("neuro")


async def health_handler(_request: web.Request) -> web.Response:
    payload = {"ok": True, "auto_post": bool(config.AUTO_POST)}
    try:
        from db import counts, next_ready_post
        from pipeline import is_busy
        from schedule import next_slot, now_tashkent, prep_slot

        now = now_tashkent()
        nxt = next_slot()
        lead = int(getattr(config, "PREP_MINUTES", 30) or 30)
        prep = prep_slot(lead_min=lead)
        ready = await next_ready_post()
        stats = await counts()
        payload.update(
            {
                "busy": is_busy(),
                "now": now.strftime("%Y-%m-%d %H:%M"),
                "prep": prep.strftime("%H:%M") if prep else None,
                "next": nxt.strftime("%H:%M"),
                "ready": ready.get("id") if ready else None,
                "posted_today": stats.get("posted_today", 0),
                "per_day": config.POSTS_PER_DAY,
            }
        )
    except Exception as exc:
        payload["err"] = str(exc)
    return web.json_response(payload)


async def webhook_handler(request: web.Request) -> web.Response:
    data = await request.json()
    upd = Update.model_validate(data)
    asyncio.get_running_loop().create_task(_process_update(upd))
    return web.Response(status=200)


async def _process_update(upd: Update) -> None:
    try:
        await dp.feed_update(bot, upd)
    except Exception:
        logger.exception("update %s", getattr(upd, "update_id", None))


async def on_startup(_app: web.Application) -> None:
    reload_env()
    await init_db()
    setup_dispatcher()
    base = (config.WEBHOOK_URL or "").rstrip("/")
    url = base + config.WEBHOOK_PATH
    await bot.set_webhook(url=url, allowed_updates=dp.resolve_used_update_types())
    logger.info("webhook set %s", url)
    if config.AUTO_POST:
        from worker import auto_loop

        asyncio.create_task(auto_loop(bot))
        logger.info("auto-pilot started")


async def on_cleanup(_app: web.Application) -> None:
    await bot.session.close()
    logger.info("shutdown, webhook left in place")


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)
    app.router.add_post(config.WEBHOOK_PATH, webhook_handler)
    return app


def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN пустой")
        sys.exit(1)
    reload_env()
    if not config.WEBHOOK_URL:
        logger.warning("WEBHOOK_URL пуст — polling")
        from bot import main as polling_main

        asyncio.run(polling_main())
        return
    logger.info("webhook server %s:%s", config.WEBAPP_HOST, config.WEBAPP_PORT)
    web.run_app(create_app(), host=config.WEBAPP_HOST, port=config.WEBAPP_PORT)


if __name__ == "__main__":
    main()
