import html
import logging
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.keyboards.inline import (
    StatusAction,
    items_keyboard,
    start_keyboard,
    status_keyboard,
)
from config.settings import settings
from services.grist.mcp_client import GristMCPError, grist_client
from utils.taxonomy import (
    add_category,
    add_status,
    get_categories,
    get_done_status,
    get_statuses,
    remove_category,
    remove_status,
)

logger = logging.getLogger("grist_bot.commands")
router = Router(name="commands")

HELP_TEXT = (
    "🤖 <b>Бот задач и заметок</b>\n\n"
    "Просто напишите сообщение — бот сам разберётся:\n"
    "• <i>«Купить фильтр для воды»</i> → задача\n"
    "• <i>«Сегодня интересная мысль...»</i> → заметка\n"
    "• <i>«Сколько у меня задач по категории дом?»</i> → аналитика\n\n"
    "Команды:\n"
    "/tasks — открытые задачи и смена статуса\n"
    "/notes — открытые заметки и смена статуса\n"
    "/categories — список категорий\n"
    "/addcategory &lt;название&gt; — добавить категорию\n"
    "/delcategory &lt;название&gt; — удалить категорию\n"
    "/statuses — список статусов\n"
    "/addstatus &lt;название&gt; — добавить статус\n"
    "/delstatus &lt;название&gt; — удалить статус\n"
    "/help — эта справка"
)


async def categories_text() -> str:
    items = "\n".join(f"• {name}" for name in get_categories())
    return (
        f"📋 <b>Категории:</b>\n{items}\n\n"
        "Добавить: /addcategory Название\n"
        "Удалить: /delcategory Название"
    )


async def statuses_text() -> str:
    items = "\n".join(f"• {name}" for name in get_statuses())
    return (
        f"📋 <b>Статусы:</b>\n{items}\n\n"
        "Добавить: /addstatus Название\n"
        "Удалить: /delstatus Название"
    )


LIST_VIEW_META: dict[str, dict[str, str]] = {
    settings.GRIST_TASKS_TABLE: {
        "title": "📋 Открытые задачи",
        "empty": "✅ Открытых задач нет.",
        "btn": "задачи",
    },
    settings.GRIST_NOTES_TABLE: {
        "title": "📝 Открытые заметки",
        "empty": "✅ Открытых заметок нет.",
        "btn": "заметки",
    },
}


async def build_items_view(table: str) -> tuple[str, InlineKeyboardMarkup | None]:
    """Список открытых записей таблицы + клавиатура смены статуса."""
    meta = LIST_VIEW_META.get(table, LIST_VIEW_META[settings.GRIST_TASKS_TABLE])
    statuses = get_statuses()
    done = get_done_status()
    open_statuses = [name for name in statuses if name != done]
    if not open_statuses:
        return meta["empty"], None

    table_id = await grist_client.table_id(table)
    text_col = await grist_client.column_id(table_id, settings.GRIST_TEXT_COLUMN)
    category_col = await grist_client.column_id(
        table_id, settings.GRIST_CATEGORY_COLUMN
    )
    status_col = await grist_client.column_id(
        table_id, settings.GRIST_STATUS_COLUMN
    )
    data = await grist_client.list_records(
        table,
        limit=1000,
        row_filter={status_col: open_statuses},
    )

    items = []
    for record in data.get("records", []):
        fields = record.get("fields") or {}
        text = str(fields.get(text_col) or "").strip()
        if not text:
            continue
        items.append(
            {
                "id": record["id"],
                "text": text,
                "category": str(fields.get(category_col) or ""),
                "status": str(fields.get(status_col) or ""),
            }
        )

    if not items:
        return meta["empty"], None

    lines = [f"<b>{meta['title']}</b> ({len(items)}):", ""]
    for number, item in enumerate(items, 1):
        lines.append(f"{number}. {html.escape(item['text'])}")
        lines.append(
            f"   {html.escape(item['category'])} · {html.escape(item['status'])}"
        )
    lines += ["", f"Кнопки ниже меняют статус {meta['btn']}."]
    return "\n".join(lines), items_keyboard(items, statuses, table_id)


def _replace_status(text: str, new_status: str) -> str:
    return re.sub(
        r"Статус: .*$", f"Статус: {html.escape(new_status)}", text, flags=re.DOTALL
    )


async def _send_list(message: Message, table: str) -> None:
    meta = LIST_VIEW_META.get(table, LIST_VIEW_META[settings.GRIST_TASKS_TABLE])
    try:
        text, keyboard = await build_items_view(table)
    except GristMCPError as exc:
        await message.answer(
            f"⚠️ Не удалось получить {meta['btn']}: {html.escape(str(exc))}"
        )
        return
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("tasks"))
async def cmd_tasks(message: Message) -> None:
    await _send_list(message, settings.GRIST_TASKS_TABLE)


@router.message(Command("notes"))
async def cmd_notes(message: Message) -> None:
    await _send_list(message, settings.GRIST_NOTES_TABLE)


async def _sync_to_grist(column_label: str, values: list[str]) -> str | None:
    """Синхронизирует Choice-колонки обеих таблиц. Возвращает текст ошибки."""
    try:
        await grist_client.sync_choices(
            [settings.GRIST_TASKS_TABLE, settings.GRIST_NOTES_TABLE],
            column_label,
            values,
        )
    except GristMCPError as exc:
        return str(exc)
    return None


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! 👋\n\n"
        "Пишите задачи и заметки текстом — я определю тип и категорию "
        "и сохраню в Grist. Вопросы с «?» превращаются в аналитику.\n\n"
        "Например: <i>«Заменить масло в машине»</i>",
        reply_markup=start_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("categories"))
async def cmd_categories(message: Message) -> None:
    await message.answer(await categories_text())


@router.message(Command("statuses"))
async def cmd_statuses(message: Message) -> None:
    await message.answer(await statuses_text())


@router.message(Command("addcategory"))
async def cmd_addcategory(message: Message, command: CommandObject) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Укажите название: /addcategory Ремонт")
        return
    changed, categories = add_category(name)
    if not changed:
        await message.answer(f"Категория «{html.escape(name)}» уже есть в списке.")
        return
    error = await _sync_to_grist(settings.GRIST_CATEGORY_COLUMN, categories)
    if error:
        await message.answer(
            f"✅ Категория «{html.escape(name)}» добавлена в бота.\n"
            f"⚠️ Не удалось обновить Grist: {html.escape(error)}"
        )
        return
    await message.answer(
        f"✅ Категория «{html.escape(name)}» добавлена в бота и в Grist."
    )


@router.message(Command("addstatus"))
async def cmd_addstatus(message: Message, command: CommandObject) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Укажите название: /addstatus Отложено")
        return
    changed, statuses = add_status(name)
    if not changed:
        await message.answer(f"Статус «{html.escape(name)}» уже есть в списке.")
        return
    error = await _sync_to_grist(settings.GRIST_STATUS_COLUMN, statuses)
    if error:
        await message.answer(
            f"✅ Статус «{html.escape(name)}» добавлен в бота.\n"
            f"⚠️ Не удалось обновить Grist: {html.escape(error)}"
        )
        return
    await message.answer(
        f"✅ Статус «{html.escape(name)}» добавлен в бота и в Grist."
    )


@router.message(Command("delcategory"))
async def cmd_delcategory(message: Message, command: CommandObject) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Укажите название: /delcategory Прочее")
        return
    changed, categories = remove_category(name)
    if not changed:
        await message.answer(
            f"Категория «{html.escape(name)}» не найдена (или это последняя категория)."
        )
        return
    error = await _sync_to_grist(settings.GRIST_CATEGORY_COLUMN, categories)
    if error:
        await message.answer(
            f"✅ Категория «{html.escape(name)}» удалена из бота.\n"
            f"⚠️ Не удалось обновить Grist: {html.escape(error)}"
        )
        return
    await message.answer(
        f"✅ Категория «{html.escape(name)}» удалена из бота и из Grist."
    )


@router.message(Command("delstatus"))
async def cmd_delstatus(message: Message, command: CommandObject) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Укажите название: /delstatus Готово")
        return
    changed, statuses = remove_status(name)
    if not changed:
        await message.answer(
            f"Статус «{html.escape(name)}» не найден (или это последний статус)."
        )
        return
    error = await _sync_to_grist(settings.GRIST_STATUS_COLUMN, statuses)
    if error:
        await message.answer(
            f"✅ Статус «{html.escape(name)}» удалён из бота.\n"
            f"⚠️ Не удалось обновить Grist: {html.escape(error)}"
        )
        return
    await message.answer(
        f"✅ Статус «{html.escape(name)}» удалён из бота и из Grist."
    )


async def _edit_reply(call: CallbackQuery, text: str) -> None:
    if isinstance(call.message, Message):
        await call.message.edit_text(text, reply_markup=start_keyboard())
    await call.answer()


@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message) -> None:
    await message.answer("Неизвестная команда. Список команд: /help")


@router.callback_query(StatusAction.filter())
async def on_status_action(call: CallbackQuery, callback_data: StatusAction) -> None:
    statuses = get_statuses()
    if not 0 <= callback_data.idx < len(statuses):
        await call.answer("Статус не найден", show_alert=True)
        return
    new_status = statuses[callback_data.idx]
    try:
        await grist_client.update_record(
            callback_data.table,
            callback_data.row,
            {settings.GRIST_STATUS_COLUMN: new_status},
        )
    except GristMCPError as exc:
        await call.answer(f"Ошибка: {exc}"[:180], show_alert=True)
        return

    await call.answer(f"Статус: {new_status}")
    message = call.message
    if not isinstance(message, Message):
        return

    if callback_data.src == "l":
        try:
            text, keyboard = await build_items_view(callback_data.table)
            await message.edit_text(text, reply_markup=keyboard)
        except GristMCPError as exc:
            logger.warning("Не удалось обновить список задач: %s", exc)
        except TelegramBadRequest:
            pass
        return

    current_idx = (
        statuses.index(new_status) if new_status in statuses else -1
    )
    try:
        await message.edit_text(
            _replace_status(message.text or "", new_status),
            reply_markup=status_keyboard(
                callback_data.table,
                callback_data.row,
                current_idx,
                statuses,
                src="m",
            ),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "ui:categories")
async def cb_categories(call: CallbackQuery) -> None:
    await _edit_reply(call, await categories_text())


@router.callback_query(F.data == "ui:statuses")
async def cb_statuses(call: CallbackQuery) -> None:
    await _edit_reply(call, await statuses_text())


@router.callback_query(F.data == "ui:help")
async def cb_help(call: CallbackQuery) -> None:
    await _edit_reply(call, HELP_TEXT)
