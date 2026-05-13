from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final

from ntb_marimo_console.contract_universe import is_final_target_contract, normalize_contract_symbol


ANCHOR_INPUT_SCHEMA_VERSION: Final[int] = 1
ANCHOR_INPUT_PAYLOAD_TYPE: Final[str] = "ntb_marimo_console.anchor_inputs"
PRIMARY_ANCHOR_CONTRACT: Final[str] = "ES"
ANCHOR_INPUT_TARGET_CONTRACTS: Final[tuple[str, ...]] = ("NQ", "CL", "6E", "MGC")

_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "payload_type",
        "schema_version",
        "saved_at_utc",
        "anchors",
    }
)
_ANCHOR_KEYS: Final[frozenset[str]] = frozenset(
    {
        "contract",
        "key_levels",
        "session_high",
        "session_low",
        "correlation_anchor",
        "operator_note",
        "updated_at",
    }
)


@dataclass(frozen=True)
class AnchorInput:
    contract: str
    key_levels: tuple[float, ...]
    session_high: float | None
    session_low: float | None
    correlation_anchor: str | None
    operator_note: str
    updated_at: str

    def __post_init__(self) -> None:
        contract = _anchor_target_contract(self.contract)
        key_levels = _normalize_key_levels(self.key_levels)
        session_high = _optional_finite_float(self.session_high, "session_high")
        session_low = _optional_finite_float(self.session_low, "session_low")
        if session_high is not None and session_low is not None and session_high < session_low:
            raise ValueError("Anchor input session_high must be greater than or equal to session_low.")
        correlation_anchor = _optional_anchor_contract(self.correlation_anchor)
        operator_note = self.operator_note.strip()
        _validate_iso_datetime(self.updated_at, field_name="updated_at")

        object.__setattr__(self, "contract", contract)
        object.__setattr__(self, "key_levels", key_levels)
        object.__setattr__(self, "session_high", session_high)
        object.__setattr__(self, "session_low", session_low)
        object.__setattr__(self, "correlation_anchor", correlation_anchor)
        object.__setattr__(self, "operator_note", operator_note)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["key_levels"] = list(self.key_levels)
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> AnchorInput:
        if not isinstance(payload, Mapping):
            raise ValueError("Anchor input payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _ANCHOR_KEYS:
            raise ValueError("Anchor input payload keys are invalid.")
        key_levels = payload.get("key_levels")
        if not isinstance(key_levels, list):
            raise ValueError("Anchor input key_levels must be a list.")
        return cls(
            contract=_required_string(payload, "contract"),
            key_levels=tuple(_required_float(item, "key_levels") for item in key_levels),
            session_high=_optional_float(payload, "session_high"),
            session_low=_optional_float(payload, "session_low"),
            correlation_anchor=_optional_string(payload, "correlation_anchor"),
            operator_note=_required_string(payload, "operator_note"),
            updated_at=_required_string(payload, "updated_at"),
        )


class AnchorInputRegistry:
    def __init__(
        self,
        anchors: Iterable[AnchorInput] = (),
        *,
        clock: object | None = None,
    ) -> None:
        self._clock = clock or _utc_now
        self._anchors: dict[str, AnchorInput] = {}
        for anchor in anchors:
            if anchor.contract in self._anchors:
                raise ValueError(f"Duplicate anchor input contract: {anchor.contract}.")
            self._anchors[anchor.contract] = anchor

    def set(
        self,
        *,
        contract: str,
        key_levels: Iterable[float],
        session_high: float | None = None,
        session_low: float | None = None,
        correlation_anchor: str | None = PRIMARY_ANCHOR_CONTRACT,
        operator_note: str = "",
        updated_at: str | None = None,
    ) -> AnchorInput:
        anchor = AnchorInput(
            contract=contract,
            key_levels=tuple(key_levels),
            session_high=session_high,
            session_low=session_low,
            correlation_anchor=correlation_anchor,
            operator_note=operator_note,
            updated_at=updated_at or _isoformat_utc(self._clock()),
        )
        self._anchors[anchor.contract] = anchor
        return anchor

    def get(self, contract: str) -> AnchorInput | None:
        return self._anchors.get(normalize_contract_symbol(contract))

    def list(self) -> tuple[AnchorInput, ...]:
        return tuple(self._anchors[contract] for contract in ANCHOR_INPUT_TARGET_CONTRACTS if contract in self._anchors)

    def to_payload(self) -> dict[str, object]:
        return {
            "payload_type": ANCHOR_INPUT_PAYLOAD_TYPE,
            "schema_version": ANCHOR_INPUT_SCHEMA_VERSION,
            "saved_at_utc": _isoformat_utc(self._clock()),
            "anchors": [anchor.to_dict() for anchor in self.list()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True)

    @classmethod
    def from_payload(cls, payload: object, *, clock: object | None = None) -> AnchorInputRegistry:
        if not isinstance(payload, Mapping):
            raise ValueError("Anchor input registry payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _ROOT_KEYS:
            raise ValueError("Anchor input registry payload keys are invalid.")
        if payload.get("payload_type") != ANCHOR_INPUT_PAYLOAD_TYPE:
            raise ValueError("Anchor input registry payload type is unsupported.")
        if payload.get("schema_version") != ANCHOR_INPUT_SCHEMA_VERSION:
            raise ValueError("Anchor input registry schema version is unsupported.")
        saved_at_utc = payload.get("saved_at_utc")
        if not isinstance(saved_at_utc, str) or not saved_at_utc:
            raise ValueError("Anchor input registry saved_at_utc is invalid.")
        _validate_iso_datetime(saved_at_utc, field_name="saved_at_utc")
        anchors = payload.get("anchors")
        if not isinstance(anchors, list):
            raise ValueError("Anchor input registry anchors must be a list.")
        return cls((AnchorInput.from_payload(item) for item in anchors), clock=clock)

    @classmethod
    def from_json(cls, payload: str, *, clock: object | None = None) -> AnchorInputRegistry:
        return cls.from_payload(json.loads(payload), clock=clock)


def parse_key_levels_text(value: str) -> tuple[float, ...]:
    if not value.strip():
        return ()
    parts = tuple(part.strip() for part in value.split(","))
    levels = tuple(_required_float(part, "key_levels") for part in parts if part)
    return _normalize_key_levels(levels)


def anchor_inputs_payload_for_pipeline(registry: AnchorInputRegistry) -> dict[str, object]:
    return {
        "schema": ANCHOR_INPUT_PAYLOAD_TYPE,
        "schema_version": ANCHOR_INPUT_SCHEMA_VERSION,
        "primary_anchor_contract": PRIMARY_ANCHOR_CONTRACT,
        "required_for_contracts": list(ANCHOR_INPUT_TARGET_CONTRACTS),
        "anchors": {anchor.contract: anchor.to_dict() for anchor in registry.list()},
        "integration_status": "operator_context_available_not_gate_enforced",
    }


def _anchor_target_contract(contract: str) -> str:
    normalized = normalize_contract_symbol(contract)
    if normalized == PRIMARY_ANCHOR_CONTRACT:
        raise ValueError("ES is the primary anchor contract and does not accept anchor inputs.")
    if not is_final_target_contract(normalized) or normalized not in ANCHOR_INPUT_TARGET_CONTRACTS:
        raise ValueError(f"Anchor input contract is not an allowed cross-asset target: {normalized}.")
    return normalized


def _optional_anchor_contract(contract: str | None) -> str | None:
    if contract is None or not contract.strip():
        return None
    normalized = normalize_contract_symbol(contract)
    if not is_final_target_contract(normalized):
        raise ValueError(f"Anchor correlation contract is not in the final target universe: {normalized}.")
    return normalized


def _normalize_key_levels(values: Iterable[float]) -> tuple[float, ...]:
    normalized = tuple(_finite_float(value, "key_levels") for value in values)
    return tuple(sorted(dict.fromkeys(normalized)))


def _finite_float(value: object, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Anchor input {field_name} must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError(f"Anchor input {field_name} must be finite.")
    return result


def _optional_finite_float(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    return _finite_float(value, field_name)


def _required_float(value: object, field_name: str) -> float:
    return _finite_float(value, field_name)


def _optional_float(payload: Mapping[object, object], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    return _finite_float(value, key)


def _required_string(payload: Mapping[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Anchor input {key} must be a string.")
    return value


def _optional_string(payload: Mapping[object, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Anchor input {key} must be a string or null.")
    return value


def _validate_iso_datetime(value: str, *, field_name: str) -> None:
    if not value:
        raise ValueError(f"Anchor input {field_name} is required.")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Anchor input {field_name} must be an ISO datetime.") from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(value: object) -> str:
    if not isinstance(value, datetime):
        raise TypeError("Clock must return a datetime.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
