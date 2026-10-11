import asyncio
import json
import logging
import re

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from config.settings import settings
from utils.prompts import build_answer_prompt, build_sql_prompt, build_system_prompt
from utils.taxonomy import get_categories, get_statuses

logger = logging.getLogger("grist_bot.gigachat")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


class GigaChatError(Exception):
    pass


def extract_json(raw: str) -> dict:
    """Достаёт JSON из ответа модели (на случай markdown-обёртки и пояснений)."""
    text = raw.strip()
    text = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise GigaChatError(f"Модель вернула не JSON: {raw[:200]}")


class GigaChatClient:
    """Клиент GigaChat: классификация текста, генерация SQL и формулировка ответа."""

    def __init__(self) -> None:
        self._client: GigaChat | None = None

    @property
    def client(self) -> GigaChat:
        if self._client is None:
            self._client = GigaChat(
                credentials=settings.GIGACHAT_AUTH_KEY,
                scope=settings.GIGACHAT_SCOPE,
                model=settings.GIGACHAT_MODEL,
                verify_ssl_certs=settings.GIGACHAT_VERIFY_SSL,
                timeout=settings.GIGACHAT_TIMEOUT,
                profanity_check=False,
            )
        return self._client

    def _ask(self, system: str, user: str) -> str:
        messages = [
            Messages(role=MessagesRole.SYSTEM, content=system),
            Messages(role=MessagesRole.USER, content=user),
        ]
        try:
            response = self.client.chat(Chat(messages=messages))
        except Exception as exc:
            raise GigaChatError(f"GigaChat недоступен: {exc}") from exc
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise GigaChatError("GigaChat вернул пустой ответ")
        return content.strip()

    def classify(self, user_text: str) -> dict:
        """Определяет тип записи, категорию и статус. Возвращает dict."""
        categories = get_categories()
        statuses = get_statuses()
        raw = self._ask(build_system_prompt(categories, statuses), user_text)
        data = extract_json(raw)
        return self._normalize(data, user_text, categories, statuses)

    @staticmethod
    def _normalize(
        data: dict, user_text: str, categories: list[str], statuses: list[str]
    ) -> dict:
        kind = str(data.get("type", "")).strip().lower()
        if kind not in {"task", "note", "analytics"}:
            raise GigaChatError(f"Неизвестный тип записи: {kind or data}")

        if kind == "analytics":
            query = str(data.get("query") or user_text).strip()
            return {"type": "analytics", "query": query}

        text = str(data.get("text") or user_text).strip()
        category = str(data.get("category") or "").strip()
        if category not in categories:
            category = "Прочее" if "Прочее" in categories else categories[0]
        status = str(data.get("status") or "").strip()
        if status not in statuses:
            status = statuses[0]
        return {"type": kind, "text": text, "category": category, "status": status}

    def make_sql(self, question: str, schema: str) -> str:
        raw = self._ask(build_sql_prompt(schema, question), question)
        sql = _FENCE_RE.sub("", raw.strip()).strip()
        if sql[:3].lower() == "sql":
            sql = sql[3:].strip()
        sql = sql.rstrip(";").strip()
        if not sql.lower().startswith(("select", "with")):
            raise GigaChatError(f"Модель сгенерировала не SELECT: {sql[:120]}")
        return sql.rstrip(";")

    def make_answer(self, question: str, result: str) -> str:
        return self._ask(build_answer_prompt(question, result), question)

    async def classify_async(self, user_text: str) -> dict:
        return await asyncio.to_thread(self.classify, user_text)

    async def make_sql_async(self, question: str, schema: str) -> str:
        return await asyncio.to_thread(self.make_sql, question, schema)

    async def make_answer_async(self, question: str, result: str) -> str:
        return await asyncio.to_thread(self.make_answer, question, result)

    def close(self) -> None:
        if self._client is None:
            return
        for method_name in ("close", "__exit__"):
            method = getattr(self._client, method_name, None)
            if method is None:
                continue
            try:
                if method_name == "__exit__":
                    method(None, None, None)
                else:
                    method()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ошибка закрытия GigaChat: %s", exc)
        self._client = None


giga_client = GigaChatClient()
