"""Async client for the Rain Bird IQ4 cloud API."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json as jsonlib
import logging
import random
import re
import secrets
import string
import time
from typing import Any
from urllib.parse import parse_qsl, unquote, unquote_plus, urlencode, urljoin, urlsplit

import aiohttp

_LOGGER = logging.getLogger(__name__)

AUTH_BASE = "https://iq4server.rainbird.com/coreidentityserver"
API_BASE = "https://iq4server.rainbird.com/coreapi/api"
CLIENT_ID = "C5A6F324-3CD3-4B22-9F78-B4835BA55D25"
REDIRECT_URI = "https://iq4.rainbird.com/auth.html"
SCOPE = "coreAPI.read coreAPI.write openid profile"
RESPONSE_TYPE = "id_token token"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

TOKEN_RE = re.compile(
    r"(?:^|[?&#\s\"'])access[_-]?token\s*[:=]\s*[\"']?([^&\"'#<>\s]+)",
    re.IGNORECASE,
)
BEARER_RE = re.compile(
    r"\bbearer\s+([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?)",
    re.IGNORECASE,
)
JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?$")
JWT_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?)(?![A-Za-z0-9_-])"
)
ANTIFORGERY_RE = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'
    r'|value="([^"]+)"[^>]*name="__RequestVerificationToken"',
    re.IGNORECASE | re.DOTALL,
)


class IQ4Error(Exception):
    """Base IQ4 error."""


class IQ4AuthError(IQ4Error):
    """Authentication failed."""


class IQ4TokenExpiredError(IQ4AuthError):
    """A manually supplied IQ4 access token expired."""


class IQ4CannotConnectError(IQ4Error):
    """Could not reach IQ4."""


class IQ4WafChallengeError(IQ4Error):
    """Rain Bird returned an AWS WAF challenge."""


class IQ4ApiError(IQ4Error):
    """IQ4 API returned an error."""


def _random_hex(bytes_count: int = 8) -> str:
    return secrets.token_hex(bytes_count)


def _random_browser_uuid() -> str:
    alphabet = string.hexdigits.lower()
    parts = (8, 4, 4, 4, 12)
    return "-".join("".join(random.choice(alphabet) for _ in range(part)) for part in parts)


def build_browser_authorization_url() -> str:
    """Return a Rain Bird login URL that ends at a browser-visible access token."""
    return_url = _build_authorize_return_url(_random_hex(), _random_hex())
    return f"{AUTH_BASE}/Account/Login?{urlencode({'ReturnUrl': return_url})}"


def extract_access_token(value: str | None) -> str | None:
    """Extract an IQ4 API access token from pasted browser or helper output."""
    if not value:
        return None

    candidates: list[tuple[int, int, str]] = []
    seen_values: set[str] = set()

    def add_candidate(token: Any, score: int = 0, source: str = "") -> None:
        if not isinstance(token, str):
            return
        clean = _clean_token_candidate(token)
        if not clean or clean in seen_values or not JWT_RE.fullmatch(clean):
            return
        seen_values.add(clean)
        candidates.append((score + _score_token_candidate(clean, source), len(candidates), clean))

    def inspect_text(text: str, score: int = 0) -> None:
        text = text.strip()
        if not text:
            return

        add_candidate(text, score + 30, text)

        if text.lower().startswith("bearer "):
            add_candidate(text[7:], score - 20, text)

        for match in BEARER_RE.finditer(text):
            add_candidate(match.group(1), score - 15, text)

        for chunk in _text_variants(text):
            _extract_from_json(chunk, add_candidate, score - 35)
            _extract_from_url_parts(chunk, add_candidate, score - 30)
            for match in TOKEN_RE.finditer(chunk):
                add_candidate(match.group(1), score - 25, chunk)

        for match in JWT_CANDIDATE_RE.finditer(text):
            add_candidate(match.group(1), score + 45, text)

    inspect_text(str(value))

    if not candidates:
        return None

    return sorted(candidates)[0][2]


def _clean_token_candidate(value: str) -> str:
    value = value.strip().strip("\"'`")
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    for _ in range(3):
        decoded = unquote_plus(value).strip().strip("\"'`")
        if decoded == value:
            break
        value = decoded
    return value.rstrip(".,;)")


def _text_variants(value: str) -> list[str]:
    variants = [value]
    current = value
    for _ in range(3):
        decoded = unquote_plus(current)
        if decoded == current:
            break
        variants.append(decoded)
        current = decoded
    return variants


def _extract_from_json(
    value: str,
    add_candidate: Any,
    score: int,
    *,
    depth: int = 0,
) -> None:
    if depth > 4:
        return
    try:
        parsed = jsonlib.loads(value)
    except (TypeError, ValueError, jsonlib.JSONDecodeError):
        return
    _walk_token_data(parsed, add_candidate, score, depth)


def _walk_token_data(value: Any, add_candidate: Any, score: int, depth: int) -> None:
    if depth > 5:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if normalized_key == "access_token":
                add_candidate(item, score - 20, str(key))
            elif isinstance(item, str):
                _extract_from_json(item, add_candidate, score + 5, depth=depth + 1)
            else:
                _walk_token_data(item, add_candidate, score + 5, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _walk_token_data(item, add_candidate, score + 5, depth + 1)
    elif isinstance(value, str):
        _extract_from_json(value, add_candidate, score + 5, depth=depth + 1)


def _extract_from_url_parts(value: str, add_candidate: Any, score: int) -> None:
    parts = [value]
    try:
        split = urlsplit(value)
    except ValueError:
        split = None
    if split is not None:
        parts.extend(part for part in (split.query, split.fragment) if part)

    for part in parts:
        if "=" not in part:
            continue
        for key, item in parse_qsl(part, keep_blank_values=True):
            normalized_key = key.lower().replace("-", "_")
            if normalized_key == "access_token":
                add_candidate(item, score - 20, key)


def _score_token_candidate(token: str, source: str = "") -> int:
    score = 0
    source_lower = source.lower()
    if "access_token" in source_lower or "access-token" in source_lower:
        score -= 20
    data = jwt_payload(token)
    haystack = jsonlib.dumps(data, separators=(",", ":"), sort_keys=True).lower()
    if "coreapi" in haystack or "coreapi.read" in haystack or "coreapi.write" in haystack:
        score -= 40
    if CLIENT_ID.lower() in haystack and "coreapi" not in haystack:
        score += 35
    exp = data.get("exp")
    if isinstance(exp, (int, float)) and exp <= int(time.time()) + 60:
        score += 100
    return score


def jwt_expiration(token: str) -> int | None:
    """Return the Unix expiration timestamp from a JWT, if present."""
    data = jwt_payload(token)
    exp = data.get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None


def jwt_identity(token: str) -> str | None:
    """Return the most stable account identifier available in a JWT."""
    data = jwt_payload(token)
    for key in ("email", "preferred_username", "name", "sub"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def jwt_payload(token: str) -> dict[str, Any]:
    """Decode the payload portion of a JWT without validating its signature."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode())
        data = jsonlib.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, ValueError, jsonlib.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _build_authorize_return_url(state: str, nonce: str) -> str:
    return (
        "/coreidentityserver/connect/authorize/callback?"
        + urlencode(
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "response_type": RESPONSE_TYPE,
                "scope": SCOPE,
                "state": state,
                "nonce": nonce,
            }
        )
    )


def _extract_access_token(value: str | None) -> str | None:
    return extract_access_token(value)


def _extract_antiforgery_token(html: str) -> str | None:
    match = ANTIFORGERY_RE.search(html)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _jwt_expiration(token: str) -> int | None:
    return jwt_expiration(token)


class IQ4Client:
    """Small async client for the Rain Bird IQ4 cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        *,
        access_token: str | None = None,
        token_expiration: int | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token = access_token
        self._token_expiration = token_expiration or (
            _jwt_expiration(access_token) if access_token else None
        )
        self._browser_tab_uuid = _random_browser_uuid()

    async def async_validate(self) -> None:
        """Validate credentials and API access."""
        await self._ensure_token()
        await self.get_controllers()

    async def async_authenticate(self) -> str:
        """Authenticate with IQ4 and return a bearer token."""
        if not self._username or not self._password:
            raise IQ4TokenExpiredError("Rain Bird IQ4 browser token expired or was rejected")

        state = _random_hex()
        nonce = _random_hex()
        return_url = _build_authorize_return_url(state, nonce)
        login_url = f"{AUTH_BASE}/Account/Login?{urlencode({'ReturnUrl': return_url})}"

        timeout = aiohttp.ClientTimeout(total=45)
        headers = {"User-Agent": USER_AGENT}
        jar = aiohttp.CookieJar(unsafe=True)

        try:
            async with aiohttp.ClientSession(
                cookie_jar=jar,
                headers=headers,
                timeout=timeout,
            ) as auth_session:
                async with auth_session.get(login_url, allow_redirects=True) as response:
                    await self._raise_for_waf(response)
                    login_html = await response.text()

                antiforgery = _extract_antiforgery_token(login_html)
                if not antiforgery:
                    raise IQ4AuthError("Could not find IQ4 login verification token")

                form = {
                    "Username": self._username,
                    "Password": self._password,
                    "ReturnUrl": return_url,
                    "__RequestVerificationToken": antiforgery,
                }
                async with auth_session.post(
                    login_url,
                    data=form,
                    allow_redirects=False,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ) as response:
                    await self._raise_for_waf(response)
                    token = await self._token_from_response(auth_session, response)
        except IQ4Error:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise IQ4CannotConnectError(f"Could not connect to IQ4 login service: {err}") from err

        if not token:
            raise IQ4AuthError("IQ4 login failed")

        self._token = token
        self._token_expiration = _jwt_expiration(token)
        return token

    async def _token_from_response(
        self,
        auth_session: aiohttp.ClientSession,
        response: aiohttp.ClientResponse,
    ) -> str | None:
        """Follow redirects manually until an access token appears."""
        candidates: list[str] = [str(response.url), response.headers.get("Location", "")]
        body = await response.text()
        candidates.append(body)
        for candidate in candidates:
            if token := _extract_access_token(candidate):
                return token

        current_url = str(response.url)
        location = response.headers.get("Location")
        for _ in range(10):
            if not location:
                return None
            next_url = urljoin(current_url, location)
            if token := _extract_access_token(next_url):
                return token
            current_url = next_url
            async with auth_session.get(next_url, allow_redirects=False) as next_response:
                await self._raise_for_waf(next_response)
                if token := _extract_access_token(str(next_response.url)):
                    return token
                if token := _extract_access_token(next_response.headers.get("Location")):
                    return token
                text = await next_response.text()
                if token := _extract_access_token(text):
                    return token
                location = next_response.headers.get("Location")

        raise IQ4AuthError("Too many IQ4 login redirects")

    @staticmethod
    async def _raise_for_waf(response: aiohttp.ClientResponse) -> None:
        if response.status == 202 or response.headers.get("x-amzn-waf-action") == "challenge":
            await response.read()
            raise IQ4WafChallengeError("IQ4 login is protected by an AWS WAF challenge")

    def _token_valid(self) -> bool:
        if not self._token:
            return False
        if self._token_expiration is None:
            return True
        return self._token_expiration > int(time.time()) + 60

    async def _ensure_token(self) -> str:
        if self._token_valid():
            return self._token or ""
        if not self._username or not self._password:
            raise IQ4TokenExpiredError("Rain Bird IQ4 browser token expired")
        return await self.async_authenticate()

    async def _api_request(
        self,
        method: str,
        path: str,
        json_body: Any | None = None,
        *,
        manual_ops_headers: bool = False,
        retry_auth: bool = True,
    ) -> Any:
        token = await self._ensure_token()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if manual_ops_headers:
            headers.update(
                {
                    "x-rbcc-client-request-sent-utc-ms": str(int(time.time() * 1000)),
                    "browser-tab-uuid": self._browser_tab_uuid,
                }
            )

        url = f"{API_BASE}{path}"
        try:
            async with self._session.request(
                method,
                url,
                json=json_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                text = await response.text()
                if response.status in (401, 403) and retry_auth:
                    self._token = None
                    self._token_expiration = None
                    if not self._username or not self._password:
                        raise IQ4TokenExpiredError("Rain Bird IQ4 browser token was rejected")
                    return await self._api_request(
                        method,
                        path,
                        json_body,
                        manual_ops_headers=manual_ops_headers,
                        retry_auth=False,
                    )
                if response.status >= 400:
                    raise IQ4ApiError(f"IQ4 API error {response.status}: {text[:500]}")
                if not text:
                    return None
                try:
                    return jsonlib.loads(text)
                except jsonlib.JSONDecodeError:
                    return text
        except IQ4Error:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise IQ4CannotConnectError(f"Could not connect to IQ4 API: {err}") from err

    async def get_sites(self) -> list[dict[str, Any]]:
        return await self._api_request("GET", "/Site/GetSites") or []

    async def get_controllers(self) -> list[dict[str, Any]]:
        return await self._api_request("GET", "/Satellite/GetSatelliteList") or []

    async def get_connection_statuses(self, controller_ids: list[int]) -> dict[int, bool]:
        if not controller_ids:
            return {}
        query = urlencode([("satelliteIds", controller_id) for controller_id in controller_ids])
        data = await self._api_request("GET", f"/Satellite/isConnected?{query}") or {}
        satellites = data.get("satellites", data if isinstance(data, list) else [])
        return {
            int(item["id"]): bool(item.get("isConnected"))
            for item in satellites
            if isinstance(item, dict) and item.get("id") is not None
        }

    async def get_stations(self, controller_id: int) -> list[dict[str, Any]]:
        return await self._api_request(
            "GET", f"/Station/GetStationListForSatellite?satelliteId={controller_id}"
        ) or []

    async def get_programs(self, controller_id: int) -> list[dict[str, Any]]:
        return await self._api_request(
            "GET", f"/Program/GetProgramList?satelliteId={controller_id}"
        ) or []

    async def start_stations(
        self,
        station_ids: list[int],
        seconds: list[int],
        *,
        is_group_start: bool = False,
    ) -> None:
        payload = {
            "stationIds": station_ids,
            "seconds": seconds,
            "isGroupStart": is_group_start,
        }
        await self._api_request(
            "POST",
            "/ManualOps/StartStations",
            payload,
            manual_ops_headers=True,
        )

    async def stop_stations(self, station_ids: list[int]) -> None:
        await self._api_request("POST", "/ManualOps/StopStations", station_ids)

    async def stop_all_irrigation(self, controller_ids: list[int]) -> None:
        await self._api_request("POST", "/Satellite/StopAllIrrigation", controller_ids)

    async def set_rain_delay(self, controller_id: int, days: int) -> None:
        await self._api_request(
            "POST",
            f"/ManualOps/SendRainDelay?satelliteId={controller_id}&days={days}",
        )
