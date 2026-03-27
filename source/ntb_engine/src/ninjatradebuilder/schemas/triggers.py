from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import field_validator

from .inputs import StrictModel


class RecheckAtTimeTrigger(StrictModel):
    trigger_family: Literal["recheck_at_time"]
    recheck_at_time: str

    @field_validator("recheck_at_time")
    @classmethod
    def _validate_iso_datetime(cls, value: str) -> str:
        if not value:
            raise ValueError("recheck_at_time must be a non-empty ISO datetime string.")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"recheck_at_time is not a valid ISO datetime: {value!r}"
            ) from exc
        return value


class PriceLevelTouchTrigger(StrictModel):
    trigger_family: Literal["price_level_touch"]
    price_level: float

    @field_validator("price_level", mode="before")
    @classmethod
    def _reject_bool(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("price_level must be a number, not a boolean.")
        return value


ReadinessTrigger = Union[RecheckAtTimeTrigger, PriceLevelTouchTrigger]


def validate_readiness_trigger(
    trigger: ReadinessTrigger | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a trigger payload at the boundary and return a clean dict.

    Accepts either a typed ReadinessTrigger model or a raw mapping.
    Returns a validated dict suitable for passing to downstream functions
    that expect ``Mapping[str, Any]``.
    """
    if isinstance(trigger, (RecheckAtTimeTrigger, PriceLevelTouchTrigger)):
        return trigger.model_dump()

    if not isinstance(trigger, Mapping):
        raise TypeError("Readiness trigger must be a mapping or ReadinessTrigger model.")

    family = trigger.get("trigger_family")
    if family == "recheck_at_time":
        return RecheckAtTimeTrigger.model_validate(dict(trigger)).model_dump()
    if family == "price_level_touch":
        return PriceLevelTouchTrigger.model_validate(dict(trigger)).model_dump()

    raise ValueError(
        f"Unsupported or missing trigger_family: {family!r}. "
        "Supported families: 'recheck_at_time', 'price_level_touch'."
    )


__all__ = [
    "PriceLevelTouchTrigger",
    "ReadinessTrigger",
    "RecheckAtTimeTrigger",
    "validate_readiness_trigger",
]
