"""Config flow for Rain Bird IQ4."""

from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urljoin

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    AUTH_METHOD_PASSWORD,
    AUTH_METHOD_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_AUTH_METHOD,
    CONF_DEFAULT_DURATION,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_EXPIRES_AT,
    CONF_TOKEN_INPUT,
    DATA_TOKEN_SESSIONS,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    FRONTEND_URL_PATH,
    MIN_SCAN_INTERVAL_MINUTES,
    TOKEN_HELPER_FILENAME,
)
from .frontend import async_register_frontend
from .iq4_client import (
    IQ4AuthError,
    IQ4CannotConnectError,
    IQ4Client,
    IQ4Error,
    IQ4TokenExpiredError,
    IQ4WafChallengeError,
    build_browser_authorization_url,
    extract_access_token,
    jwt_expiration,
    jwt_identity,
)

TOKEN_SESSION_TTL_SECONDS = 30 * 60


async def _validate_input(hass: HomeAssistant, username: str, password: str) -> None:
    session = async_get_clientsession(hass)
    client = IQ4Client(session, username, password)
    await client.async_validate()


async def _validate_token(hass: HomeAssistant, token: str) -> None:
    session = async_get_clientsession(hass)
    client = IQ4Client(session, access_token=token, token_expiration=jwt_expiration(token))
    await client.async_validate()


def _token_expired(token: str) -> bool:
    expires_at = jwt_expiration(token)
    return expires_at is not None and expires_at <= int(time.time()) + 60


class RainBirdIQ4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rain Bird IQ4."""

    VERSION = 1

    _entry_name: str = DEFAULT_NAME
    _reauth_entry: config_entries.ConfigEntry | None = None
    _username_hint: str | None = None
    _authorization_url: str | None = None
    _token_session_id: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> RainBirdIQ4OptionsFlow:
        return RainBirdIQ4OptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._entry_name = user_input[CONF_NAME]
            if user_input[CONF_AUTH_METHOD] == AUTH_METHOD_PASSWORD:
                return await self.async_step_password()
            return await self.async_step_browser_token()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                    vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_TOKEN): vol.In(
                        {
                            AUTH_METHOD_TOKEN: "Browser token",
                            AUTH_METHOD_PASSWORD: "Username and password",
                        }
                    ),
                }
            ),
        )

    async def async_step_password(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await _validate_input(self.hass, username, password)
            except IQ4WafChallengeError:
                self._username_hint = username
                return await self.async_step_browser_token()
            except IQ4AuthError:
                errors["base"] = "invalid_auth"
            except IQ4CannotConnectError:
                errors["base"] = "cannot_connect"
            except IQ4Error:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=self._entry_name,
                    data={
                        CONF_NAME: self._entry_name,
                        CONF_AUTH_METHOD: AUTH_METHOD_PASSWORD,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                    options={
                        CONF_DEFAULT_DURATION: DEFAULT_DURATION_MINUTES,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
                    },
                )

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_browser_token(self, user_input: dict[str, Any] | None = None):
        await async_register_frontend(self.hass)
        errors: dict[str, str] = {}

        if user_input is not None:
            token = extract_access_token(user_input.get(CONF_TOKEN_INPUT)) or self._get_captured_token()
            if not token:
                errors["base"] = "token_missing"
            elif _token_expired(token):
                errors["base"] = "token_expired"
            else:
                try:
                    await _validate_token(self.hass, token)
                except IQ4TokenExpiredError:
                    errors["base"] = "invalid_token"
                except IQ4AuthError:
                    errors["base"] = "invalid_token"
                except IQ4CannotConnectError:
                    errors["base"] = "cannot_connect"
                except IQ4Error:
                    errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"
                else:
                    return await self._async_finish_token_flow(token)

        return self.async_show_form(
            step_id="browser_token",
            data_schema=vol.Schema({vol.Optional(CONF_TOKEN_INPUT, default=""): cv.string}),
            errors=errors,
            description_placeholders={
                "authorization_url": self._get_authorization_url(),
                "token_helper_url": self._get_token_helper_url(),
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._entry_name = entry_data.get(CONF_NAME, DEFAULT_NAME)
        self._username_hint = entry_data.get(CONF_USERNAME)
        return await self.async_step_browser_token()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if self._reauth_entry is not None:
            self._entry_name = self._reauth_entry.data.get(CONF_NAME, DEFAULT_NAME)
            self._username_hint = self._reauth_entry.data.get(CONF_USERNAME)
        return await self.async_step_browser_token(user_input)

    async def _async_finish_token_flow(self, token: str):
        token_expiration = jwt_expiration(token)
        token_identity = jwt_identity(token) or self._username_hint
        entry_data = {
            CONF_NAME: self._entry_name,
            CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
            CONF_ACCESS_TOKEN: token,
        }
        if token_identity:
            entry_data[CONF_USERNAME] = token_identity
        if token_expiration is not None:
            entry_data[CONF_TOKEN_EXPIRES_AT] = token_expiration

        if self._reauth_entry is not None:
            updated_data = {**self._reauth_entry.data, **entry_data}
            updated_data.pop(CONF_PASSWORD, None)
            if token_expiration is None:
                updated_data.pop(CONF_TOKEN_EXPIRES_AT, None)
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data=updated_data,
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            self._clear_token_session()
            if self.context.get("source") == config_entries.SOURCE_RECONFIGURE:
                return self.async_abort(reason="reconfigure_successful")
            return self.async_abort(reason="reauth_successful")

        await self.async_set_unique_id((token_identity or self._entry_name).lower())
        self._abort_if_unique_id_configured()
        self._clear_token_session()
        return self.async_create_entry(
            title=self._entry_name,
            data=entry_data,
            options={
                CONF_DEFAULT_DURATION: DEFAULT_DURATION_MINUTES,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
            },
        )

    def _get_authorization_url(self) -> str:
        if not self._authorization_url:
            self._authorization_url = build_browser_authorization_url()
        return self._authorization_url

    def _get_token_helper_url(self) -> str:
        if not self._token_session_id:
            self._token_session_id = secrets.token_urlsafe(24)
            sessions = self.hass.data.setdefault(DOMAIN, {}).setdefault(DATA_TOKEN_SESSIONS, {})
            _purge_old_token_sessions(sessions)
            sessions[self._token_session_id] = {"created_at": time.time()}
        path = f"{FRONTEND_URL_PATH}/{TOKEN_HELPER_FILENAME}?session={self._token_session_id}"
        try:
            base_url = get_url(
                self.hass,
                allow_internal=False,
                allow_external=True,
                prefer_external=True,
            )
        except NoURLAvailableError:
            return path
        return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))

    def _get_captured_token(self) -> str | None:
        if not self._token_session_id:
            return None
        sessions = self.hass.data.setdefault(DOMAIN, {}).setdefault(DATA_TOKEN_SESSIONS, {})
        _purge_old_token_sessions(sessions)
        session = sessions.get(self._token_session_id)
        if not isinstance(session, dict):
            return None
        token = session.get("token")
        return token if isinstance(token, str) else None

    def _clear_token_session(self) -> None:
        if not self._token_session_id:
            return
        sessions = self.hass.data.setdefault(DOMAIN, {}).setdefault(DATA_TOKEN_SESSIONS, {})
        sessions.pop(self._token_session_id, None)


def _purge_old_token_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    cutoff = time.time() - TOKEN_SESSION_TTL_SECONDS
    for session_id, session in list(sessions.items()):
        timestamp = session.get("updated_at") or session.get("created_at") or 0
        if not isinstance(timestamp, (int, float)) or timestamp < cutoff:
            sessions.pop(session_id, None)


class RainBirdIQ4OptionsFlow(config_entries.OptionsFlow):
    """Handle options for Rain Bird IQ4."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEFAULT_DURATION,
                        default=options.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=720)),
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=60)),
                }
            ),
        )
