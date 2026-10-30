"""Config, reconfigure and options flows for Modbus Slave."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    BIT_DOMAINS,
    BIT_WRITABLE_DOMAINS,
    CONF_ALLOWED_IPS,
    CONF_HOST,
    CONF_MAPPINGS,
    CONF_PORT,
    CONF_SHARE_USAGE,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ID,
    DOMAIN,
    PRIVACY_URL,
    REG_WRITABLE_DOMAINS,
)
from .registers import DataType, Mapping, detect, find_overlap
from .server import parse_networks


def _number(lo: int, hi: int) -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=lo, max=hi, step=1, mode=NumberSelectorMode.BOX))


def _server_schema(data: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_SLAVE_ID, default=data[CONF_SLAVE_ID]): _number(1, 247),
            vol.Required(CONF_PORT, default=data[CONF_PORT]): _number(1, 65535),
            vol.Optional(CONF_HOST, default=data.get(CONF_HOST, "")): TextSelector(),
            vol.Optional(
                CONF_ALLOWED_IPS, default=", ".join(data.get(CONF_ALLOWED_IPS, []))
            ): TextSelector(),
            vol.Optional(
                CONF_SHARE_USAGE, default=data.get(CONF_SHARE_USAGE, False)
            ): BooleanSelector(),
        }
    )


def _parse_server(user_input: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Turn the server form into entry data, or return an error key."""
    host = user_input.get(CONF_HOST, "").strip()
    try:
        if host:
            ipaddress.ip_address(host)
    except ValueError:
        return {}, "invalid_host"
    try:
        allowed = parse_networks(user_input.get(CONF_ALLOWED_IPS, ""))
    except ValueError:
        return {}, "invalid_allowed_ips"
    return {
        CONF_SLAVE_ID: int(user_input[CONF_SLAVE_ID]),
        CONF_PORT: int(user_input[CONF_PORT]),
        CONF_HOST: host,
        CONF_ALLOWED_IPS: allowed,
        CONF_SHARE_USAGE: bool(user_input.get(CONF_SHARE_USAGE, False)),
    }, None


async def _port_free(host: str, port: int) -> bool:
    try:
        server = await asyncio.start_server(lambda _r, _w: None, host=host or None, port=port)
    except OSError:
        return False
    server.close()
    await server.wait_closed()
    return True


def _title(slave_id: int, port: int) -> str:
    return f"Modbus Slave (port {port}, ID {slave_id})"


def _label(mapping: Mapping) -> str:
    space = "BIT" if mapping.space == "bits" else "REG"
    return f"{mapping.entity_id} → {space} {mapping.address}–{mapping.end} {mapping.data_type}"


class ModbusSlaveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up slave ID and port."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = _parse_server(user_input)
            if not error:
                await self.async_set_unique_id(str(data[CONF_PORT]))
                self._abort_if_unique_id_configured()
                if not await _port_free(data[CONF_HOST], data[CONF_PORT]):
                    error = "port_in_use"
            if not error:
                return self.async_create_entry(
                    title=_title(data[CONF_SLAVE_ID], data[CONF_PORT]),
                    data=data,
                    options={CONF_MAPPINGS: []},
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=_server_schema(
                user_input
                or {
                    CONF_SLAVE_ID: DEFAULT_SLAVE_ID,
                    CONF_PORT: DEFAULT_PORT,
                    CONF_SHARE_USAGE: True,
                }
            ),
            description_placeholders={"privacy_url": PRIVACY_URL},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = _parse_server(user_input)
            # an unchanged port is held by our own server, so it can't be checked
            if not error and data[CONF_PORT] != entry.data[CONF_PORT]:
                await self.async_set_unique_id(str(data[CONF_PORT]))
                self._abort_if_unique_id_configured()
                if not await _port_free(data[CONF_HOST], data[CONF_PORT]):
                    error = "port_in_use"
            if not error:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=str(data[CONF_PORT]),
                    title=_title(data[CONF_SLAVE_ID], data[CONF_PORT]),
                    data=data,
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_server_schema(user_input or entry.data),
            description_placeholders={"privacy_url": PRIVACY_URL},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ModbusSlaveOptionsFlow()


class ModbusSlaveOptionsFlow(OptionsFlow):
    """Add, edit and remove entity mappings."""

    def __init__(self) -> None:
        self._mappings: list[Mapping] | None = None
        self._draft: dict[str, Any] = {}
        self._edit_index: int | None = None

    @property
    def mappings(self) -> list[Mapping]:
        if self._mappings is None:
            self._mappings = [
                Mapping.from_dict(d) for d in self.config_entry.options.get(CONF_MAPPINGS, [])
            ]
        return self._mappings

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data={CONF_MAPPINGS: [m.as_dict() for m in self.mappings]})

    def _options(self) -> list[dict[str, str]]:
        return [
            {
                "value": str(i),
                "label": _label(m) + ("" if self.hass.states.get(m.entity_id) else " (missing)"),
            }
            for i, m in enumerate(self.mappings)
        ]

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["add_mapping"]
        if self.mappings:
            menu += ["edit_mapping", "remove_mapping"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input["entity"]
            state = self.hass.states.get(entity_id)
            detected = state and detect(
                entity_id.split(".", 1)[0], state.state, dict(state.attributes)
            )
            if detected:
                self._edit_index = None
                self._draft = {
                    "entity_id": entity_id,
                    "address": int(user_input["address"]),
                    **detected,
                }
                return await self.async_step_confirm()
            errors["base"] = "unsupported_entity"
        return self.async_show_form(
            step_id="add_mapping",
            data_schema=vol.Schema(
                {
                    vol.Required("entity"): EntitySelector(),
                    vol.Required("address", default=0): _number(0, 65535),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._edit_index = int(user_input["mapping"])
            self._draft = self.mappings[self._edit_index].as_dict()
            return await self.async_step_confirm()
        return self.async_show_form(
            step_id="edit_mapping",
            data_schema=vol.Schema(
                {
                    vol.Required("mapping"): SelectSelector(
                        SelectSelectorConfig(options=self._options())
                    )
                }
            ),
        )

    async def async_step_remove_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            remove = {int(i) for i in user_input["mappings"]}
            self._mappings = [m for i, m in enumerate(self.mappings) if i not in remove]
            return self._save()
        return self.async_show_form(
            step_id="remove_mapping",
            data_schema=vol.Schema(
                {
                    vol.Required("mappings"): SelectSelector(
                        SelectSelectorConfig(
                            options=self._options(),
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"conflict": ""}
        if user_input is not None:
            mapping = Mapping(
                entity_id=self._draft["entity_id"],
                address=int(user_input["address"]),
                data_type=user_input["data_type"],
                scale=int(user_input["scale"]),
                signed=user_input["signed"],
                writable=user_input["writable"],
                fallback=user_input["fallback"],
            )
            if error := self._validate(mapping, placeholders):
                errors["base"] = error
                self._draft = mapping.as_dict()
            elif self._edit_index is None:
                self.mappings.append(mapping)
                return self._save()
            else:
                self.mappings[self._edit_index] = mapping
                return self._save()

        draft = Mapping.from_dict(self._draft)
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("address", default=draft.address): _number(0, 65535),
                    vol.Required("data_type", default=str(draft.data_type)): SelectSelector(
                        SelectSelectorConfig(
                            options=[str(t) for t in DataType], mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Required("scale", default=str(draft.scale)): SelectSelector(
                        SelectSelectorConfig(
                            options=["1", "10", "100", "1000"], mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Required("signed", default=draft.signed): BooleanSelector(),
                    vol.Required("writable", default=draft.writable): BooleanSelector(),
                    vol.Required("fallback", default=draft.fallback): NumberSelector(
                        NumberSelectorConfig(mode=NumberSelectorMode.BOX, step="any")
                    ),
                }
            ),
            description_placeholders={
                "entity": draft.entity_id,
                "summary": _label(draft),
                **placeholders,
            },
            errors=errors,
        )

    def _validate(self, mapping: Mapping, placeholders: dict[str, str]) -> str:
        domain = mapping.entity_id.split(".", 1)[0]
        is_bit = mapping.data_type == DataType.BIT
        if is_bit != (domain in BIT_DOMAINS):
            return "type_mismatch"
        if mapping.writable and domain not in (
            BIT_WRITABLE_DOMAINS if is_bit else REG_WRITABLE_DOMAINS
        ):
            return "not_writable"
        if mapping.end > 65535:
            return "address_out_of_range"
        if conflict := find_overlap(self.mappings, mapping, self._edit_index):
            placeholders["conflict"] = conflict.entity_id
            return "address_overlap"
        return ""
