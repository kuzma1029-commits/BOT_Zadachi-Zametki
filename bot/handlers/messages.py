import html
import json
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import Message

from config.settings import settings
from services.gigachat.client import GigaChatError, giga_client
from services.grist.mcp_client import GristMCPError, grist_client

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
        await grist_client.add_record(
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
    await message.answer(
        f"{emoji} <b>{title}</b> сохранена в «{html.escape(table)}»\n"
        f"<i>{html.escape(data['text'])}</i>\n\n"
        f"Категория: {html.escape(data['category'])} · "
        f"Статус: {html.escape(data['status'])}"
    )


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
