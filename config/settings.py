from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str

    GIGACHAT_AUTH_KEY: str
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    GIGACHAT_MODEL: str = "GigaChat-3-Pro"
    GIGACHAT_VERIFY_SSL: bool = False
    GIGACHAT_TIMEOUT: float = 60.0

    GRIST_MCP_URL: str = "https://docs.getgrist.com/api/mcp"
    GRIST_API_KEY: str = ""
    GRIST_DOC_ID: str = ""
    GRIST_TASKS_TABLE: str = "Задачи"
    GRIST_NOTES_TABLE: str = "Заметки"
    GRIST_TIMEOUT: float = 120.0

    GRIST_TEXT_COLUMN: str = "Текст"
    GRIST_CATEGORY_COLUMN: str = "Категория"
    GRIST_DATETIME_COLUMN: str = "Время/Дата"
    GRIST_STATUS_COLUMN: str = "Статус"

    DEFAULT_CATEGORIES: list[str] = ["Дом", "Авто", "Работа", "Обучение", "Прочее"]
    DEFAULT_STATUSES: list[str] = ["Новая", "В работе", "Готово"]

    DATA_DIR: Path = DATA_DIR
    MAX_ANALYTICS_ROWS: int = 30


settings = Settings()  # type: ignore[call-arg]
