import json
import threading

from config.settings import DATA_DIR, settings

_LOCK = threading.Lock()
_FILE = DATA_DIR / "taxonomy.json"


def _defaults() -> dict:
    return {
        "categories": list(settings.DEFAULT_CATEGORIES),
        "statuses": list(settings.DEFAULT_STATUSES),
    }


def _load() -> dict:
    if not _FILE.exists():
        return _defaults()
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _defaults()
    if not isinstance(data, dict):
        return _defaults()
    categories = [str(c) for c in data.get("categories", []) if str(c).strip()]
    statuses = [str(s) for s in data.get("statuses", []) if str(s).strip()]
    return {
        "categories": categories or list(settings.DEFAULT_CATEGORIES),
        "statuses": statuses or list(settings.DEFAULT_STATUSES),
    }


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_categories() -> list[str]:
    with _LOCK:
        return _load()["categories"]


def get_statuses() -> list[str]:
    with _LOCK:
        return _load()["statuses"]


def get_done_status() -> str:
    """Статус, означающий завершение задачи."""
    statuses = get_statuses()
    if "Готово" in statuses:
        return "Готово"
    return statuses[-1] if statuses else "Готово"


def add_category(name: str) -> tuple[bool, list[str]]:
    """Добавляет категорию. Возвращает (изменено ли, актуальный список)."""
    name = name.strip()
    with _LOCK:
        data = _load()
        if name in data["categories"]:
            return False, data["categories"]
        data["categories"].append(name)
        _save(data)
        return True, data["categories"]


def add_status(name: str) -> tuple[bool, list[str]]:
    """Добавляет статус. Возвращает (изменено ли, актуальный список)."""
    name = name.strip()
    with _LOCK:
        data = _load()
        if name in data["statuses"]:
            return False, data["statuses"]
        data["statuses"].append(name)
        _save(data)
        return True, data["statuses"]


def remove_category(name: str) -> tuple[bool, list[str]]:
    """Удаляет категорию. Нельзя удалить единственную оставшуюся."""
    name = name.strip()
    with _LOCK:
        data = _load()
        if name not in data["categories"]:
            return False, data["categories"]
        if len(data["categories"]) <= 1:
            return False, data["categories"]
        data["categories"].remove(name)
        _save(data)
        return True, data["categories"]


def remove_status(name: str) -> tuple[bool, list[str]]:
    """Удаляет статус. Нельзя удалить единственный оставшийся."""
    name = name.strip()
    with _LOCK:
        data = _load()
        if name not in data["statuses"]:
            return False, data["statuses"]
        if len(data["statuses"]) <= 1:
            return False, data["statuses"]
        data["statuses"].remove(name)
        _save(data)
        return True, data["statuses"]

