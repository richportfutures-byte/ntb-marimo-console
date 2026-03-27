from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import TriggerSpec


def trigger_specs_from_brief(brief: Mapping[str, Any]) -> list[TriggerSpec]:
    """Build frozen TriggerSpec rows from `PreMarketBrief` content.

    This is structural extraction only; no market reasoning is performed.
    """

    specs: list[TriggerSpec] = []
    setups = brief.get("structural_setups", [])
    if not isinstance(setups, list):
        return specs

    for setup in setups:
        if not isinstance(setup, Mapping):
            continue
        query_triggers = setup.get("query_triggers", [])
        if not isinstance(query_triggers, list):
            continue
        for trigger in query_triggers:
            if not isinstance(trigger, Mapping):
                continue
            trigger_id = str(trigger.get("id", ""))
            observable = trigger.get("observable_conditions", [])
            fields_used = trigger.get("fields_used", [])
            if not trigger_id or not isinstance(observable, list) or not isinstance(fields_used, list):
                continue

            predicate = " AND ".join(str(item) for item in observable if isinstance(item, str)).strip()
            dependencies = tuple(str(item) for item in fields_used if isinstance(item, str))
            if not predicate or not dependencies:
                continue

            specs.append(
                TriggerSpec(
                    id=trigger_id,
                    predicate=predicate,
                    required_live_field_paths=dependencies,
                    source_brief_trigger_id=trigger_id,
                )
            )

    return specs
