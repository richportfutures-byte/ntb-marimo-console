import json
from pathlib import Path

from pipeline.premarket import generate_premarket_brief
from pipeline.schemas import PacketBundle
from pipeline.watchman import sweep_all


def _load_bundle() -> PacketBundle:
    data = json.loads(Path("data/sample_packet.json").read_text())
    return PacketBundle(**data)


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, *args, **kwargs):
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str):
        self.models = _FakeModels(text)


def test_generate_premarket_brief_returns_required_sections(monkeypatch):
    bundle = _load_bundle()
    packet = bundle.packets["ES"]
    ext = bundle.extensions["ES"]
    watchman_state = sweep_all(bundle)["ES"]

    fake_payload = {
        "contract": "ES",
        "session_date": bundle.session_date,
        "analytical_framework": "ES is framed through value migration, breadth, and cash tone.",
        "key_structural_levels": [
            {
                "level_name": "previous_session_vah",
                "value": packet.levels.previous_session_vah,
                "significance": "Acts as the upper value reference and first acceptance test.",
            },
            {
                "level_name": "prior_day_low",
                "value": packet.levels.prior_day_low,
                "significance": "Defines the downside failure point for bearish continuation.",
            },
        ],
        "long_thesis": "Long only if price reclaims previous_session_vah and breadth improves.",
        "short_thesis": "Short if value rejects and cash tone remains negative below vwap.",
        "current_structure_summary": "Price is sitting on upper prior-session value while still above vwap.",
        "query_triggers": [
            {
                "condition": "If price reclaims and holds previous_session_vah with breadth improving, rerun the live pipeline.",
                "schema_fields": ["current_price", "levels.previous_session_vah", "breadth_advancing_pct"],
                "level_or_value": str(packet.levels.previous_session_vah),
            }
        ],
        "watch_for": [
            "Acceptance above previous_session_vah",
            "Breadth improvement in ES extension data",
        ],
        "schema_fields_referenced": [
            "current_price",
            "levels.previous_session_vah",
            "levels.prior_day_low",
            "levels.vwap",
            "breadth_advancing_pct",
            "index_cash_tone",
        ],
        "generated_at": "2026-03-25T11:00:00+00:00",
    }

    monkeypatch.setattr(
        "pipeline.premarket._get_client",
        lambda: _FakeClient(json.dumps(fake_payload)),
    )

    brief = generate_premarket_brief(
        contract="ES",
        packet=packet,
        ext=ext,
        session_date=bundle.session_date,
        watchman_state=watchman_state,
    )

    assert brief.contract == "ES"
    assert brief.analytical_framework
    assert brief.current_structure_summary
    assert brief.long_thesis
    assert brief.short_thesis
    assert brief.key_structural_levels
    assert all(level.significance for level in brief.key_structural_levels)
    assert brief.query_triggers
    assert all(trigger.schema_fields for trigger in brief.query_triggers)
    assert brief.watch_for
    assert brief.schema_fields_referenced
