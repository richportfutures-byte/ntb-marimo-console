from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from .stream_lifecycle import StreamLifecycleState


StreamEventType = Literal[
    "login_requested",
    "login_succeeded",
    "login_denied",
    "subscription_requested",
    "subscription_succeeded",
    "subscription_failed",
    "data_received",
    "heartbeat_seen",
    "heartbeat_stale",
    "malformed_message",
    "connection_lost",
    "shutdown_requested",
    "shutdown_completed",
]

STREAM_EVENT_TYPES: Final[tuple[StreamEventType, ...]] = (
    "login_requested",
    "login_succeeded",
    "login_denied",
    "subscription_requested",
    "subscription_succeeded",
    "subscription_failed",
    "data_received",
    "heartbeat_seen",
    "heartbeat_stale",
    "malformed_message",
    "connection_lost",
    "shutdown_requested",
    "shutdown_completed",
)


@dataclass(frozen=True)
class StreamEvent:
    event_type: StreamEventType
    state: StreamLifecycleState
    provider: str
    summary: str
    generated_at: str
    symbols: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    blocking_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _safe_label(self.provider))
        object.__setattr__(self, "summary", redact_sensitive_text(self.summary))
        if self.blocking_reason is not None:
            object.__setattr__(self, "blocking_reason", redact_sensitive_text(self.blocking_reason))

    def to_dict(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "state": self.state,
            "provider": self.provider,
            "summary": self.summary,
            "generated_at": self.generated_at,
            "symbols": list(self.symbols),
            "services": list(self.services),
            "blocking_reason": self.blocking_reason,
        }


def redact_sensitive_text(value: object) -> str:
    text = str(value)
    text = re.sub(
        r"(?i)(access_token|refresh_token|auth(?:orization)?|secret|app_key|app_secret|credential|token)"
        r"([:=]\s*|=)([^&\s,}\"']+)",
        r"\1\2[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(customer|correl|account)[A-Za-z_ -]*(?:id|number)?([:=]\s*|=)([^&\s,}\"']+)",
        r"\1\2[REDACTED]",
        text,
    )
    text = re.sub(
        r'(?i)"(customerId|correlId|accountNumber|displayAcctId|Authorization)"\s*:\s*"[^"]+"',
        r'"\1":"[REDACTED]"',
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(wss?|https?)://[^\s,}\"']+", "[REDACTED_URL]", text)
    text = re.sub(
        r"\b(?=[A-Za-z0-9._~+/=-]{24,}\b)(?=[A-Za-z0-9._~+/=-]*[0-9./+=~-])[A-Za-z0-9._~+/=-]+\b",
        "[REDACTED_TOKEN_LIKE]",
        text,
    )
    return text[:300]


def _safe_label(value: object) -> str:
    label = str(value).strip() or "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", label)[:64]
