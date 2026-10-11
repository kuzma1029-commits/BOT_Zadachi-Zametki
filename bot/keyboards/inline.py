from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Категории", callback_data="ui:categories"),
                InlineKeyboardButton(text="📋 Статусы", callback_data="ui:statuses"),
            ],
            [
                InlineKeyboardButton(text="❓ Помощь", callback_data="ui:help"),
            ],
        ]
    )
