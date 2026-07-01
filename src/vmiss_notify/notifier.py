from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import request

from .config import AppConfig


class MessageApiError(RuntimeError):
    """Raised when the message API returns a non-zero errorCode."""


class JsonTransport(Protocol):
    def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        ...


class UrllibJsonTransport:
    def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        print(f"Message API request URL: {url}", flush=True)
        print(
            f"Message API request headers: {json.dumps(request_headers, ensure_ascii=False)}",
            flush=True,
        )
        print(f"Message API request payload: {json.dumps(payload, ensure_ascii=False)}", flush=True)
        req = request.Request(url, data=body, headers=request_headers, method="POST")
        with request.urlopen(req, timeout=30) as response:
            response_body = response.read().decode("utf-8")
        print(f"Message API response body: {response_body}", flush=True)
        return json.loads(response_body)


@dataclass
class TokenState:
    access_token: str
    corp_id: str
    refresh_at: float


class MessageNotifier:
    def __init__(
        self,
        config: AppConfig,
        transport: JsonTransport | None = None,
        clock=time.time,
    ) -> None:
        self._config = config
        self._transport = transport or UrllibJsonTransport()
        self._clock = clock
        self._token_state: TokenState | None = None

    def send_text(self, content: str) -> None:
        token = self._get_token()
        payload = {
            "toUser": self._config.message_to_users,
            "msgType": "text",
            "text": {"content": content},
            "accessToken": token.access_token,
            "corpId": token.corp_id,
        }
        response = self._transport.post_json(
            self._url("/cgi/message/send"),
            payload,
        )
        self._ensure_success(response)

    def _get_token(self) -> TokenState:
        now = self._clock()
        if self._token_state and now < self._token_state.refresh_at:
            return self._token_state

        payload = {
            "appId": self._config.message_app_id,
            "appSecret": self._config.message_app_secret,
            "permanentCode": self._config.message_permanent_code,
        }
        response = self._transport.post_json(self._url("/cgi/corpAccessToken/get/V2"), payload)
        self._ensure_success(response)

        access_token = str(response.get("corpAccessToken", ""))
        corp_id = str(response.get("corpId", ""))
        if not access_token or not corp_id:
            raise MessageApiError("Token response is missing corpAccessToken or corpId")

        expires_in = int(response.get("expiresIn", 7200))
        refresh_after = min(self._config.token_refresh_after_seconds, max(1, expires_in - 60))
        self._token_state = TokenState(access_token, corp_id, now + refresh_after)
        return self._token_state

    def _url(self, path: str) -> str:
        return f"https://{self._config.message_cloud_domain}{path}?thirdTraceId={uuid.uuid4().hex}"

    @staticmethod
    def _ensure_success(response: dict[str, Any]) -> None:
        if response.get("errorCode") == 0:
            return
        code = response.get("errorCode")
        message = response.get("errorMessage") or response.get("errorDescription") or response
        raise MessageApiError(f"Message API errorCode={code}: {message}")
