from __future__ import annotations

import base64
import time
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class KalshiSigner:
    def __init__(self, api_key_id: str, private_key_path: str | Path) -> None:
        self._api_key_id = api_key_id
        self._private_key_path = Path(private_key_path)
        self._private_key = self._load_private_key(self._private_key_path)

    @staticmethod
    def current_timestamp_ms() -> int:
        return time.time_ns() // 1_000_000

    @staticmethod
    def extract_path(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return parsed.path or "/"

        return url.split("?", maxsplit=1)[0] or "/"

    def sign(self, method: str, url: str, timestamp_ms: int) -> str:
        path = self.extract_path(url)
        message = f"{timestamp_ms}{method.upper()}{path}".encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

        return base64.b64encode(signature).decode("utf-8")

    def build_auth_headers(
        self,
        method: str,
        url: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        resolved_timestamp_ms = (
            timestamp_ms if timestamp_ms is not None else self.current_timestamp_ms()
        )
        signature = self.sign(method=method, url=url, timestamp_ms=resolved_timestamp_ms)

        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(resolved_timestamp_ms),
            "KALSHI-ACCESS-SIGNATURE": signature,
        }

    @staticmethod
    def _load_private_key(private_key_path: Path) -> rsa.RSAPrivateKey:
        private_key_bytes = private_key_path.read_bytes()
        private_key = serialization.load_pem_private_key(
            private_key_bytes,
            password=None,
        )

        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise TypeError("Expected an RSA private key")

        return private_key
