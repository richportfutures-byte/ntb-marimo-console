from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .stream_events import redact_sensitive_text


ProviderStatus = Literal["disabled", "connected", "active", "stale", "blocked", "error", "shutdown"]
StreamMessageType = Literal["quote", "bar"]
JsonScalar = str | int | float | bool | None


@dataclass(frozen=True)
class NormalizedStreamMessage:
    provider: str
    service: str
    symbol: str
    contract: str
    message_type: StreamMessageType
    fields: Mapping[str, object]
    received_at: str


@dataclass(frozen=True)
class StreamCacheRecord:
    provider: str
    service: str
    symbol: str
    contract: str
    message_type: StreamMessageType
    fields: tuple[tuple[str, JsonScalar], ...]
    updated_at: str
    age_seconds: float | None
    fresh: bool
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "service": self.service,
            "symbol": self.symbol,
            "contract": self.contract,
            "message_type": self.message_type,
            "fields": dict(self.fields),
            "updated_at": self.updated_at,
            "age_seconds": self.age_seconds,
            "fresh": self.fresh,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class StreamCacheSnapshot:
    generated_at: str
    provider: str
    provider_status: ProviderStatus
    cache_max_age_seconds: float
    records: tuple[StreamCacheRecord, ...]
    blocking_reasons: tuple[str, ...]
    stale_symbols: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return (
            self.provider_status == "active"
            and bool(self.records)
            and not self.blocking_reasons
            and not self.stale_symbols
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "provider": self.provider,
            "provider_status": self.provider_status,
            "cache_max_age_seconds": self.cache_max_age_seconds,
            "ready": self.ready,
            "records": [record.to_dict() for record in self.records],
            "blocking_reasons": list(self.blocking_reasons),
            "stale_symbols": list(self.stale_symbols),
        }


class StreamCache:
    def __init__(
        self,
        *,
        provider: str,
        cache_max_age_seconds: float,
        clock: object | None = None,
    ) -> None:
        self._provider = _safe_label(provider)
        self._cache_max_age_seconds = cache_max_age_seconds
        self._clock = clock or _utc_now
        self._provider_status: ProviderStatus = "disabled"
        self._records: dict[tuple[str, str, str], NormalizedStreamMessage] = {}
        self._blocking_reasons: list[str] = []
        self._symbol_blocking_reasons: dict[str, list[str]] = {}

    @property
    def provider_status(self) -> ProviderStatus:
        return self._provider_status

    def set_provider_status(self, status: ProviderStatus) -> None:
        self._provider_status = status

    def put_message(self, message: NormalizedStreamMessage) -> None:
        key = (
            message.contract.strip().upper(),
            message.symbol.strip().upper(),
            message.service.strip().upper(),
        )
        self._records[key] = message

    def add_blocking_reason(self, reason: object, *, symbol: str | None = None) -> None:
        safe_reason = redact_sensitive_text(reason)
        if safe_reason not in self._blocking_reasons:
            self._blocking_reasons.append(safe_reason)
        if symbol:
            normalized_symbol = symbol.strip().upper()
            reasons = self._symbol_blocking_reasons.setdefault(normalized_symbol, [])
            if safe_reason not in reasons:
                reasons.append(safe_reason)

    def snapshot(self) -> StreamCacheSnapshot:
        now = self._clock()
        generated_at = _isoformat(now)
        records: list[StreamCacheRecord] = []
        stale_symbols: list[str] = []
        for message in sorted(
            self._records.values(),
            key=lambda item: (item.contract.strip().upper(), item.symbol.strip().upper(), item.service),
        ):
            age_seconds = _age_seconds(message.received_at, now=now)
            fresh = age_seconds is not None and age_seconds <= self._cache_max_age_seconds
            normalized_symbol = message.symbol.strip().upper()
            if not fresh and normalized_symbol not in stale_symbols:
                stale_symbols.append(normalized_symbol)
            records.append(
                StreamCacheRecord(
                    provider=_safe_label(message.provider),
                    service=_safe_label(message.service),
                    symbol=normalized_symbol,
                    contract=message.contract.strip().upper(),
                    message_type=message.message_type,
                    fields=_safe_fields(message.fields),
                    updated_at=message.received_at,
                    age_seconds=age_seconds,
                    fresh=fresh,
                    blocking_reasons=tuple(self._symbol_blocking_reasons.get(normalized_symbol, ())),
                )
            )

        status = self._provider_status
        if status == "active" and stale_symbols:
            status = "stale"

        return StreamCacheSnapshot(
            generated_at=generated_at,
            provider=self._provider,
            provider_status=status,
            cache_max_age_seconds=self._cache_max_age_seconds,
            records=tuple(records),
            blocking_reasons=tuple(self._blocking_reasons),
            stale_symbols=tuple(stale_symbols),
        )


def _safe_fields(fields: Mapping[str, object]) -> tuple[tuple[str, JsonScalar], ...]:
    normalized: list[tuple[str, JsonScalar]] = []
    for key, value in fields.items():
        normalized.append((_safe_label(key), _safe_scalar(value)))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _safe_scalar(value: object) -> JsonScalar:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return redact_sensitive_text(value)


def _age_seconds(value: str, *, now: datetime) -> float | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (now.astimezone(timezone.utc) - parsed).total_seconds())


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _safe_label(value: object) -> str:
    return redact_sensitive_text(value).strip()[:96] or "unknown"
