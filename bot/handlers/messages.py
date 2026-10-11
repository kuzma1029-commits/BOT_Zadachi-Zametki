import html
import json
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import InlineKeyboardMarkup, Message

from bot.keyboards.inline import status_keyboard
from config.settings import settings
from services.gigachat.client import GigaChatError, giga_client
from services.grist.mcp_client import GristMCPError, grist_client
from utils.taxonomy import get_statuses

logger = logging.getLogger("grist_bot.messages")
router = Router(name="messages")


def _limit_result(result: object) -> str:
    """Готовит результат запроса для промпта: не больше MAX_ANALYTICS_ROWS строк."""
    max_rows = settings.MAX_ANALYTICS_ROWS
    if isinstance(result, list) and len(result) > max_rows:
        payload: object = result[:max_rows]
        note = f" (показаны первые {max_rows} из {len(result)} строк)"
    else:
        payload = result
        note = ""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text[:6000] + note


async def _save_record(message: Message, table: str, data: dict, title: str, emoji: str) -> None:
    when = datetime.now().replace(microsecond=0).isoformat()
    try:
        result = await grist_client.add_record(
            table,
            {
                settings.GRIST_TEXT_COLUMN: data["text"],
                settings.GRIST_CATEGORY_COLUMN: data["category"],
                settings.GRIST_DATETIME_COLUMN: when,
                settings.GRIST_STATUS_COLUMN: data["status"],
            },
        )
    except GristMCPError as exc:
        await message.answer(f"⚠️ Не удалось сохранить в Grist: {html.escape(str(exc))}")
        return

    keyboard = await _status_keyboard_for(table, data, result)
    await message.answer(
        f"{emoji} <b>{title}</b> сохранена в «{html.escape(table)}»\n"
        f"<i>{html.escape(data['text'])}</i>\n\n"
        f"Категория: {html.escape(data['category'])} · "
        f"Статус: {html.escape(data['status'])}",
        reply_markup=keyboard,
    )


async def _status_keyboard_for(
    table: str, data: dict, result: object
) -> InlineKeyboardMarkup | None:
    """Кнопки смены статуса для записей в Grist (задачи и заметки)."""
    if table not in (settings.GRIST_TASKS_TABLE, settings.GRIST_NOTES_TABLE):
        return None
    row_id = None
    if isinstance(result, dict):
        ids = result.get("ids") or []
        if ids:
            row_id = ids[0]
    if not isinstance(row_id, int):
        logger.warning("Не удалось получить id записи: %r", result)
        return None

    statuses = get_statuses()
    current = statuses.index(data["status"]) if data["status"] in statuses else -1
    table_id = await grist_client.table_id(table)
    return status_keyboard(table_id, row_id, current, statuses, src="m")


async def _analytics(message: Message, question: str) -> None:
    sql = ""
    try:
        schema = await grist_client.schema_description()
        sql = await giga_client.make_sql_async(question, schema)
        logger.info("SQL: %s", sql)
        result = await grist_client.query(sql)
        answer = await giga_client.make_answer_async(question, _limit_result(result))
    except (GigaChatError, GristMCPError) as exc:
        logger.warning("Аналитика не удалась (SQL: %s): %s", sql, exc)
        await message.answer(f"⚠️ Не удалось получить аналитику: {html.escape(str(exc))}")
        return
    await message.answer(f"📊 {html.escape(answer)}")


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    bot = message.bot
    if bot is not None:
        try:
            await bot.send_chat_action(message.chat.id, "typing")
        except Exception as exc:  # noqa: BLE001
            logger.debug("send_chat_action failed: %s", exc)

    try:
        data = await giga_client.classify_async(text)
    except GigaChatError as exc:
        await message.answer(f"⚠️ Не удалось обработать сообщение: {html.escape(str(exc))}")
        return
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"⚠️ Непредвиденная ошибка: {html.escape(str(exc))}")
        return

    kind = data.get("type")
    if kind == "task":
        await _save_record(message, settings.GRIST_TASKS_TABLE, data, "Задача", "✅")
    elif kind == "note":
        await _save_record(message, settings.GRIST_NOTES_TABLE, data, "Заметка", "📝")
    elif kind == "analytics":
        await _analytics(message, data["query"])
    else:
        await message.answer("⚠️ Не удалось определить тип записи, попробуйте ещё раз.")
