"""Config, reconfigure and options flows for Modbus Slave."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
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
    CONF_FLOAT_SUPPORT,
    CONF_HOST,
    CONF_MAPPINGS,
    CONF_PORT,
    CONF_SHARE_USAGE,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ID,
    DOMAIN,
    NON_NUMERIC_DEVICE_CLASSES,
    REG_WRITABLE_DOMAINS,
    SITE_URL,
)
from .registers import (
    Answers,
    DataType,
    Evidence,
    Mapping,
    TypeChoice,
    answers_from_mapping,
    choose_type,
    encode,
    find_overlap,
    first_free,
    has_numbers,
    master_view,
    suggest_answers,
)
from .server import parse_networks
from .suggest import async_gather_evidence

_AUTO = {"data_type": "auto", "scale": "1", "signed": False}  # Advanced section: no override


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
                CONF_FLOAT_SUPPORT, default=data.get(CONF_FLOAT_SUPPORT, False)
            ): BooleanSelector(),
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
        CONF_FLOAT_SUPPORT: bool(user_input.get(CONF_FLOAT_SUPPORT, False)),
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


def _unique_id(data: dict[str, Any]) -> str:
    return f"{data[CONF_PORT]}-{data[CONF_SLAVE_ID]}"


def _shared_port_error(hass, data: dict[str, Any], entry_id: str | None = None) -> str | None:
    """Slaves on one port share its listener, so they need its host and allowed IPs."""
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry_id or other.data[CONF_PORT] != data[CONF_PORT]:
            continue
        if other.data[CONF_SLAVE_ID] == data[CONF_SLAVE_ID]:
            return "slave_id_in_use"
        if other.data.get(CONF_HOST, "") != data[CONF_HOST] or sorted(
            other.data.get(CONF_ALLOWED_IPS, [])
        ) != sorted(data[CONF_ALLOWED_IPS]):
            return "port_settings_differ"
    return None


def _port_shared(hass, port: int, entry_id: str | None = None) -> bool:
    """Another entry already listens on this port (so it is ours, not free)."""
    return any(
        e.entry_id != entry_id and e.data[CONF_PORT] == port
        for e in hass.config_entries.async_entries(DOMAIN)
    )


def _title(slave_id: int, port: int) -> str:
    return f"Modbus Slave (port {port}, ID {slave_id})"


def _label(mapping: Mapping) -> str:
    space = "BIT" if mapping.space == "bits" else "REG"
    return f"{mapping.entity_id} → {space} {mapping.address}–{mapping.end} {mapping.data_type}"


class ModbusSlaveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up slave ID and port."""

    VERSION = 1
    MINOR_VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = _parse_server(user_input)
            if not error:
                await self.async_set_unique_id(_unique_id(data))
                self._abort_if_unique_id_configured()
                error = _shared_port_error(self.hass, data)
            if (
                not error
                and not _port_shared(self.hass, data[CONF_PORT])
                and not await _port_free(data[CONF_HOST], data[CONF_PORT])
            ):
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
                    CONF_SHARE_USAGE: False,
                }
            ),
            description_placeholders={"site_url": SITE_URL},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = _parse_server(user_input)
            if not error:
                error = _shared_port_error(self.hass, data, entry.entry_id)
            # an unchanged port is held by our own server, so it can't be checked
            if not error and data[CONF_PORT] != entry.data[CONF_PORT]:
                if not _port_shared(
                    self.hass, data[CONF_PORT], entry.entry_id
                ) and not await _port_free(data[CONF_HOST], data[CONF_PORT]):
                    error = "port_in_use"
            elif (
                not error
                and data[CONF_HOST]
                and data[CONF_HOST] != entry.data.get(CONF_HOST, "")
                and not await _port_free(data[CONF_HOST], 0)  # port 0: is the address ours?
            ):
                error = "invalid_host"
            if not error:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=_unique_id(data),
                    title=_title(data[CONF_SLAVE_ID], data[CONF_PORT]),
                    data=data,
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_server_schema(user_input or entry.data),
            description_placeholders={"site_url": SITE_URL},
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
        self._form: dict[str, Any] = {}  # confirm-step values plus "entity_id"
        self._evidence = Evidence()
        self._edit_index: int | None = None
        self._pending: dict[str, Any] | None = None  # input that got a notice instead of saving
        self._proposed: int | None = None  # address we filled in, until the user changes it

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
            domain = entity_id.split(".", 1)[0]
            evidence = await async_gather_evidence(self.hass, entity_id)
            # a sensor's device class says it is numeric even while unavailable; other
            # domains (cover, media_player, ...) have device classes with text states
            numeric = has_numbers(evidence) or (
                domain == "sensor"
                and evidence.device_class not in (None, *NON_NUMERIC_DEVICE_CLASSES)
            )
            if domain in BIT_DOMAINS or numeric:
                self._edit_index = None
                self._evidence = evidence
                self._form = self._prefill(
                    {"entity_id": entity_id, "address": 0}, suggest_answers(domain, evidence)
                )
                self._form["address"] = self._proposed = self._free_address(self._form)
                return await self.async_step_confirm()
            errors["base"] = "unsupported_entity"
        return self.async_show_form(
            step_id="add_mapping",
            data_schema=vol.Schema(
                {
                    vol.Required("entity"): EntitySelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._edit_index = int(user_input["mapping"])
            self._proposed = None
            mapping = self.mappings[self._edit_index]
            self._evidence = await async_gather_evidence(self.hass, mapping.entity_id)
            self._form = self._prefill(
                {
                    "entity_id": mapping.entity_id,
                    "address": mapping.address,
                    "writable": mapping.writable,
                    "fallback": mapping.fallback,
                },
                answers_from_mapping(mapping, self._evidence),
            )
            # unchanged answers must give back exactly the stored type: if Automatic would
            # pick another one, start the override on the stored type
            stored = TypeChoice(mapping.data_type, mapping.scale, mapping.signed)
            if self._choice(self._form) != stored:
                self._form["advanced"] = {
                    "data_type": str(mapping.data_type),
                    "scale": str(mapping.scale),
                    "signed": mapping.signed,
                }
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
            shown = self._choice(self._form)
            answers = ("negative", "decimals", "max_value")
            if user_input["advanced"] == self._form["advanced"] != _AUTO and any(
                user_input.get(k) != self._form.get(k) for k in answers
            ):
                # the user changed an answer, not the preset type: the answers win
                user_input = {**user_input, "advanced": _AUTO}
            self._form = {"entity_id": self._form["entity_id"], **user_input}
            if self._proposed is not None and int(user_input["address"]) == self._proposed:
                # address left as proposed: keep it the first free one for the new type
                user_input["address"] = self._form["address"] = self._free_address(self._form)
                self._proposed = user_input["address"]
            else:
                self._proposed = None  # the user picked an address: leave it alone
            choice = self._choice(self._form)
            confirmed = user_input == self._pending  # same input again: user saw the notice
            mapping = choice and Mapping(
                entity_id=self._form["entity_id"],
                address=int(user_input["address"]),
                data_type=choice.data_type,
                scale=choice.scale,
                signed=choice.signed,
                writable=user_input["writable"],
                fallback=user_input.get("fallback", 0),
            )
            if mapping is None:
                errors["base"] = "value_too_large"
            elif error := self._validate(mapping, placeholders):
                errors["base"] = error
            elif not confirmed and (warning := self._warning(user_input)):
                errors["base"] = warning
                self._pending = user_input
            elif (
                choice != shown and not confirmed and user_input["advanced"]["data_type"] == "auto"
            ):
                # no live preview in HA forms: show the new result before saving it
                errors["base"] = "result_changed"
                self._pending = user_input
            elif self._edit_index is None:
                self.mappings.append(mapping)
                return self._save()
            else:
                self.mappings[self._edit_index] = mapping
                return self._save()

        form = self._form
        fields: dict[Any, Any] = {
            vol.Required("address", default=form["address"]): _number(0, 65535)
        }
        if not self._is_bit:
            fields |= {
                vol.Required("negative", default=form["negative"]): BooleanSelector(),
                vol.Required("decimals", default=form["decimals"]): SelectSelector(
                    SelectSelectorConfig(
                        options=["0", "1", "2", "3"], mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required("max_value", default=form["max_value"]): NumberSelector(
                    NumberSelectorConfig(min=0, mode=NumberSelectorMode.BOX, step="any")
                ),
            }
        fields[vol.Required("writable", default=form["writable"])] = BooleanSelector()
        if not self._is_bit:
            fields[vol.Required("fallback", default=form["fallback"])] = NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, step="any")
            )
        advanced = form["advanced"]
        fields[vol.Required("advanced")] = section(
            vol.Schema(
                {
                    vol.Required("data_type", default=advanced["data_type"]): SelectSelector(
                        SelectSelectorConfig(
                            options=["auto", *(str(t) for t in DataType)],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="data_type",
                        )
                    ),
                    vol.Required("scale", default=advanced["scale"]): SelectSelector(
                        SelectSelectorConfig(
                            options=["1", "10", "100", "1000"], mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Required("signed", default=advanced["signed"]): BooleanSelector(),
                }
            ),
            {"collapsed": advanced["data_type"] == "auto"},  # an active override stays visible
        )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(fields),
            description_placeholders={**self._describe(form), **placeholders},
            errors=errors,
        )

    def _warning(self, user_input: dict[str, Any]) -> str:
        """An answer the evidence contradicts (not blocking: submitting again keeps it)."""
        if self._is_bit or user_input["advanced"]["data_type"] != "auto":
            return ""
        ev = self._evidence
        # a number's own range is the truth; its history can't widen it
        lows = (ev.bounds[0],) if ev.bounds else (ev.lo, ev.current)
        if not user_input["negative"] and any(v is not None and v < 0 for v in lows):
            return "warn_negative"
        seen = [abs(v) for v in (ev.bounds or (ev.lo, ev.hi)) if v is not None]
        if seen and float(user_input["max_value"]) < max(seen):
            return "warn_max"
        return ""

    def _free_address(self, form: dict[str, Any]) -> int:
        """First address where this type fits; unchanged when no type fits (validation says why)."""
        if (choice := self._choice(form)) is None:
            return int(form["address"])
        return first_free(self.mappings, Mapping(form["entity_id"], 0, choice.data_type))

    @property
    def _is_bit(self) -> bool:
        return self._form["entity_id"].split(".", 1)[0] in BIT_DOMAINS

    @staticmethod
    def _prefill(base: dict[str, Any], answers: Answers) -> dict[str, Any]:
        """Form values from the answers, plus the mapping's own settings."""
        return {
            "writable": False,
            "fallback": 0,
            "advanced": _AUTO,
            **base,
            "negative": answers.negative,
            "decimals": str(answers.decimals),
            "max_value": answers.max_value,
        }

    def _choice(self, form: dict[str, Any]) -> TypeChoice | None:
        advanced = form["advanced"]
        if advanced["data_type"] != "auto":  # expert override, used as given
            return TypeChoice(
                DataType(advanced["data_type"]), int(advanced["scale"]), bool(advanced["signed"])
            )
        if self._is_bit:
            return TypeChoice(DataType.BIT)
        answers = Answers(bool(form["negative"]), int(form["decimals"]), float(form["max_value"]))
        return choose_type(answers, self.config_entry.data.get(CONF_FLOAT_SUPPORT, False))

    def _describe(self, form: dict[str, Any]) -> dict[str, str]:
        """Placeholders: what the entity reports and what the master will read."""
        ev = self._evidence

        def num(value: float | None) -> str:
            return "–" if value is None else f"{value:g}"

        text = {
            "entity": form["entity_id"],
            "current": num(ev.current),
            "lo": num(ev.lo),
            "hi": num(ev.hi),
            "days": str(ev.history_days),
            "result_type": "–",
            "registers": "–",
            "example_value": "–",
            "example_words": "–",
        }
        choice = self._choice(form)
        if choice is None:
            return text
        example = Mapping(form["entity_id"], 0, choice.data_type, choice.scale, choice.signed)
        if self._is_bit:
            value = "on"
        else:
            sample = next((v for v in (ev.current, ev.hi) if v is not None), None)
            value = num(sample if sample is not None else float(form["max_value"]))
        words, _ = encode(example, value)
        text |= {
            "result_type": master_view(example),
            "registers": str(example.size),
            "example_value": value,
            "example_words": " ".join(str(int(w)) for w in words),
        }
        return text

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
