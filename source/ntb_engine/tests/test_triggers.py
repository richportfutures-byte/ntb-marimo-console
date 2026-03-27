from __future__ import annotations

import pytest

from ninjatradebuilder.schemas.triggers import (
    PriceLevelTouchTrigger,
    RecheckAtTimeTrigger,
    validate_readiness_trigger,
)


class TestRecheckAtTimeTrigger:
    def test_valid_trigger(self) -> None:
        trigger = RecheckAtTimeTrigger(
            trigger_family="recheck_at_time",
            recheck_at_time="2026-01-14T15:15:00Z",
        )
        assert trigger.trigger_family == "recheck_at_time"
        assert trigger.recheck_at_time == "2026-01-14T15:15:00Z"

    def test_rejects_empty_recheck_time(self) -> None:
        with pytest.raises(Exception):
            RecheckAtTimeTrigger(
                trigger_family="recheck_at_time",
                recheck_at_time="",
            )

    def test_rejects_non_iso_datetime(self) -> None:
        with pytest.raises(Exception):
            RecheckAtTimeTrigger(
                trigger_family="recheck_at_time",
                recheck_at_time="not-a-datetime",
            )

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            RecheckAtTimeTrigger(
                trigger_family="recheck_at_time",
                recheck_at_time="2026-01-14T15:15:00Z",
                extra_field="should fail",
            )

    def test_rejects_missing_recheck_time(self) -> None:
        with pytest.raises(Exception):
            RecheckAtTimeTrigger(trigger_family="recheck_at_time")


class TestPriceLevelTouchTrigger:
    def test_valid_trigger(self) -> None:
        trigger = PriceLevelTouchTrigger(
            trigger_family="price_level_touch",
            price_level=5950.25,
        )
        assert trigger.trigger_family == "price_level_touch"
        assert trigger.price_level == 5950.25

    def test_rejects_boolean_price_level(self) -> None:
        with pytest.raises(Exception):
            PriceLevelTouchTrigger(
                trigger_family="price_level_touch",
                price_level=True,
            )

    def test_rejects_missing_price_level(self) -> None:
        with pytest.raises(Exception):
            PriceLevelTouchTrigger(trigger_family="price_level_touch")

    def test_accepts_integer_price_level(self) -> None:
        trigger = PriceLevelTouchTrigger(
            trigger_family="price_level_touch",
            price_level=5950,
        )
        assert trigger.price_level == 5950.0


class TestValidateReadinessTrigger:
    def test_validates_recheck_dict(self) -> None:
        result = validate_readiness_trigger(
            {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}
        )
        assert result == {
            "trigger_family": "recheck_at_time",
            "recheck_at_time": "2026-01-14T15:15:00Z",
        }

    def test_validates_price_level_dict(self) -> None:
        result = validate_readiness_trigger(
            {"trigger_family": "price_level_touch", "price_level": 5950.25}
        )
        assert result == {
            "trigger_family": "price_level_touch",
            "price_level": 5950.25,
        }

    def test_passes_through_typed_recheck_trigger(self) -> None:
        trigger = RecheckAtTimeTrigger(
            trigger_family="recheck_at_time",
            recheck_at_time="2026-01-14T15:15:00Z",
        )
        result = validate_readiness_trigger(trigger)
        assert result["trigger_family"] == "recheck_at_time"
        assert result["recheck_at_time"] == "2026-01-14T15:15:00Z"

    def test_passes_through_typed_price_trigger(self) -> None:
        trigger = PriceLevelTouchTrigger(
            trigger_family="price_level_touch",
            price_level=5950.25,
        )
        result = validate_readiness_trigger(trigger)
        assert result["trigger_family"] == "price_level_touch"
        assert result["price_level"] == 5950.25

    def test_rejects_unsupported_family(self) -> None:
        with pytest.raises(ValueError, match="Unsupported or missing trigger_family"):
            validate_readiness_trigger({"trigger_family": "unknown_family"})

    def test_rejects_missing_family(self) -> None:
        with pytest.raises(ValueError, match="Unsupported or missing trigger_family"):
            validate_readiness_trigger({"recheck_at_time": "2026-01-14T15:15:00Z"})

    def test_rejects_non_mapping(self) -> None:
        with pytest.raises(TypeError, match="mapping"):
            validate_readiness_trigger("not a mapping")

    def test_rejects_malformed_recheck_dict(self) -> None:
        with pytest.raises(Exception):
            validate_readiness_trigger(
                {"trigger_family": "recheck_at_time", "recheck_at_time": ""}
            )

    def test_rejects_malformed_price_dict(self) -> None:
        with pytest.raises(Exception):
            validate_readiness_trigger(
                {"trigger_family": "price_level_touch", "price_level": True}
            )
