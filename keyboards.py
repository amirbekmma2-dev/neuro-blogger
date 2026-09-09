from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_GENERATE = "🎬 Сгенерировать"
BTN_IDEA = "💡 Идея"
BTN_QUEUE = "📋 Очередь"
BTN_STATUS = "📊 Статус"
BTN_PERSONA = "👤 Персона"
BTN_SETTINGS = "⚙️ Настройки"


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_GENERATE), KeyboardButton(text=BTN_IDEA)],
            [KeyboardButton(text=BTN_QUEUE), KeyboardButton(text=BTN_STATUS)],
            [KeyboardButton(text=BTN_PERSONA), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Тема ролика или кнопка ниже",
    )


def generate_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎲 Случайная идея", callback_data="gen:random"),
                InlineKeyboardButton(text="✍️ Своя тема", callback_data="gen:topic"),
            ]
        ]
    )


def preview_kb(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ В Instagram", callback_data=f"post:{post_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Другое видео", callback_data=f"regen:{post_id}"
                ),
                InlineKeyboardButton(
                    text="✏️ Подпись", callback_data=f"cap:{post_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Скип", callback_data=f"skip:{post_id}"
                )
            ],
        ]
    )


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Ключ Grok API", callback_data="set:xai")],
            [InlineKeyboardButton(text="📸 Instagram логин", callback_data="set:ig")],
            [
                InlineKeyboardButton(text="🖼 Сгенерировать лицо", callback_data="set:face"),
                InlineKeyboardButton(text="📷 Своё фото", callback_data="set:photo"),
            ],
            [
                InlineKeyboardButton(text="480p ✓", callback_data="set:res:480p"),
                InlineKeyboardButton(text="720p", callback_data="set:res:720p"),
            ],
        ]
    )


def persona_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ниша", callback_data="per:niche")],
            [InlineKeyboardButton(text="Тон", callback_data="per:tone")],
            [InlineKeyboardButton(text="CTA", callback_data="per:cta")],
            [InlineKeyboardButton(text="Имя персонажа", callback_data="per:name")],
        ]
    )
