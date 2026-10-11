import base64
import os
import ssl
import threading
import time
import uuid

import httpx
from dotenv import load_dotenv

DEFAULT_TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_API_URL = "https://api.giga.chat/v1"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_MODEL = "GigaChat"
DEFAULT_TIMEOUT = 60
TOKEN_REFRESH_MARGIN = 60


class GigaChatError(Exception):
    pass


def _verify_param():
    mode = (os.getenv("GIGACHAT_VERIFY_SSL") or "system").lower()
    if mode in ("0", "false", "no"):
        return False
    bundle = os.getenv("GIGACHAT_CA_BUNDLE")
    if bundle:
        return bundle
    if mode == "certifi":
        return True
    context = ssl.create_default_context()
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return context


class GigaChatClient:
    def __init__(
        self,
        auth_key: str | None = None,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
        model: str | None = None,
        token_url: str | None = None,
        api_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        env_file: str | None = None,
    ):
        if env_file:
            load_dotenv(env_file)

        auth_key = auth_key or os.getenv("GIGACHAT_AUTH_KEY")
        client_id = client_id or os.getenv("GIGACHAT_CLIENT_ID")
        client_secret = client_secret or os.getenv("GIGACHAT_CLIENT_SECRET")
        if not auth_key and client_id and client_secret:
            auth_key = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        if not auth_key:
            raise GigaChatError(
                "Нет ключа GigaChat: задай GIGACHAT_AUTH_KEY "
                "(или GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET) в .env"
            )

        self._auth_key = auth_key
        self.scope = scope or os.getenv("GIGACHAT_SCOPE", DEFAULT_SCOPE)
        self.model = model or os.getenv("GIGACHAT_MODEL", DEFAULT_MODEL)
        self.token_url = token_url or os.getenv("GIGACHAT_TOKEN_URL", DEFAULT_TOKEN_URL)
        self.api_url = (api_url or os.getenv("GIGACHAT_API_URL", DEFAULT_API_URL)).rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at = 0.0
        self.last_model: str | None = None
        self._lock = threading.Lock()

    def _fetch_token(self) -> tuple[str, float]:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self._auth_key}",
        }
        with httpx.Client(timeout=self.timeout, trust_env=False, verify=_verify_param()) as client:
            response = client.post(self.token_url, headers=headers, data={"scope": self.scope})
        if response.status_code != 200:
            raise GigaChatError(f"Не удалось получить токен GigaChat: HTTP {response.status_code}")
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise GigaChatError("В ответе нет access_token")
        expires_at = float(data.get("expires_at") or 0)
        if expires_at > 1e12:
            expires_at /= 1000.0
        if not expires_at:
            expires_at = time.time() + 1800
        return token, expires_at

    def _get_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expires_at - TOKEN_REFRESH_MARGIN:
                return self._token
            self._token, self._token_expires_at = self._fetch_token()
            return self._token

    def _invalidate_token(self) -> None:
        with self._lock:
            self._token = None
            self._token_expires_at = 0.0

    def _request(self, path: str, payload: dict) -> dict:
        for attempt in range(2):
            token = self._get_token()
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            with httpx.Client(timeout=self.timeout, trust_env=False, verify=_verify_param()) as client:
                response = client.post(f"{self.api_url}{path}", headers=headers, json=payload)
            if response.status_code == 401 and attempt == 0:
                self._invalidate_token()
                continue
            if response.status_code != 200:
                raise GigaChatError(f"GigaChat API: HTTP {response.status_code}")
            return response.json()
        raise GigaChatError("GigaChat API: авторизация не прошла")

    def chat(self, messages: list[dict], model: str | None = None, **params) -> str:
        payload = {"model": model or self.model, "messages": messages, "stream": False}
        payload.update(params)
        data = self._request("/chat/completions", payload)
        self.last_model = data.get("model")
        choices = data.get("choices") or []
        if not choices:
            raise GigaChatError("Пустой ответ модели")
        content = (choices[0].get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise GigaChatError("Пустой ответ модели")
        return content.strip()

    def ask(self, text: str, system: str | None = None, **params) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        return self.chat(messages, **params)

    def models(self) -> list[str]:
        for attempt in range(2):
            token = self._get_token()
            with httpx.Client(timeout=self.timeout, trust_env=False, verify=_verify_param()) as client:
                response = client.get(
                    f"{self.api_url}/models",
                    headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                )
            if response.status_code == 401 and attempt == 0:
                self._invalidate_token()
                continue
            if response.status_code != 200:
                raise GigaChatError(f"GigaChat API: HTTP {response.status_code}")
            return [item.get("id", "") for item in response.json().get("data", [])]
        raise GigaChatError("GigaChat API: авторизация не прошла")


def load_client(env_file: str | None = None) -> GigaChatClient:
    return GigaChatClient(env_file=env_file)
