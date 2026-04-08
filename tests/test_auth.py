import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.auth import KalshiSigner


def test_extract_path_excludes_query_parameters() -> None:
    url = "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders?limit=5&cursor=abc"

    path = KalshiSigner.extract_path(url)

    assert path == "/trade-api/v2/portfolio/orders"


def test_sign_generates_valid_signature_for_timestamp_method_and_path(
    tmp_path: Path,
) -> None:
    key_path, private_key = _write_private_key(tmp_path)
    signer = KalshiSigner(api_key_id="test-api-key", private_key_path=key_path)
    timestamp_ms = 1703123456789
    method = "get"
    url = "https://demo-api.kalshi.co/trade-api/v2/portfolio/balance?foo=bar"

    signature = signer.sign(method=method, url=url, timestamp_ms=timestamp_ms)

    private_key.public_key().verify(
        base64.b64decode(signature),
        b"1703123456789GET/trade-api/v2/portfolio/balance",
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )


def test_build_auth_headers_returns_expected_header_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = _build_test_signer(tmp_path, monkeypatch=monkeypatch)

    headers = signer.build_auth_headers(
        method="POST",
        url="https://demo-api.kalshi.co/trade-api/v2/portfolio/orders?limit=1",
        timestamp_ms=1703123456789,
    )

    assert set(headers) == {
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-TIMESTAMP",
        "KALSHI-ACCESS-SIGNATURE",
    }
    assert headers["KALSHI-ACCESS-KEY"] == "test-api-key"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1703123456789"
    assert isinstance(headers["KALSHI-ACCESS-SIGNATURE"], str)
    assert headers["KALSHI-ACCESS-SIGNATURE"]


def test_build_auth_headers_uses_string_millisecond_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = _build_test_signer(tmp_path, monkeypatch=monkeypatch, signature_bytes=b"sig")
    monkeypatch.setattr(KalshiSigner, "current_timestamp_ms", staticmethod(lambda: 1703123456789))

    headers = signer.build_auth_headers(
        method="GET",
        url="https://demo-api.kalshi.co/trade-api/v2/portfolio/balance?foo=bar",
    )

    assert isinstance(headers["KALSHI-ACCESS-TIMESTAMP"], str)
    assert headers["KALSHI-ACCESS-TIMESTAMP"].isdigit()
    assert len(headers["KALSHI-ACCESS-TIMESTAMP"]) == 13


def _write_private_key(tmp_path: Path) -> tuple[Path, rsa.RSAPrivateKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "kalshi-test-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return key_path, private_key


def _build_test_signer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    signature_bytes: bytes = b"test-signature",
) -> KalshiSigner:
    class DummyPrivateKey:
        def sign(
            self,
            message: bytes,
            padding_scheme: padding.AsymmetricPadding,
            algorithm: hashes.HashAlgorithm,
        ) -> bytes:
            return signature_bytes

    monkeypatch.setattr(
        KalshiSigner,
        "_load_private_key",
        staticmethod(lambda private_key_path: DummyPrivateKey()),
    )

    return KalshiSigner(
        api_key_id="test-api-key",
        private_key_path=tmp_path / "unused-test-key.pem",
    )
