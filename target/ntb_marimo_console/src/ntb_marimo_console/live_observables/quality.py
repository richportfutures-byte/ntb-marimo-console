from __future__ import annotations

from typing import Final, Literal


ProviderStatusV2 = Literal["connected", "stale", "disconnected", "error", "disabled"]
SnapshotQualityState = Literal["ready", "blocked"]

CONTRACT_TICK_SIZES: Final[dict[str, float]] = {
    "ES": 0.25,
    "NQ": 0.25,
    "CL": 0.01,
    "6E": 0.00005,
    "MGC": 0.1,
}

PROVIDER_STATUS_BLOCKING_REASONS: Final[dict[ProviderStatusV2, str]] = {
    "disabled": "provider_disabled",
    "stale": "provider_stale",
    "disconnected": "provider_disconnected",
    "error": "provider_error",
}


def normalize_provider_status(status: object) -> ProviderStatusV2:
    normalized = str(status).strip().lower()
    if normalized in {"active", "connected"}:
        return "connected"
    if normalized in {"stale"}:
        return "stale"
    if normalized in {"disconnected", "blocked", "shutdown"}:
        return "disconnected"
    if normalized in {"error"}:
        return "error"
    return "disabled"


def provider_blocking_reason(status: ProviderStatusV2) -> str | None:
    return PROVIDER_STATUS_BLOCKING_REASONS.get(status)


def quality_state_from_reasons(blocking_reasons: tuple[str, ...]) -> SnapshotQualityState:
    return "blocked" if blocking_reasons else "ready"


def contract_tick_size(contract: str) -> float | None:
    return CONTRACT_TICK_SIZES.get(contract.strip().upper())
