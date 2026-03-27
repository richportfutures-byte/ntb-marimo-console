"""
Pre-Market Condition Framework.
Generates contract-specific structural briefings before RTH using Gemini.
Each brief cites actual schema field names and values, not generic commentary.
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.genai import types

from .schemas import MarketPacket, PacketBundle, PreMarketBrief, QueryTrigger, KeyLevelAnalysis
from .prompts import premarket_brief_prompt
from .watchman import WatchmanState


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable not set. "
            "Run: export GEMINI_API_KEY=your-api-key-here"
        )
    return genai.Client(api_key=api_key)


def _parse_brief_response(raw: str, contract: str, session_date: str) -> PreMarketBrief:
    """Parse Gemini's JSON response into a PreMarketBrief."""
    import re

    text = raw.strip()

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try to extract the outermost JSON object if there's extra text
    if not text.startswith("{"):
        brace_start = text.find("{")
        if brace_start != -1:
            text = text[brace_start:]

    # Find the matching closing brace — properly skip over quoted strings
    if text.startswith("{"):
        depth = 0
        in_string = False
        escape_next = False
        end_idx = len(text) - 1
        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                if in_string:
                    escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        text = text[: end_idx + 1]

    # Replace NaN / Infinity which Gemini sometimes emits
    text = re.sub(r'\bNaN\b', 'null', text)
    text = re.sub(r'\bInfinity\b', 'null', text)
    text = re.sub(r'\b-Infinity\b', 'null', text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Strip control characters and retry
        cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Final attempt: strip trailing comma before } or ]
            cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
            data = json.loads(cleaned)

    # Parse key_structural_levels
    key_levels = [
        KeyLevelAnalysis(
            level_name=lvl["level_name"],
            value=float(lvl["value"]),
            significance=lvl["significance"]
        )
        for lvl in data.get("key_structural_levels", [])
    ]

    # Parse query_triggers — coerce level_or_value to str (Gemini may return floats)
    triggers = []
    for t in data.get("query_triggers", []):
        lov = t.get("level_or_value")
        if lov is not None and not isinstance(lov, str):
            lov = str(lov)
        triggers.append(
            QueryTrigger(
                condition=t["condition"],
                schema_fields=t.get("schema_fields", []),
                level_or_value=lov,
            )
        )

    return PreMarketBrief(
        contract=data.get("contract", contract),
        session_date=data.get("session_date", session_date),
        analytical_framework=data.get("analytical_framework", ""),
        key_structural_levels=key_levels,
        long_thesis=data.get("long_thesis"),
        short_thesis=data.get("short_thesis"),
        current_structure_summary=data.get("current_structure_summary", ""),
        query_triggers=triggers,
        watch_for=data.get("watch_for", []),
        schema_fields_referenced=data.get("schema_fields_referenced", []),
        generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
    )


def generate_premarket_brief(
    contract: str,
    packet: MarketPacket,
    ext: dict,
    session_date: str,
    watchman_state: Optional[WatchmanState] = None,
    model: str = "gemini-2.5-flash",
) -> PreMarketBrief:
    """
    Generate a pre-market structural brief for a single contract.
    Returns a PreMarketBrief with field-specific language and explicit query triggers.
    """
    client = _get_client()
    system_prompt, user_prompt = premarket_brief_prompt(contract, packet, ext, session_date)

    # Inject watchman context if available
    if watchman_state:
        packet_age = (
            f"{watchman_state.packet_age_seconds:.0f}s"
            if watchman_state.packet_age_seconds is not None
            else "unknown"
        )
        nearest_level = (
            f"{watchman_state.nearest_level_name} @ {watchman_state.nearest_level_value}"
            if watchman_state.nearest_level_name and watchman_state.nearest_level_value is not None
            else "unknown"
        )
        hard_lockouts = ", ".join(watchman_state.hard_lockout_flags) or "none"
        awareness_flags = ", ".join(watchman_state.awareness_flags) or "none"
        watchman_context = f"""
WATCHMAN PRE-FLIGHT CONTEXT (deterministic, no LLM):
- Packet age: {packet_age} (stale: {watchman_state.is_stale})
- VWAP posture: {watchman_state.vwap_posture}
- Value location: {watchman_state.value_location}
- Level proximity: {watchman_state.level_proximity} (nearest: {nearest_level})
- Delta posture: {watchman_state.delta_posture}
- Event risk: {watchman_state.event_risk}
- Macro state: {watchman_state.macro_state or 'N/A'}
- Hard lockouts: {hard_lockouts}
- Awareness flags: {awareness_flags}
"""
        user_prompt = user_prompt + watchman_context

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )

    raw_text = response.text
    try:
        return _parse_brief_response(raw_text, contract, session_date)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini returned unparseable JSON for {contract}: {e}\n"
            f"Raw response (first 500 chars): {raw_text[:500]}"
        ) from e


def generate_all_premarket_briefs(
    bundle: PacketBundle,
    watchman_states: Optional[dict[str, WatchmanState]] = None,
    contracts: Optional[list[str]] = None,
    model: str = "gemini-2.5-flash",
) -> dict[str, PreMarketBrief | Exception]:
    """
    Generate pre-market briefs for all (or selected) contracts in a bundle.
    Returns dict of {contract: PreMarketBrief} or {contract: Exception} if one fails.
    """
    targets = contracts or list(bundle.packets.keys())
    results: dict[str, PreMarketBrief | Exception] = {}

    for contract in targets:
        packet = bundle.packets.get(contract)
        if not packet:
            results[contract] = ValueError(f"No packet found for {contract}")
            continue
        ext = bundle.extensions.get(contract, {})
        ws = watchman_states.get(contract) if watchman_states else None

        try:
            brief = generate_premarket_brief(
                contract=contract,
                packet=packet,
                ext=ext,
                session_date=bundle.session_date,
                watchman_state=ws,
                model=model,
            )
            results[contract] = brief
        except Exception as e:
            results[contract] = e

    return results
