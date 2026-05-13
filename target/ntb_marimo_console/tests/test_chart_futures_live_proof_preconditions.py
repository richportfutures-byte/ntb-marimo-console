from __future__ import annotations

from pathlib import Path


DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "chart_futures_live_proof_preconditions.md"
CAPABILITY_AUDIT_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "five_contract_schwab_stream_capability_audit.md"
)
PROOF_CAPTURE_PATH = Path(__file__).resolve().parents[1] / "docs" / "five_contract_live_proof_capture.md"


FORBIDDEN_SENSITIVE_FRAGMENTS = (
    "Authorization: Bearer",
    "Bearer ey",
    "access_token=",
    "refresh_token=",
    "app_key=",
    "app_secret=",
    "customerId=",
    "correlId=",
    "accountId=",
    "schwabClientCustomerId",
    "schwabClientCorrelId",
    "wss://",
    "https://streamer-api",
    "streamer-api.schwab.com",
    ".state/secrets",
    "schwab_live.env",
    "token.json",
)


def _text(path: Path) -> str:
    assert path.exists(), f"{path.name} must exist"
    return path.read_text(encoding="utf-8")


def test_chart_futures_preconditions_doc_records_premature_verdict() -> None:
    text = _text(DOC_PATH)

    assert "**CHART_FUTURES proof is premature with the current implementation.**" in text
    assert "bounded five-contract `LEVELONE_FUTURES` live updates were received and counted" in text
    assert "cannot yet produce direct `CHART_FUTURES` proof" in text
    assert "Implementation work is required" in text


def test_chart_futures_preconditions_doc_names_missing_live_surfaces() -> None:
    text = _text(DOC_PATH)

    assert "`OperatorSchwabStreamerSession.subscribe()` currently builds a `LEVELONE_FUTURES` subscription payload" in text
    assert "`services_requested=(\"LEVELONE_FUTURES\",)` only" in text
    assert "does not route live chart frames into `ChartFuturesBarBuilder`" in text
    assert "does not parse Schwab `CHART_FUTURES` payloads into" in text
    assert "does not count completed one-minute or completed five-minute chart bars" in text


def test_chart_futures_preconditions_doc_preserves_boundaries() -> None:
    text = _text(DOC_PATH)

    for contract in ("`ES`", "`NQ`", "`CL`", "`6E`", "`MGC`"):
        assert contract in text
    assert "`ZN` and `GC` excluded" in text
    assert "never maps `MGC` to `GC`" in text
    assert "preserved engine remains the sole decision authority" in text
    assert "Production release readiness remains premature" in text
    for fragment in FORBIDDEN_SENSITIVE_FRAGMENTS:
        assert fragment not in text


def test_existing_capability_audit_reflects_levelone_but_not_chart_live_proof() -> None:
    text = _text(CAPABILITY_AUDIT_PATH)

    assert "Latest reviewed checkpoint: `a57b0fa Record five-contract LEVELONE live result`" in text
    assert "bounded five-contract `LEVELONE_FUTURES` live result is now recorded" in text
    assert "still does not implement live `CHART_FUTURES` subscription/parsing" in text
    assert "LEVELONE recorded; CHART pending" in text
    assert "Live `LEVELONE_FUTURES` behavior for all five final contracts is implemented" in text
    assert "does not establish `CHART_FUTURES`" in text


def test_live_proof_capture_doc_blocks_levelone_to_chart_generalization() -> None:
    text = _text(PROOF_CAPTURE_PATH)

    assert "`LEVELONE_FUTURES` observations must not be reused as `CHART_FUTURES` observations" in text
    assert "Neither path is a five-contract `CHART_FUTURES` proof collector" in text
    assert "direct chart-futures evidence, not by the recorded `LEVELONE_FUTURES` result" in text
