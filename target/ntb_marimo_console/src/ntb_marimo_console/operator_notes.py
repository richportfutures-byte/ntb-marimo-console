from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Final, Literal
from uuid import uuid4

from ntb_marimo_console.contract_universe import is_final_target_contract, normalize_contract_symbol


OPERATOR_NOTE_SCHEMA_VERSION: Final[int] = 1
OPERATOR_NOTE_PAYLOAD_TYPE: Final[str] = "ntb_marimo_console.operator_notes"

OperatorNoteCategory = Literal["pre_market", "intraday", "post_session", "general"]

_NOTE_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"pre_market", "intraday", "post_session", "general"}
)
_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "payload_type",
        "schema_version",
        "saved_at_utc",
        "notes",
    }
)
_NOTE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "note_id",
        "timestamp",
        "category",
        "contract",
        "content",
        "tags",
    }
)


@dataclass(frozen=True)
class OperatorNote:
    note_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: _isoformat_utc(_utc_now()))
    category: OperatorNoteCategory = "general"
    contract: str | None = None
    content: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        note_id = self.note_id.strip()
        category = self.category.strip().lower()
        contract = _optional_final_target_contract(self.contract)
        content = self.content.strip()
        tags = _normalize_tags(self.tags)

        if not note_id:
            raise ValueError("Operator note note_id is required.")
        _validate_iso_datetime(self.timestamp, field_name="timestamp")
        if category not in _NOTE_CATEGORIES:
            raise ValueError("Operator note category must be pre_market, intraday, post_session, or general.")
        if not content:
            raise ValueError("Operator note content is required.")

        object.__setattr__(self, "note_id", note_id)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "contract", contract)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "tags", tags)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> OperatorNote:
        if not isinstance(payload, Mapping):
            raise ValueError("Operator note payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _NOTE_KEYS:
            raise ValueError("Operator note payload keys are invalid.")
        tags = payload.get("tags")
        if not isinstance(tags, list):
            raise ValueError("Operator note tags must be a list.")
        return cls(
            note_id=_required_string(payload, "note_id"),
            timestamp=_required_string(payload, "timestamp"),
            category=_required_string(payload, "category"),  # type: ignore[arg-type]
            contract=_optional_string(payload, "contract"),
            content=_required_string(payload, "content"),
            tags=tuple(_required_string_value(item, "tags") for item in tags),
        )


class OperatorNotesRegistry:
    def __init__(
        self,
        notes: Iterable[OperatorNote] = (),
        *,
        clock: object | None = None,
    ) -> None:
        self._clock = clock or _utc_now
        self._notes: dict[str, OperatorNote] = {}
        for note in notes:
            if note.note_id in self._notes:
                raise ValueError(f"Duplicate operator note id: {note.note_id}.")
            self._notes[note.note_id] = note

    def add(
        self,
        *,
        content: str,
        category: OperatorNoteCategory = "general",
        contract: str | None = None,
        tags: Iterable[str] = (),
        timestamp: str | None = None,
        note_id: str | None = None,
    ) -> OperatorNote:
        note = OperatorNote(
            note_id=note_id or uuid4().hex,
            timestamp=timestamp or _isoformat_utc(self._clock()),
            category=category,
            contract=contract,
            content=content,
            tags=tuple(tags),
        )
        if note.note_id in self._notes:
            raise ValueError(f"Duplicate operator note id: {note.note_id}.")
        self._notes[note.note_id] = note
        return note

    def list(self) -> tuple[OperatorNote, ...]:
        return tuple(
            sorted(
                self._notes.values(),
                key=lambda note: (_datetime_sort_key(note.timestamp), note.note_id),
            )
        )

    def list_by_category(self, category: OperatorNoteCategory) -> tuple[OperatorNote, ...]:
        category_key = _note_category(category)
        return tuple(note for note in self.list() if note.category == category_key)

    def list_by_contract(self, contract: str) -> tuple[OperatorNote, ...]:
        contract_key = _final_target_contract(contract)
        return tuple(note for note in self.list() if note.contract == contract_key)

    def to_payload(self) -> dict[str, object]:
        return {
            "payload_type": OPERATOR_NOTE_PAYLOAD_TYPE,
            "schema_version": OPERATOR_NOTE_SCHEMA_VERSION,
            "saved_at_utc": _isoformat_utc(self._clock()),
            "notes": [note.to_dict() for note in self.list()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True)

    def export_json(self) -> str:
        return self.to_json()

    @classmethod
    def from_payload(cls, payload: object, *, clock: object | None = None) -> OperatorNotesRegistry:
        if not isinstance(payload, Mapping):
            raise ValueError("Operator note registry payload must be a mapping.")
        if frozenset(str(key) for key in payload.keys()) != _ROOT_KEYS:
            raise ValueError("Operator note registry payload keys are invalid.")
        if payload.get("payload_type") != OPERATOR_NOTE_PAYLOAD_TYPE:
            raise ValueError("Operator note registry payload type is unsupported.")
        if payload.get("schema_version") != OPERATOR_NOTE_SCHEMA_VERSION:
            raise ValueError("Operator note registry schema version is unsupported.")
        saved_at_utc = payload.get("saved_at_utc")
        if not isinstance(saved_at_utc, str) or not saved_at_utc:
            raise ValueError("Operator note registry saved_at_utc is invalid.")
        _validate_iso_datetime(saved_at_utc, field_name="saved_at_utc")
        notes = payload.get("notes")
        if not isinstance(notes, list):
            raise ValueError("Operator note registry notes must be a list.")
        return cls((OperatorNote.from_payload(item) for item in notes), clock=clock)

    @classmethod
    def from_json(cls, payload: str, *, clock: object | None = None) -> OperatorNotesRegistry:
        return cls.from_payload(json.loads(payload), clock=clock)


def parse_tags_text(value: str) -> tuple[str, ...]:
    return _normalize_tags(part for part in value.split(","))


def _note_category(category: str) -> str:
    normalized = category.strip().lower()
    if normalized not in _NOTE_CATEGORIES:
        raise ValueError("Operator note category must be pre_market, intraday, post_session, or general.")
    return normalized


def _final_target_contract(contract: str) -> str:
    normalized = normalize_contract_symbol(contract)
    if not is_final_target_contract(normalized):
        raise ValueError(f"Operator note contract is not in the final target universe: {normalized}.")
    return normalized


def _optional_final_target_contract(contract: str | None) -> str | None:
    if contract is None or not contract.strip():
        return None
    return _final_target_contract(contract)


def _normalize_tags(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip()
        if not tag or tag in seen:
            continue
        normalized.append(tag)
        seen.add(tag)
    return tuple(normalized)


def _required_string(payload: Mapping[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Operator note {key} must be a string.")
    return value


def _required_string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Operator note {field_name} must contain only strings.")
    return value


def _optional_string(payload: Mapping[object, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Operator note {key} must be a string or null.")
    return value


def _validate_iso_datetime(value: str, *, field_name: str) -> None:
    if not value:
        raise ValueError(f"Operator note {field_name} is required.")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Operator note {field_name} must be an ISO datetime.") from exc


def _datetime_sort_key(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(value: object) -> str:
    if not isinstance(value, datetime):
        raise TypeError("Clock must return a datetime.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
