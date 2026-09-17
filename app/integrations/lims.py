"""HTTP client for pushing completed results to LIMS."""

from typing import Any

import httpx


class LimsClientError(RuntimeError):
    """Raised when the configured LIMS endpoint cannot accept results."""


class HttpLimsClient:
    def __init__(self, result_url: str, timeout: float = 10.0) -> None:
        self.result_url = result_url
        self.timeout = timeout

    async def push_results(self, payload: dict[str, Any], idempotency_key: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.result_url,
                    json=payload,
                    headers={"X-Idempotency-Key": idempotency_key},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LimsClientError(str(exc)) from exc
