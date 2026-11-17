"""Gather what Home Assistant knows about an entity's value, to pre-fill the type questions."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import timedelta

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .registers import Evidence, decimals_of, to_float

_LOGGER = logging.getLogger(__name__)

HISTORY_TIMEOUT = 5  # seconds; the form opens without history rather than wait
HISTORY_DAYS = 30  # raw states; the recorder keeps 10 days by default
STATISTICS_DAYS = 365  # hourly min/max, kept for years: catches the other seasons


def _display_precision(hass: HomeAssistant, entity_id: str) -> int | None:
    """Decimals the user (or the integration) chose to display for a sensor."""
    entry = er.async_get(hass).async_get(entity_id)
    options = entry.options.get("sensor", {}) if entry else {}
    precision = options.get("display_precision")
    return precision if precision is not None else options.get("suggested_display_precision")


def _read_recorder(hass: HomeAssistant, entity_id: str) -> tuple[list, list, float | None]:
    """Numeric history values, statistics min/max and the oldest timestamp. Runs in the
    recorder's executor."""
    from homeassistant.components.recorder import history, statistics

    now = dt_util.utcnow()
    states = history.get_significant_states(
        hass,
        now - timedelta(days=HISTORY_DAYS),
        None,
        [entity_id],
        significant_changes_only=False,
        no_attributes=True,
    ).get(entity_id, [])
    values, oldest = [], None
    for state in states:
        if isinstance(state, State) and (value := to_float(state.state)) is not None:
            values.append((value, decimals_of(state.state)))
            oldest = min(oldest or state.last_changed.timestamp(), state.last_changed.timestamp())

    rows = statistics.statistics_during_period(
        hass,
        now - timedelta(days=STATISTICS_DAYS),
        None,
        {entity_id},
        "month",
        None,
        {"min", "max"},
    ).get(entity_id, [])
    extremes = []
    for row in rows:
        extremes += [v for v in (row.get("min"), row.get("max")) if v is not None]
        oldest = min(oldest or row["start"], row["start"])
    return values, extremes, oldest


async def _history_minmax(
    hass: HomeAssistant, entity_id: str
) -> tuple[float | None, float | None, int | None, int]:
    """(lowest, highest, most decimals, days covered) from the recorder."""
    from homeassistant.components.recorder import get_instance

    values, extremes, oldest = await get_instance(hass).async_add_executor_job(
        _read_recorder, hass, entity_id
    )
    numbers = [v for v, _ in values] + extremes
    if not numbers:
        return None, None, None, 0
    days = max(1, math.ceil((dt_util.utcnow().timestamp() - oldest) / 86400))
    decimals = max((d for _, d in values), default=None)
    return min(numbers), max(numbers), decimals, days


async def async_gather_evidence(hass: HomeAssistant, entity_id: str) -> Evidence:
    state = hass.states.get(entity_id)
    attrs = state.attributes if state else {}
    current = to_float(state.state) if state else None
    bounds = None
    if entity_id.split(".", 1)[0] in ("number", "input_number") and {"min", "max"} <= attrs.keys():
        bounds = (attrs["min"], attrs["max"])

    lo = hi = history_decimals = None
    days = 0
    if "recorder" in hass.config.components:
        try:
            async with asyncio.timeout(HISTORY_TIMEOUT):
                lo, hi, history_decimals, days = await _history_minmax(hass, entity_id)
        except Exception as err:  # noqa: BLE001 - a suggestion must never block the form
            _LOGGER.debug("No history for %s: %r", entity_id, err)
    seen = [v for v in (lo, hi, current) if v is not None]

    decimals = _display_precision(hass, entity_id)
    if decimals is None and "step" in attrs:
        decimals = decimals_of(attrs["step"])
    if decimals is None:
        decimals = history_decimals
    if decimals is None and current is not None:
        decimals = decimals_of(state.state)

    return Evidence(
        current=current,
        lo=min(seen) if seen else None,
        hi=max(seen) if seen else None,
        bounds=bounds,
        decimals=min(decimals, 3) if decimals is not None else None,
        device_class=attrs.get("device_class"),
        state_class=attrs.get("state_class"),
        history_days=days,
    )
