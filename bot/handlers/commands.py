import html

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import start_keyboard
from config.settings import settings
from services.grist.mcp_client import GristMCPError, grist_client
from utils.taxonomy import (
    add_category,
    add_status,
    get_categories,
    get_statuses,
    remove_category,
    remove_status,
)

router = Router(name="commands")

HELP_TEXT = (
    "🤖 <b>Бот задач и заметок</b>\n\n"
    "Просто напишите сообщение — бот сам разберётся:\n"
    "• <i>«Купить фильтр для воды»</i> → задача\n"
    "• <i>«Сегодня интересная мысль...»</i> → заметка\n"
    "• <i>«Сколько у меня задач по категории дом?»</i> → аналитика\n\n"
    "Команды:\n"
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


@router.callback_query(F.data == "ui:categories")
async def cb_categories(call: CallbackQuery) -> None:
    await _edit_reply(call, await categories_text())


@router.callback_query(F.data == "ui:statuses")
async def cb_statuses(call: CallbackQuery) -> None:
    await _edit_reply(call, await statuses_text())


@router.callback_query(F.data == "ui:help")
async def cb_help(call: CallbackQuery) -> None:
    await _edit_reply(call, HELP_TEXT)
