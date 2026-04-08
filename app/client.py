from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.auth import KalshiSigner

logger = logging.getLogger(__name__)


class KalshiHttpClient:
    def __init__(
        self,
        base_url: str,
        signer: KalshiSigner | None = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.25,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._signer = signer
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> KalshiHttpClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> httpx.Response:
        request_url = self._build_url(path)
        headers = self._build_headers(method="GET", url=request_url, authenticated=authenticated)

        for attempt in range(1, self._max_retries + 2):
            try:
                logger.info(
                    "Sending Kalshi GET request",
                    extra={"method": "GET", "url": request_url, "attempt": attempt},
                )
                response = await self._client.get(path, params=params, headers=headers)
                if self._should_retry_response(response, attempt):
                    await self._log_and_wait_for_retry(
                        reason=f"http_{response.status_code}",
                        method="GET",
                        url=request_url,
                        attempt=attempt,
                    )
                    continue

                response.raise_for_status()
                return response
            except httpx.RequestError as exc:
                if attempt > self._max_retries:
                    logger.warning(
                        "Kalshi GET request failed after retries",
                        extra={
                            "method": "GET",
                            "url": request_url,
                            "attempt": attempt,
                            "error": str(exc),
                        },
                    )
                    raise

                await self._log_and_wait_for_retry(
                    reason=exc.__class__.__name__,
                    method="GET",
                    url=request_url,
                    attempt=attempt,
                )

        raise RuntimeError("Retry loop exited unexpectedly")

    def _build_url(self, path: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self._base_url}{normalized_path}"

    def _build_headers(
        self,
        method: str,
        url: str,
        authenticated: bool,
    ) -> dict[str, str]:
        if not authenticated:
            return {}

        if self._signer is None:
            raise ValueError("Authenticated request requires a KalshiSigner")

        return self._signer.build_auth_headers(method=method, url=url)

    def _should_retry_response(self, response: httpx.Response, attempt: int) -> bool:
        return attempt <= self._max_retries and response.status_code in {
            429,
            500,
            502,
            503,
            504,
        }

    async def _log_and_wait_for_retry(
        self,
        reason: str,
        method: str,
        url: str,
        attempt: int,
    ) -> None:
        logger.warning(
            "Retrying Kalshi request after transient failure",
            extra={"method": method, "url": url, "attempt": attempt, "reason": reason},
        )
        await asyncio.sleep(self._retry_delay_seconds)
