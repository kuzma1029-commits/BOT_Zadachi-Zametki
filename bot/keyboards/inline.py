from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

STATUS_SYMBOLS = {"Новая": "↩️ ", "В работе": "▶️ ", "Готово": "✅ "}


class StatusAction(CallbackData, prefix="st"):
    """Смена статуса записи: таблица + строка + индекс целевого статуса."""

    table: str
    row: int
    idx: int
    src: str  # "m" — сообщение о записи, "l" — список /tasks


def status_label(name: str) -> str:
    return STATUS_SYMBOLS.get(name, "") + name


def _short(text: str, limit: int = 20) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def status_keyboard(
    table_id: str,
    row_id: int,
    current_idx: int,
    statuses: list[str],
    src: str = "m",
) -> InlineKeyboardMarkup:
    """Кнопки смены статуса: все статусы, кроме текущего."""
    keyboard = []
    for index, name in enumerate(statuses):
        if index == current_idx:
            continue
        callback = StatusAction(
            table=table_id, row=row_id, idx=index, src=src
        ).pack()
        keyboard.append(
            [InlineKeyboardButton(text=status_label(name), callback_data=callback)]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def items_keyboard(
    items: list[dict], statuses: list[str], table_id: str
) -> InlineKeyboardMarkup:
    """Кнопки для списка /tasks и /notes: по строке на каждую запись."""
    keyboard = []
    for item in items:
        current = (
            statuses.index(item["status"]) if item["status"] in statuses else -1
        )
        row_buttons = []
        for index, name in enumerate(statuses):
            if index == current:
                continue
            callback = StatusAction(
                table=table_id, row=item["id"], idx=index, src="l"
            ).pack()
            row_buttons.append(
                InlineKeyboardButton(
                    text=f"{_short(item['text'])} → {status_label(name)}",
                    callback_data=callback,
                )
            )
        if row_buttons:
            keyboard.append(row_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
