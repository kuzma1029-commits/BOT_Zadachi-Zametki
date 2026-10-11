"""Идемпотентная настройка схемы Grist для бота.

Запуск:  python scripts/setup_grist.py

Что делает:
  * находит таблицы «Задачи» и «Заметки»;
  * приводит колонки к нужным типам (Text / Choice / DateTime);
  * прописывает актуальные категории и статусы в Choice-колонки.

Флаг --cleanup удаляет тестовые записи с текстом, начинающимся на «ТЕСТ».
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings
from services.grist.mcp_client import GristMCPError, grist_client
from utils.taxonomy import get_categories, get_statuses

COLUMNS = {
    settings.GRIST_TEXT_COLUMN: {"type": "Text"},
    settings.GRIST_CATEGORY_COLUMN: {"type": "Choice"},
    settings.GRIST_DATETIME_COLUMN: {
        "type": "DateTime",
        "date_format": "YYYY-MM-DD",
        "time_format": "HH:mm",
    },
    settings.GRIST_STATUS_COLUMN: {"type": "Choice"},
}


async def setup() -> None:
    await grist_client.connect()
    await grist_client.warmup()

    categories = get_categories()
    statuses = get_statuses()

    for table in (settings.GRIST_TASKS_TABLE, settings.GRIST_NOTES_TABLE):
        table_id = await grist_client.table_id(table)
        print(f"\nТаблица «{table}» (id: {table_id})")
        for label, options in COLUMNS.items():
            column_id = await grist_client.column_id(table_id, label)
            payload: dict[str, Any] = dict(options)
            if label == settings.GRIST_CATEGORY_COLUMN:
                payload["choices"] = categories
            if label == settings.GRIST_STATUS_COLUMN:
                payload["choices"] = statuses
            await grist_client.call_json(
                "grist_update_table_column",
                {
                    "doc_id": grist_client.doc_id,
                    "table_id": table_id,
                    "column_id": column_id,
                    "column_options": payload,
                },
            )
            grist_client._columns_cache.pop(table_id, None)
            extra = ""
            if payload.get("choices"):
                extra = f" choices={payload['choices']}"
            print(f"  [ok] {label} -> id={column_id}, type={payload['type']}{extra}")

    print("\nСхема настроена.")


async def cleanup() -> None:
    await grist_client.connect()
    for table in (settings.GRIST_TASKS_TABLE, settings.GRIST_NOTES_TABLE):
        table_id = await grist_client.table_id(table)
        text_col = await grist_client.column_id(table_id, settings.GRIST_TEXT_COLUMN)
        data = await grist_client.call_json(
            "grist_list_records",
            {"doc_id": grist_client.doc_id, "table_id": table_id, "limit": 1000},
        )
        for record in data.get("records", []):
            value = str((record.get("fields") or {}).get(text_col) or "")
            if value.startswith("ТЕСТ"):
                await grist_client.call_json(
                    "grist_remove_records",
                    {
                        "doc_id": grist_client.doc_id,
                        "table_id": table_id,
                        "record_ids": [record["id"]],
                    },
                )
                print(f"  [del] test-record #{record['id']} in \"{table}\"")
    print("Готово.")


async def amain() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true", help="удалить тестовые записи")
    args = parser.parse_args()
    try:
        if args.cleanup:
            await cleanup()
        else:
            await setup()
    except GristMCPError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        await grist_client.close()


if __name__ == "__main__":
    asyncio.run(amain())
