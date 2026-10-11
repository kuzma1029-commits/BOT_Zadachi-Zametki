# AGENTS.md — инструкция для OpenCode

## Что это за проект

Telegram-бот «Задачи и заметки»: пользователь пишет текст → GigaChat определяет
тип записи (задача / заметка / аналитика) и категорию → запись сохраняется в
Grist через MCP-сервер, аналитика отвечает цифрами из этих же данных.

```
Telegram → aiogram 3 → GigaChat (классификация)
                     ↘ MCP Client → Grist MCP Server → Grist
```

Репозиторий: https://github.com/kuzma1029-commits/BOT_Zadachi-Zametki (публичный).
Живой бот: https://t.me/Tyrki_1348_bot · Grist: https://docs.getgrist.com/5BrBNc9VUqx8

## Стек

Python 3.14 · aiogram 3.31 · gigachat SDK 0.2.3 · mcp SDK 2.3 (Streamable HTTP) ·
pydantic-settings 2.15 · httpx / httpx2 · ruff 0.17 · mypy 2.4

## Команды

```bash
python main.py                                   # запуск бота (polling)
python scripts/smoke_test.py                     # проверка GigaChat + Grist без Telegram
python scripts/setup_grist.py                    # настройка схемы Grist (идемпотентно)
python scripts/setup_grist.py --cleanup          # удалить тестовые записи (начинаются с «ТЕСТ»)

python -m ruff check .                           # линт
python -m mypy --ignore-missing-imports config bot services utils main.py scripts
```

**После любых правок кода прогоняй `ruff` и `mypy`** — это обязательная проверка.
`ruff`/`mypy` установлены в `AppData\Roaming\Python\Python314\Scripts`, на PATH их нет —
запускай через `python -m`.

Консоль Windows — cp1251: не используй эмодзи и символы вроде `✓` в `print`,
иначе `UnicodeEncodeError`. Для читаемого вывода скриптов: `$env:PYTHONIOENCODING='utf-8'`.

## Структура

```
main.py                       точка входа: polling, startup/shutdown, логирование
config/settings.py            Settings (pydantic-settings, читает .env из корня)
bot/handlers/commands.py      /start /help /tasks /notes /categories /addcategory /
                              /delcategory /statuses /addstatus /delstatus +
                              inline-кнопки, колбэк смены статуса
bot/handlers/messages.py      текст: classify → запись в Grist или аналитика;
                              кнопки смены статуса под подтверждением записи
bot/keyboards/inline.py       /start, StatusAction, клавиатуры статусов и списков
services/gigachat/client.py   GigaChatClient: classify(), make_sql(), make_answer()
services/grist/mcp_client.py  GristMCPClient: подключение, вызов инструментов, резолв имён
utils/prompts.py              SYSTEM_PROMPT, SQL-промпт, промпт формулирования ответа
utils/taxonomy.py             категории/статусы → data/taxonomy.json
data/taxonomy.json            текущие списки категорий и статусов
scripts/setup_grist.py        настройка схемы Grist
scripts/smoke_test.py         интеграционный тест без Telegram
```

## Важные особенности

- **`.env` обязателен** (см. `.env.example`). Содержит BOT_TOKEN, GIGACHAT_AUTH_KEY,
  GRIST_API_KEY, GRIST_DOC_ID. **Никогда не коммить `.env`, `.env.txt`, `*.docx`** —
  там ключи; всё это в `.gitignore`.
- **Grist MCP — по API-ключу, не OAuth.** `services/grist/mcp_client.py` создаёт
  `httpx2.AsyncClient` с заголовком `Authorization: Bearer <key>` и передаёт его в
  `streamable_http_client()`. OAuth/браузер боту не нужен.
- **Имена → id.** В настройках human-readable имена (`Задачи`, `Категория`), клиент
  сам находит внутренние id (`Table1`, `B`) и кэширует. Записи в Grist принимают
  только id таблиц/колонок, SQL — только id (`SELECT ... FROM "Table1"`).
- **Схема Grist:** `Текст`=Text, `Категория`/`Статус`=Choice, `Время/Дата`=DateTime
  (Europe/Moscow, хранится как epoch-секунды). Настройка типов и choices —
  `scripts/setup_grist.py`.
- **GigaChat SDK синхронный** → в асинхронных хендлерах вызывай через
  `asyncio.to_thread` (в клиенте уже есть `*_async`-обёртки).
- **Категории/статусы живые:** команда `/addcategory` меняет `data/taxonomy.json`,
  Choice-колонки Grist (обе таблицы) и подставляет списки в промпт. Добавляй
  функции изменения списков в `utils/taxonomy.py`, синхрон — через
  `grist_client.sync_choices(...)`.
- **Смена статуса:** `StatusAction` (prefix `st`) хранит `table, row, idx, src`
  (src: `m` — сообщение о задаче/заметке, `l` — список `/tasks` или `/notes`).
  Колбэк в `bot/handlers/commands.py` вызывает `grist_client.update_record(...)` и
  редактирует сообщение (regex `Статус: ...` для src=`m`, пересборка списка для
  `l`). Обработка TelegramBadRequest «message is not modified» обязательна.
- **Аналитика:** GigaChat генерирует SQL по схеме → `grist_query_document` →
  модель формулирует ответ. SQL в чат не выводится (пишется в лог).
- Запись/чтение GigaChat может занимать 5–20 секунд на сообщение — это нормально.

## Что не трогать без просьбы

- `.env`, `.env.txt`, `Grist Ключ API.docx` — секреты.
- Старый прототип `gigachat_client.py` в корне — заменён
  `services/gigachat/client.py`, оставлен как референс.

## Git

Коммиты и пуш — только по явной просьбе. Репозиторий публичный, поэтому перед
коммитом проверяй, что секреты не попали в индекс:

```bash
git status --short
```
