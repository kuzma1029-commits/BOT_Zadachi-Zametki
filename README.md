# BOT_Задачи-Заметки

Telegram-бот для записи, категоризации и анализа задач и заметок: пишете текст
обычным сообщением, бот определяет тип и категорию через GigaChat, сохраняет
данные в Grist через MCP-сервер, а на вопросы с «?» отвечает аналитикой по своим данным.

**Живой проект**
- Telegram-бот: https://t.me/Tyrki_1348_bot
- Таблицы Grist: https://docs.getgrist.com/5BrBNc9VUqx8

---

## Решаемая задача

Личный учёт дел без структурированного ввода: не нужно выбирать форму, категорию
или открывать приложение. Достаточно написать сообщение — бот сам:

1. понимает, что перед ним: **задача** («Заменить масло в машине»), **заметка**
   («Сегодня была интересная мысль…») или **вопрос на аналитику**
   («Сколько у меня задач по категории дом?»);
2. определяет категорию (Дом / Авто / Работа / Обучение / Прочее);
3. кладёт запись в нужную таблицу Grist с датой и статусом;
4. отвечает на аналитические вопросы цифрами из своих же данных.

## Пользователь

Персональный (один) пользователь: владелец Telegram-аккаунта, который ведёт
собственные задачи и заметки. Многопользовательского режима, регистрации и прав
доступа нет — доступ определяется токеном бота. Данные хранятся в личном
документе Grist пользователя.

## Как это работает

```
Telegram → aiogram 3 → GigaChat (тип записи + категория)
                     ↘ MCP Client → Grist MCP Server → Grist
```

| Тип записи | Признак | Действие |
|---|---|---|
| Задача | начинается с глагола («Купить…», «Заменить…») | запись в таблицу «Задачи» |
| Заметка | любой другой текст | запись в таблицу «Заметки» |
| Аналитика | текст заканчивается на `?` | GigaChat строит SQL → Grist выполняет → краткий ответ |

## Стек и инструменты

| Компонент | Версия / выбор | Зачем |
|---|---|---|
| Python | 3.14 | язык реализации |
| aiogram | 3.31 | Telegram-бот, polling, inline-кнопки |
| GigaChat SDK | 0.2.3 | классификация текста, генерация SQL, формулировка ответа |
| MCP Python SDK | 2.3 | клиент Grist MCP (Streamable HTTP) |
| Grist MCP Server | `https://docs.getgrist.com/api/mcp` | доступ к таблицам по API-ключу |
| Grist | SaaS-документ | хранение задач/заметок и аналитика (SQL) |
| pydantic-settings | 2.15 | конфигурация через `.env` |
| httpx / httpx2 | 0.28 / 2.13 | HTTP-клиенты GigaChat и MCP-транспорта |
| ruff, mypy | 0.17 / 2.4 | линт и проверка типов |
| GitHub CLI | 2.99 | публикация репозитория |

## Возможности и команды

| Команда | Действие |
|---|---|
| `/start`, `/help` | приветствие и справка |
| `/categories` | список категорий |
| `/addcategory <название>` | добавить категорию (в бота и в Grist) |
| `/delcategory <название>` | удалить категорию |
| `/statuses` | список статусов |
| `/addstatus <название>` | добавить статус (в бота и в Grist) |
| `/delstatus <название>` | удалить статус |

Любой другой текст без `/` бот классифицирует сам. Списки категорий и статусов
хранятся в `data/taxonomy.json`, синхронизируются с Choice-колонками обеих таблиц
и подставляются в системный промпт GigaChat.

**Схема Grist:** таблицы «Задачи» и «Заметки», колонки `Текст` (Text),
`Категория` (Choice), `Время/Дата` (DateTime, Europe/Moscow), `Статус` (Choice).

## Как запустить

### 1. Клонировать и установить зависимости

```bash
git clone https://github.com/kuzma1029-commits/BOT_Zadachi-Zametki.git
cd BOT_Zadachi-Zametki
python -m venv .venv
.venv\Scripts\activate        # Windows; Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Заполнить `.env`

```bash
cp .env.example .env
```

| Переменная | Откуда взять |
|---|---|
| `BOT_TOKEN` | @BotFather → `/newbot` |
| `GIGACHAT_AUTH_KEY` | [НейроПомощник GigaChat](https://ngw.devices.sberbank.ru), scope `GIGACHAT_API_PERS` |
| `GIGACHAT_MODEL` | по умолчанию `GigaChat-3-Pro` |
| `GIGACHAT_VERIFY_SSL` | `0` — без проверки SSL (для продакшена получите Russian Trusted Root CA и поставьте `1`) |
| `GRIST_API_KEY` | Grist → Account settings → API keys |
| `GRIST_DOC_ID` | id документа из его URL |
| `GRIST_TASKS_TABLE` / `GRIST_NOTES_TABLE` | имена таблиц: `Задачи`, `Заметки` |

`.env` в репозиторий не попадает — ключи живут только на вашей машине.

### 3. Настроить схему Grist

```bash
python scripts/setup_grist.py
```

Скрипт найдёт таблицы, приведёт колонки к нужным типам и пропишет актуальные
категории/статусы в Choice-колонки. Повторный запуск безопасен.

### 4. Запустить бота

```bash
python main.py
```

При старте бот подключается к Grist MCP, резолвит таблицы и начинает polling.

### 5. Проверить без Telegram (опционально)

```bash
python scripts/smoke_test.py                 # классификация, запись, аналитика
python scripts/setup_grist.py --cleanup      # удалить тестовые записи
```

### Качество кода

```bash
ruff check .
mypy --ignore-missing-imports config bot services utils main.py scripts
```

## Структура проекта

```
main.py                       точка входа (polling, startup/shutdown)
config/settings.py            pydantic-settings + .env
bot/handlers/commands.py      команды и inline-кнопки
bot/handlers/messages.py      обработка текста: classify → запись/аналитика
bot/keyboards/inline.py       клавиатура
services/gigachat/client.py   GigaChat: classify, генерация SQL, формулировка ответа
services/grist/mcp_client.py  MCP-клиент Grist
utils/prompts.py              системные промпты
utils/taxonomy.py             категории/статусы (data/taxonomy.json)
scripts/setup_grist.py        настройка схемы Grist
scripts/smoke_test.py         проверка GigaChat + Grist без Telegram
```

## Особенности реализации

- **MCP без OAuth.** Серверу Grist передаётся API-ключ в заголовке
  `Authorization: Bearer` — браузерное подключение для бота не требуется.
- **Имена вместо id.** В настройках указаны человекочитаемые имена
  (`Задачи`, `Категория`), клиент сам находит их внутренние id (`Table1`, `B`).
- **Аналитика в два шага.** GigaChat по схеме документа генерирует SQL, Grist
  выполняет запрос, затем модель формулирует короткий ответ — SQL в чат не выводится.
- **Категории и статусы живые.** Команда `/addcategory` меняет и бота, и выпадающие
  списки в Grist, и промпт классификатора — без правки кода.
