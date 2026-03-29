from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .session_evidence import (
    SESSION_EVIDENCE_LIMIT,
    deserialize_session_evidence_payload,
    serialize_session_evidence_payload,
    SessionEvidenceRecord,
)

SESSION_EVIDENCE_STORE_ENV: Final[str] = "NTB_CONSOLE_EVIDENCE_STORE_PATH"
SESSION_EVIDENCE_STORE_RELATIVE_PATH: Final[Path] = Path(".state") / "recent_session_evidence.v1.json"


@dataclass(frozen=True)
class SessionEvidenceRestoreSnapshot:
    history: tuple[SessionEvidenceRecord, ...]
    persistence_path: str
    restore_status: str
    restore_message: str


@dataclass(frozen=True)
class SessionEvidencePersistenceStatus:
    persistence_path: str
    health_status: str
    last_status: str
    last_message: str
    last_persisted_at_utc: str | None


def resolve_session_evidence_store_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()

    from_env = os.environ.get(SESSION_EVIDENCE_STORE_ENV)
    if from_env:
        return Path(from_env).expanduser().resolve()

    test_path = _test_scoped_store_path()
    if test_path is not None:
        return test_path

    return (_target_root() / SESSION_EVIDENCE_STORE_RELATIVE_PATH).resolve()


def restore_session_evidence_history(
    *,
    path: str | Path | None = None,
) -> SessionEvidenceRestoreSnapshot:
    resolved_path = resolve_session_evidence_store_path(path)
    if not resolved_path.exists():
        return SessionEvidenceRestoreSnapshot(
            history=tuple(),
            persistence_path=str(resolved_path),
            restore_status="RESTORE_MISSING",
            restore_message=(
                "No prior recent-session evidence file was found. "
                "This app session started a fresh bounded evidence ledger."
            ),
        )

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        history = deserialize_session_evidence_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return SessionEvidenceRestoreSnapshot(
            history=tuple(),
            persistence_path=str(resolved_path),
            restore_status="RESTORE_BLOCKED",
            restore_message=(
                "Prior recent-session evidence could not be restored because the persisted file was invalid "
                f"under the current schema. Detail: {exc}"
            ),
        )

    if not history:
        return SessionEvidenceRestoreSnapshot(
            history=tuple(),
            persistence_path=str(resolved_path),
            restore_status="RESTORE_EMPTY",
            restore_message=(
                "The persisted recent-session evidence file was valid but contained no retained entries."
            ),
        )

    return SessionEvidenceRestoreSnapshot(
        history=history,
        persistence_path=str(resolved_path),
        restore_status="RESTORE_OK",
        restore_message=(
            f"Restored {len(history)} retained recent-session evidence entries from the prior persisted ledger."
        ),
    )


def persist_session_evidence_history(
    history: tuple[SessionEvidenceRecord, ...],
    *,
    path: str | Path | None = None,
    minimum_event_index: int = 1,
) -> SessionEvidencePersistenceStatus:
    resolved_path = resolve_session_evidence_store_path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    retained_history = tuple(
        record for record in history if record.event_index >= minimum_event_index
    )
    if not retained_history:
        return clear_session_evidence_history(
            path=resolved_path,
            status_if_missing="CLEAR_OK",
            message_if_missing=(
                "No retained evidence entries were eligible to persist after the most recent intentional clear."
            ),
        )

    payload = serialize_session_evidence_payload(
        retained_history,
        history_limit=SESSION_EVIDENCE_LIMIT,
    )
    persisted_at = payload["saved_at_utc"]

    fd, temp_name = tempfile.mkstemp(
        prefix="recent_session_evidence.",
        suffix=".tmp",
        dir=str(resolved_path.parent),
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, resolved_path)
        return SessionEvidencePersistenceStatus(
            persistence_path=str(resolved_path),
            health_status="HEALTHY",
            last_status="WRITE_OK",
            last_message=(
                f"Retained evidence persisted successfully with {len(retained_history)} bounded entries."
            ),
            last_persisted_at_utc=str(persisted_at),
        )
    except OSError as exc:
        return SessionEvidencePersistenceStatus(
            persistence_path=str(resolved_path),
            health_status="BLOCKED",
            last_status="WRITE_FAILED",
            last_message=(
                "Retained evidence could not be written to the target-owned persistence file. "
                f"Detail: {exc}"
            ),
            last_persisted_at_utc=None,
        )
    finally:
        if temp_path.exists():
            temp_path.unlink()


def clear_session_evidence_history(
    *,
    path: str | Path | None = None,
    status_if_missing: str = "CLEAR_MISSING",
    message_if_missing: str | None = None,
) -> SessionEvidencePersistenceStatus:
    resolved_path = resolve_session_evidence_store_path(path)
    cleared_at = _utc_now_iso()
    if not resolved_path.exists():
        return SessionEvidencePersistenceStatus(
            persistence_path=str(resolved_path),
            health_status="HEALTHY",
            last_status=status_if_missing,
            last_message=(
                message_if_missing
                or "No retained evidence file existed, so there was nothing to clear."
            ),
            last_persisted_at_utc=cleared_at,
        )

    try:
        resolved_path.unlink()
        return SessionEvidencePersistenceStatus(
            persistence_path=str(resolved_path),
            health_status="HEALTHY",
            last_status="CLEAR_OK",
            last_message=(
                "Retained evidence was cleared from the target-owned persistence file. "
                "Current-session evidence remains visible until restart or subsequent actions."
            ),
            last_persisted_at_utc=cleared_at,
        )
    except OSError as exc:
        return SessionEvidencePersistenceStatus(
            persistence_path=str(resolved_path),
            health_status="BLOCKED",
            last_status="CLEAR_FAILED",
            last_message=(
                "Retained evidence could not be cleared from the target-owned persistence file. "
                f"Detail: {exc}"
            ),
            last_persisted_at_utc=cleared_at,
        )


def _target_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _test_scoped_store_path() -> Path | None:
    if "pytest" not in sys.modules:
        return None

    identity = os.environ.get("PYTEST_CURRENT_TEST")
    if not identity:
        for frame in inspect.stack():
            filename = frame.filename.replace("\\", "/")
            if frame.function.startswith("test_") and "/tests/" in filename:
                identity = f"{Path(frame.filename).name}:{frame.function}"
                break
    if not identity:
        identity = f"pytest-process-{os.getpid()}"

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    root = Path(tempfile.gettempdir()) / "ntb_marimo_console_pytest_state"
    return (root / f"recent_session_evidence.{digest}.json").resolve()


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
