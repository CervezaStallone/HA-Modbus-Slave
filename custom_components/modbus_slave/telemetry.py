"""Usage report, every 6 hours.

Opt-out: "share usage" is on unless the user unticks it. While at least one
config entry has it on, one report per
Home Assistant installation goes to the telemetry server. It holds only a
random installation ID and the integration version, so the server can count
active installations and versions; the server looks up the country itself.
Nothing about Modbus, entities, the network or Home Assistant is sent.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import aiohttp
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from .const import (
    CONF_SHARE_USAGE,
    DOMAIN,
    TELEMETRY_FIRST_DELAY,
    TELEMETRY_INTERVAL,
    TELEMETRY_SCHEMA,
    TELEMETRY_TIMEOUT,
    TELEMETRY_URL,
)

_LOGGER = logging.getLogger(__name__)


def build_report(install_id: str, integration_version: str) -> dict:
    """The random installation ID and the integration version: exactly these keys."""
    return {
        "schema": TELEMETRY_SCHEMA,
        "install_id": install_id.lower(),
        "integration_version": integration_version,
    }


class TelemetryReporter:
    """Sends the report unless every entry has opted out."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store = Store(hass, 1, f"{DOMAIN}.telemetry")
        self._unsubs: list = []

    async def async_install_id(self) -> str:
        """The random installation ID, created and saved on first use."""
        try:
            data = dict(await self._store.async_load() or {})
            return str(uuid.UUID(data["install_id"]))
        except Exception:  # noqa: BLE001 - missing or corrupt: start over
            install_id = str(uuid.uuid4())
            await self._store.async_save({"install_id": install_id})
            return install_id

    async def async_send(self, _now: Any = None) -> None:
        """Send one report; do nothing when every entry has opted out."""
        entries = self._hass.config_entries.async_entries(DOMAIN)
        if not any(e.data.get(CONF_SHARE_USAGE, True) for e in entries):
            return
        try:
            integration = await async_get_integration(self._hass, DOMAIN)
            async with async_get_clientsession(self._hass).post(
                TELEMETRY_URL,
                json=build_report(await self.async_install_id(), str(integration.version)),
                timeout=aiohttp.ClientTimeout(total=TELEMETRY_TIMEOUT),
            ) as response:
                if response.status >= 300:
                    _LOGGER.debug("Usage report rejected: HTTP %s", response.status)
        except Exception as err:  # noqa: BLE001 - never bother the user with it
            _LOGGER.debug("Usage report not sent: %r", err)

    @callback
    def async_start(self) -> None:
        """Schedule the first and the recurring report."""
        self._unsubs = [
            async_call_later(self._hass, TELEMETRY_FIRST_DELAY, self.async_send),
            async_track_time_interval(self._hass, self.async_send, TELEMETRY_INTERVAL),
        ]
        self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.async_stop)

    @callback
    def async_stop(self, _event: Any = None) -> None:
        """Cancel the scheduled reports."""
        while self._unsubs:
            self._unsubs.pop()()
