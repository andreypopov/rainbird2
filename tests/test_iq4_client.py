"""Tests for Rain Bird IQ4 token parsing helpers."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "rainbird_iq4"))
sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))

from iq4_client import CLIENT_ID, extract_access_token  # noqa: E402


def _jwt(payload: dict[str, object]) -> str:
    def encode(value: dict[str, object]) -> str:
        data = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.sig"


ACCESS_TOKEN = _jwt(
    {
        "aud": ["coreAPI"],
        "scope": "coreAPI.read coreAPI.write openid profile",
        "exp": 4102444800,
    }
)
ID_TOKEN = _jwt({"aud": CLIENT_ID, "sub": "user", "exp": 4102444800})


def test_extracts_access_token_from_final_url() -> None:
    value = f"https://iq4.rainbird.com/auth.html#id_token={ID_TOKEN}&access_token={ACCESS_TOKEN}"

    assert extract_access_token(value) == ACCESS_TOKEN


def test_extracts_access_token_from_url_encoded_final_url() -> None:
    value = (
        "https%3A%2F%2Fiq4.rainbird.com%2Fauth.html%23"
        f"id_token%3D{ID_TOKEN}%26access_token%3D{ACCESS_TOKEN}%26token_type%3DBearer"
    )

    assert extract_access_token(value) == ACCESS_TOKEN


def test_extracts_access_token_from_json_payload() -> None:
    value = json.dumps({"id_token": ID_TOKEN, "access_token": ACCESS_TOKEN})

    assert extract_access_token(value) == ACCESS_TOKEN


def test_extracts_access_token_from_bearer_text() -> None:
    assert extract_access_token(f"Bearer {ACCESS_TOKEN}") == ACCESS_TOKEN


def test_prefers_core_api_token_when_unlabeled() -> None:
    assert extract_access_token(f"{ID_TOKEN}\n{ACCESS_TOKEN}") == ACCESS_TOKEN
