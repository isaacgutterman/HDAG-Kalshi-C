import httpx
import pytest

from app.client import KalshiHttpClient


class DummySigner:
    def build_auth_headers(self, method: str, url: str) -> dict[str, str]:
        return {
            "KALSHI-ACCESS-KEY": "test-key",
            "KALSHI-ACCESS-TIMESTAMP": "1703123456789",
            "KALSHI-ACCESS-SIGNATURE": f"{method}:{url}",
        }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_get_injects_auth_headers_when_authenticated() -> None:
    captured_headers: httpx.Headers | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = request.headers
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async with KalshiHttpClient(
        base_url="https://demo-api.kalshi.co",
        signer=DummySigner(),
        transport=transport,
    ) as client:
        response = await client.get("/trade-api/v2/portfolio/balance", authenticated=True)

    assert response.status_code == 200
    assert captured_headers is not None
    assert captured_headers["KALSHI-ACCESS-KEY"] == "test-key"
    assert captured_headers["KALSHI-ACCESS-TIMESTAMP"] == "1703123456789"
    assert "KALSHI-ACCESS-SIGNATURE" in captured_headers


@pytest.mark.anyio
async def test_get_retries_once_for_transient_server_error() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": "temporary"})

        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async with KalshiHttpClient(
        base_url="https://demo-api.kalshi.co",
        max_retries=1,
        retry_delay_seconds=0.0,
        transport=transport,
    ) as client:
        response = await client.get("/trade-api/v2/markets")

    assert attempts == 2
    assert response.status_code == 200


@pytest.mark.anyio
async def test_get_requires_signer_for_authenticated_requests() -> None:
    async with KalshiHttpClient(
        base_url="https://demo-api.kalshi.co",
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    ) as client:
        with pytest.raises(ValueError, match="KalshiSigner"):
            await client.get("/trade-api/v2/markets", authenticated=True)
