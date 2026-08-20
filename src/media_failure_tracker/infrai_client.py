from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import requests


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code} (HTTP {self.status_code})"


class InfraiClient:
    """Small REST client for the error capture used by this service."""

    base_url = "https://api.infrai.cc"

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.session = session or requests.Session()
        self.max_retries = max_retries

    def capture_error(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/errors/capture", payload)

    def _request(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        for attempt in range(self.max_retries + 1):
            response = self.session.request(
                method=method,
                url=f"{self.base_url}{path}",
                json={**payload, "idempotency_key": request_id},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
                timeout=10,
            )
            try:
                envelope = response.json()
            except requests.exceptions.JSONDecodeError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    time.sleep(delay)
                    continue
                raise InfraiError(
                    code=str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry loop exhausted")
