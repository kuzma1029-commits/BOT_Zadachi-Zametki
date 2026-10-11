import asyncio
import json
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from config.settings import settings


class GristMCPError(Exception):
    pass


class GristMCPClient:
    """MCP-клиент для Grist (Streamable HTTP + API-ключ в заголовке Authorization)."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        doc_id: str | None = None,
    ) -> None:
        self.url = url or settings.GRIST_MCP_URL
        self.api_key = api_key or settings.GRIST_API_KEY
        self.doc_id = doc_id or settings.GRIST_DOC_ID
        self._http: httpx2.AsyncClient | None = None
        self._mcp: Client | None = None
        self._lock = asyncio.Lock()
        self._tables_cache: list[dict] | None = None
        self._columns_cache: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------ connect
    @property
    def connected(self) -> bool:
        return self._mcp is not None

    async def connect(self) -> None:
        async with self._lock:
            if self._mcp is not None:
                return
            if not self.api_key or not self.doc_id:
                raise GristMCPError("Не заданы GRIST_API_KEY и/или GRIST_DOC_ID в .env")
            self._http = httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=httpx2.Timeout(settings.GRIST_TIMEOUT),
            )
            transport = streamable_http_client(self.url, http_client=self._http)
            self._mcp = Client(transport, read_timeout_seconds=settings.GRIST_TIMEOUT)
            await self._mcp.__aenter__()

    async def close(self) -> None:
        async with self._lock:
            if self._mcp is not None:
                try:
                    await self._mcp.__aexit__(None, None, None)
                finally:
                    self._mcp = None
            if self._http is not None:
                try:
                    await self._http.aclose()
                finally:
                    self._http = None
            self._tables_cache = None
            self._columns_cache.clear()

    def _require(self) -> Client:
        if self._mcp is None:
            raise GristMCPError("MCP-клиент Grist не подключён (нет connect())")
        return self._mcp

    # ------------------------------------------------------------------- tools
    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        client = self._require()
        try:
            result = await client.call_tool(name, args)
        except GristMCPError:
            raise
        except Exception as exc:
            raise GristMCPError(f"Ошибка вызова {name}: {exc}") from exc
        text = "".join(
            getattr(part, "text", "") or "" for part in (result.content or [])
        )
        if getattr(result, "is_error", False):
            raise GristMCPError(text.strip() or f"Инструмент {name} вернул ошибку")
        return text.strip()

    async def call_json(self, name: str, args: dict[str, Any]) -> Any:
        text = await self.call_tool(name, args)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GristMCPError(f"{name}: не удалось разобрать ответ: {text[:200]}") from exc

    async def list_tools(self) -> list[str]:
        client = self._require()
        tools = await client.list_tools()
        return [tool.name for tool in tools.tools]

    # ------------------------------------------------------------- introspection
    async def tables(self) -> list[dict]:
        if self._tables_cache is None:
            data = await self.call_json(
                "grist_get_tables", {"doc_id": self.doc_id}
            )
            if isinstance(data, dict):
                data = data.get("tables", [])
            self._tables_cache = [
                {"id": t.get("id"), "name": t.get("name") or t.get("id")} for t in data
            ]
        return self._tables_cache

    async def table_id(self, name: str) -> str:
        """Резолвит имя таблицы («Задачи») в её id («Table1»)."""
        tables = await self.tables()
        for table in tables:
            if name in (table["id"], table["name"]):
                return str(table["id"])
        available = ", ".join(f"{t['name']} ({t['id']})" for t in tables)
        raise GristMCPError(f"Таблица «{name}» не найдена. Есть: {available}")

    async def columns(self, table_id: str) -> list[dict]:
        if table_id not in self._columns_cache:
            data = await self.call_json(
                "grist_get_table_columns", {"doc_id": self.doc_id, "table_id": table_id}
            )
            if isinstance(data, dict):
                data = data.get("columns", [])
            columns = []
            for col in data:
                fields = col.get("fields") or {}
                options = {}
                widget = fields.get("widgetOptions")
                if isinstance(widget, dict):
                    options = widget
                elif isinstance(widget, str) and widget.strip():
                    try:
                        options = json.loads(widget)
                    except json.JSONDecodeError:
                        options = {}
                columns.append(
                    {
                        "id": col.get("id"),
                        "label": fields.get("label") or col.get("id"),
                        "type": fields.get("type"),
                        "choices": options.get("choices") or [],
                    }
                )
            self._columns_cache[table_id] = columns
        return self._columns_cache[table_id]

    async def column_id(self, table_id: str, label: str) -> str:
        for col in await self.columns(table_id):
            if label in (col["id"], col["label"]):
                return str(col["id"])
        available = ", ".join(c["label"] for c in await self.columns(table_id))
        raise GristMCPError(f"Колонка «{label}» не найдена в {table_id}. Есть: {available}")

    async def schema_description(self) -> str:
        """Описание схемы для промпта генерации SQL (только id, никаких имён)."""
        lines = []
        for name in (settings.GRIST_TASKS_TABLE, settings.GRIST_NOTES_TABLE):
            try:
                tid = await self.table_id(name)
            except GristMCPError:
                continue
            lines.append(f'Таблица «{name}» (id: {tid}):')
            for col in await self.columns(tid):
                details = col["type"] or "?"
                if col["choices"]:
                    details += f', значения: {", ".join(col["choices"])}'
                lines.append(f'  - id "{col["id"]}" (label «{col["label"]}»): {details}')
        if not lines:
            raise GristMCPError("Не удалось получить схему документа Grist")
        return "\n".join(lines)

    # ------------------------------------------------------------------- writes
    async def add_record(self, table: str, fields: dict[str, Any]) -> Any:
        """Добавляет запись. keys — названия колонок (label), значения — данные."""
        tid = await self.table_id(table)
        record = {}
        for label, value in fields.items():
            record[await self.column_id(tid, label)] = value
        return await self.call_json(
            "grist_add_records",
            {"doc_id": self.doc_id, "table_id": tid, "records": [record]},
        )

    async def set_choices(self, table: str, column_label: str, choices: list[str]) -> None:
        """Обновляет список вариантов Choice-колонки (категории/статусы)."""
        tid = await self.table_id(table)
        cid = await self.column_id(tid, column_label)
        await self.call_json(
            "grist_update_table_column",
            {
                "doc_id": self.doc_id,
                "table_id": tid,
                "column_id": cid,
                "column_options": {"choices": list(choices)},
            },
        )
        self._columns_cache.pop(tid, None)

    async def sync_choices(
        self, tables: list[str], column_label: str, choices: list[str]
    ) -> None:
        errors = []
        for table in tables:
            try:
                await self.set_choices(table, column_label, choices)
            except GristMCPError as exc:
                errors.append(f"{table}: {exc}")
        if errors:
            raise GristMCPError("; ".join(errors))

    # ------------------------------------------------------------------- reads
    async def query(self, sql: str, args: list[Any] | None = None) -> Any:
        return await self.call_json(
            "grist_query_document",
            {"doc_id": self.doc_id, "query": sql, "args": args or []},
        )

    async def list_records(
        self, table: str, limit: int = 100, offset: int = 0
    ) -> Any:
        tid = await self.table_id(table)
        return await self.call_json(
            "grist_list_records",
            {"doc_id": self.doc_id, "table_id": tid, "limit": limit, "offset": offset},
        )

    async def warmup(self) -> None:
        """Проверяет соединение и резолвит таблицы/колонки заранее."""
        await self.tables()
        for name in (settings.GRIST_TASKS_TABLE, settings.GRIST_NOTES_TABLE):
            tid = await self.table_id(name)
            await self.columns(tid)


grist_client = GristMCPClient()
