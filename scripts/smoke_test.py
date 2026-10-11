"""Смоук-тест: GigaChat + Grist MCP без Telegram.

Запуск:  python scripts/smoke_test.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings
from services.gigachat.client import giga_client
from services.grist.mcp_client import GristMCPError, grist_client

SAMPLES = [
    "Купить фильтр для воды и заменить",
    "Заменить масло в машине",
    "Дочитать главу по FastAPI",
    "Подготовить отчёт для шефа",
    "Сегодня была интересная мысль о том, как устроен мир",
    "Сколько у меня задач по категории дом?",
]


async def main() -> None:
    print("== 1. GigaChat: классификация ==")
    for sample in SAMPLES:
        data = await giga_client.classify_async(sample)
        print(f"  {sample!r}\n    -> {json.dumps(data, ensure_ascii=False)}")

    print("\n== 2. Grist MCP: схема ==")
    await grist_client.connect()
    await grist_client.warmup()
    schema = await grist_client.schema_description()
    print(schema)

    print("\n== 3. Grist MCP: запись (DateTime round-trip) ==")
    when = datetime.now().replace(microsecond=0).isoformat()
    result = await grist_client.add_record(
        settings.GRIST_TASKS_TABLE,
        {
            settings.GRIST_TEXT_COLUMN: "ТЕСТ: проверка записи из смоук-теста",
            settings.GRIST_CATEGORY_COLUMN: "Дом",
            settings.GRIST_DATETIME_COLUMN: when,
            settings.GRIST_STATUS_COLUMN: "Новая",
        },
    )
    print(f"  added: {result}, sent datetime: {when}")
    rows = await grist_client.list_records(settings.GRIST_TASKS_TABLE)
    for row in rows.get("records", []):
        if str((row.get("fields") or {}).get("A", "")).startswith("ТЕСТ"):
            print(f"  read back: id={row['id']} fields={json.dumps(row['fields'], ensure_ascii=False)}")

    print("\n== 4. Grist MCP: аналитика (SQL) ==")
    question = "Сколько у меня задач по категории дом?"
    sql = await giga_client.make_sql_async(question, schema)
    print(f"  SQL: {sql}")
    result = await grist_client.query(sql)
    print(f"  rows: {json.dumps(result, ensure_ascii=False)[:500]}")
    answer = await giga_client.make_answer_async(
        question, json.dumps(result, ensure_ascii=False)
    )
    print(f"  answer: {answer}")

    print("\nСмоук-тест завершён. Удалите тестовые записи: python scripts/setup_grist.py --cleanup")


async def run() -> None:
    try:
        await main()
    finally:
        await grist_client.close()
        giga_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except GristMCPError as exc:
        print(f"Grist error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
