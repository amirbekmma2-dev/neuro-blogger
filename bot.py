from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message, TelegramObject

import config
from config import (
    ADMIN_USER_IDS,
    BOT_TOKEN,
    CHARACTER_FILE,
    IG_PASSWORD,
    IG_USERNAME,
    VIDEO_RESOLUTION,
    XAI_API_KEY,
    ensure_dirs,
    missing_setup,
    reload_env,
    upsert_env,
)
from grok_auth import grok_ready
from db import counts, get_post, init_db, list_posts, update_post
from grok_api import GrokError, ensure_character
from instagram import account_info, submit_code, waiting_for_code
from keyboards import (
    BTN_GENERATE,
    BTN_IDEA,
    BTN_PERSONA,
    BTN_QUEUE,
    BTN_SETTINGS,
    BTN_STATUS,
    generate_choice_kb,
    main_kb,
    persona_kb,
    settings_kb,
)
from persona import format_persona, load_persona, save_persona
from pipeline import is_busy, publish_post, regenerate_video, run_generation

_dp_ready = False

ensure_dirs()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_DIR / "bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("neuro")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()


class AdminOnly(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.id not in ADMIN_USER_IDS:
            if isinstance(event, CallbackQuery):
                await event.answer("Нет доступа", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Этот бот только для владельца.")
            return None
        return await handler(event, data)


class Form(StatesGroup):
    topic = State()
    caption = State()
    xai = State()
    ig_user = State()
    ig_pass = State()
    persona_value = State()
    photo = State()


def setup_text() -> str:
    gaps = missing_setup()
    ig = f"@{IG_USERNAME}" if IG_USERNAME else "нет"
    if XAI_API_KEY:
        grok = "ключ API"
    elif grok_ready():
        grok = "сессия grok.com"
    else:
        grok = "нет"
    face = "есть" if CHARACTER_FILE.exists() else "нет"
    lines = [
        "Нейро-блогер @motivstile.ai",
        "Ниша: vaqt sayohati · til: o'zbek · peak Toshkent",
        "",
        f"Grok: {grok}",
        f"Instagram: {ig}",
        f"Лицо персонажа: {face}",
        f"Sifat: 9:16 · 30s · 8/kun · slotdan 30 daqiqa oldin tayyor",
        f"Avtopilot: {'yoqilgan' if config.AUTO_POST else 'off'}",
        f"Hozir band: {'ha' if is_busy() else 'yoq'}",
    ]
    if gaps:
        lines += ["", "Не хватает: " + ", ".join(gaps)]
        if "Grok" in gaps:
            lines += [
                "",
                "Grok login qil yoki ⚙️ ga XAI_API_KEY qo'y.",
            ]
    else:
        lines += ["", "Avtopilot o'zi yozadi va Instagramga chiqaradi. 🎬 — qo'shimcha reel."]
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(setup_text(), reply_markup=main_kb())


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message) -> None:
    reload_env()
    c = await counts()
    extra = ""
    if IG_USERNAME and IG_PASSWORD:
        try:
            info = await asyncio.to_thread(account_info)
            extra = (
                f"\nIG @{info.get('username')} · "
                f"{info.get('follower_count')} подп. · "
                f"{info.get('media_count')} постов"
            )
        except Exception as exc:
            extra = f"\nIG пока не залогинен: {exc}"
    posted = c.get("posted", 0)
    ready = c.get("ready", 0)
    failed = c.get("failed", 0)
    await message.answer(
        setup_text()
        + extra
        + f"\n\nГотово: {ready}\nВыложено: {posted} (сегодня {c.get('posted_today', 0)})\nОшибки: {failed}",
        reply_markup=main_kb(),
    )


@router.message(Command("queue"))
@router.message(F.text == BTN_QUEUE)
async def cmd_queue(message: Message) -> None:
    rows = await list_posts(12)
    if not rows:
        await message.answer("Очередь пустая.")
        return
    lines = []
    for p in rows:
        idea = (p.get("idea") or p.get("topic") or "—")[:60]
        lines.append(f"#{p['id']} [{p['status']}] {idea}")
    await message.answer("\n".join(lines))


@router.message(Command("idea"))
@router.message(F.text == BTN_IDEA)
async def cmd_idea(message: Message) -> None:
    from grok_api import invent_script

    if "Grok" in missing_setup():
        await message.answer("Grok yo'q. ⚙️ Настройки.")
        return
    wait = await message.answer("Думаю тему…")
    try:
        script = await invent_script(None)
        await wait.edit_text(
            f"Идея: {script['idea']}\n\nХук: {script['hook']}\n\n{script['caption']}\n\n"
            "Если ок — 🎬 Сгенерировать и выбери «своя тема», вставь эту идею."
        )
    except GrokError as exc:
        await wait.edit_text(str(exc))


@router.message(Command("generate"))
@router.message(F.text == BTN_GENERATE)
async def cmd_generate(message: Message, state: FSMContext) -> None:
    await state.clear()
    if "Grok" in missing_setup():
        await message.answer("Grok yo'q. ⚙️ Настройки → ключ yoki grok login.")
        return
    if is_busy():
        await message.answer("Уже генерирую. Дождись.")
        return
    await message.answer("Какой ролик?", reply_markup=generate_choice_kb())


@router.callback_query(F.data == "gen:random")
async def cb_random(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer()
    await cb.message.answer("Пошла генерация со случайной идеей.")
    asyncio.create_task(run_generation(bot, cb.message.chat.id, None))


@router.callback_query(F.data == "gen:topic")
async def cb_topic(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.set_state(Form.topic)
    await cb.message.answer("Напиши тему одним сообщением. Например: «дисциплина в зале в 6 утра».")


@router.message(Form.topic)
async def on_topic(message: Message, state: FSMContext) -> None:
    topic = (message.text or "").strip()
    await state.clear()
    if not topic:
        await message.answer("Пусто.")
        return
    await message.answer(f"Тема: {topic}\nГенерирую.")
    asyncio.create_task(run_generation(bot, message.chat.id, topic))


@router.callback_query(F.data.startswith("post:"))
async def cb_post(cb: CallbackQuery) -> None:
    post_id = int(cb.data.split(":")[1])
    await cb.answer("Публикую")
    asyncio.create_task(publish_post(bot, cb.message.chat.id, post_id))


@router.callback_query(F.data.startswith("regen:"))
async def cb_regen(cb: CallbackQuery) -> None:
    post_id = int(cb.data.split(":")[1])
    await cb.answer("Новый дубль")
    asyncio.create_task(regenerate_video(bot, cb.message.chat.id, post_id))


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(cb: CallbackQuery) -> None:
    post_id = int(cb.data.split(":")[1])
    await update_post(post_id, status="rejected")
    await cb.answer("Скип")
    await cb.message.answer(f"#{post_id} скипнул.")


@router.callback_query(F.data.startswith("cap:"))
async def cb_cap(cb: CallbackQuery, state: FSMContext) -> None:
    post_id = int(cb.data.split(":")[1])
    await state.set_state(Form.caption)
    await state.update_data(post_id=post_id)
    post = await get_post(post_id)
    await cb.answer()
    await cb.message.answer(
        f"Сейчас подпись:\n\n{post.get('caption') if post else '—'}\n\nПришли новую целиком."
    )


@router.message(Form.caption)
async def on_caption(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    post_id = int(data["post_id"])
    await update_post(post_id, caption=message.text or "")
    await message.answer(f"#{post_id} подпись обновлена. Можно жать ✅.")


@router.message(F.text == BTN_PERSONA)
async def cmd_persona(message: Message) -> None:
    await message.answer(format_persona(load_persona()), reply_markup=persona_kb())


@router.callback_query(F.data.startswith("per:"))
async def cb_persona_field(cb: CallbackQuery, state: FSMContext) -> None:
    field = cb.data.split(":")[1]
    await state.set_state(Form.persona_value)
    await state.update_data(field=field)
    await cb.answer()
    await cb.message.answer(f"Новое значение для «{field}» — одним сообщением.")


@router.message(Form.persona_value)
async def on_persona_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    field = data["field"]
    p = load_persona()
    p[field] = (message.text or "").strip()
    save_persona(p)
    await message.answer("Записал.\n\n" + format_persona(p), reply_markup=persona_kb())


@router.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message) -> None:
    await message.answer(setup_text(), reply_markup=settings_kb())


@router.callback_query(F.data == "set:xai")
async def cb_xai(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Form.xai)
    await cb.answer()
    await cb.message.answer(
        "Пришли ключ с https://console.x.ai (начинается с xai-). "
        "Сообщение потом лучше удали."
    )


@router.message(Form.xai)
async def on_xai(message: Message, state: FSMContext) -> None:
    await state.clear()
    key = (message.text or "").strip()
    if not key.startswith("xai-"):
        await message.answer("Это не похоже на ключ xAI. Должен начинаться с xai-")
        return
    upsert_env("XAI_API_KEY", key)
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("Ключ сохранил. Можно генерировать.")


@router.callback_query(F.data == "set:ig")
async def cb_ig(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Form.ig_user)
    await cb.answer()
    await cb.message.answer("Логин Instagram (без @).")


@router.message(Form.ig_user)
async def on_ig_user(message: Message, state: FSMContext) -> None:
    upsert_env("IG_USERNAME", (message.text or "").strip().lstrip("@"))
    await state.set_state(Form.ig_pass)
    await message.answer("Пароль Instagram.")


@router.message(Form.ig_pass)
async def on_ig_pass(message: Message, state: FSMContext) -> None:
    await state.clear()
    upsert_env("IG_PASSWORD", message.text or "")
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("Логин Instagram сохранил. При публикации спрошу код, если Instagram его захочет.")


@router.callback_query(F.data == "set:res:480p")
@router.callback_query(F.data == "set:res:720p")
async def cb_res(cb: CallbackQuery) -> None:
    res = cb.data.split(":")[-1]
    upsert_env("VIDEO_RESOLUTION", res)
    await cb.answer(res)
    await cb.message.answer(f"Качество роликов: {res}")


@router.callback_query(F.data == "set:face")
async def cb_face(cb: CallbackQuery) -> None:
    await cb.answer("Рисую лицо")
    if not grok_ready():
        await cb.message.answer("Grok yo'q.")
        return
    try:
        if CHARACTER_FILE.exists():
            CHARACTER_FILE.unlink()
        path = await ensure_character()
        await cb.message.answer_photo(
            FSInputFile(path),
            caption="Это лицо блогера. Все ролики будут с ним. Не нравится — снова «Сгенерировать лицо» или пришли своё фото.",
        )
    except Exception as exc:
        await cb.message.answer(f"Не вышло: {exc}")


@router.callback_query(F.data == "set:photo")
async def cb_photo(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Form.photo)
    await cb.answer()
    await cb.message.answer("Пришли фото лица (лучше вертикальное, одно лицо, без текста).")


@router.message(Form.photo, F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _save_character_photo(message)


@router.message(F.photo)
async def on_any_photo(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        return
    await _save_character_photo(message)


async def _save_character_photo(message: Message) -> None:
    photo = message.photo[-1]
    dest = CHARACTER_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    await bot.download(photo, destination=dest)
    await message.answer_photo(
        FSInputFile(dest),
        caption="Лицо блогера обновлено. Следующие ролики будут с этого фото.",
    )


@router.message(F.text.regexp(r"^\d{4,8}$"))
async def on_digits(message: Message) -> None:
    if waiting_for_code:
        submit_code(message.text or "")
        await message.answer("Код принял, пробую войти в Instagram.")
        return
    await message.answer("Это код? Сейчас Instagram его не ждёт. Если тема ролика — жми 🎬.")


@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    if "Grok" in missing_setup():
        await message.answer("Grok yo'q. ⚙️ Настройки.")
        return
    if is_busy():
        await message.answer("Уже генерирую. Дождись.")
        return
    await message.answer(f"Тема: {text}\nГенерирую.")
    asyncio.create_task(run_generation(bot, message.chat.id, text))


def setup_dispatcher() -> None:
    global _dp_ready
    if _dp_ready:
        return
    dp.message.middleware(AdminOnly())
    dp.callback_query.middleware(AdminOnly())
    dp.include_router(router)
    _dp_ready = True


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN пустой")
        sys.exit(1)
    await init_db()
    setup_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    logger.info("neuro-blogger @%s polling", me.username)
    if config.AUTO_POST:
        from worker import auto_loop

        asyncio.create_task(auto_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
