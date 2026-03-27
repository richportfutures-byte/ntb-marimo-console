import marimo

__generated_with = "0.8.0"
app = marimo.App(width="medium")


@app.cell
def __( ):
    import marimo as mo
    import json
    from pathlib import Path
    from ninjatradebuilder.execution_facade import sweep_watchman
    from ninjatradebuilder.view_models import readiness_cards_from_sweep, ReadinessCard

    return Path, ReadinessCard, json, mo, readiness_cards_from_sweep, sweep_watchman


@app.cell
def __(Path, json, mo):
    FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "packets.valid.json"
    packet_bundle = json.loads(FIXTURE_PATH.read_text())
    trigger = {
        "trigger_family": "recheck_at_time",
        "recheck_at_time": "2026-01-14T15:15:00Z",
    }
    contract_count = len(packet_bundle.get("contracts", {}))
    bundle_status = mo.md(
        f"## Packet Bundle Loaded\nLoaded {contract_count} contracts from `{FIXTURE_PATH}`."
    )

    return FIXTURE_PATH, bundle_status, packet_bundle, trigger


@app.cell
def __(mo, packet_bundle, readiness_cards_from_sweep, sweep_watchman, trigger):
    sweep_result = sweep_watchman(packet_bundle, trigger)
    readiness_cards = readiness_cards_from_sweep(sweep_result)
    sweep_status = mo.md(
        f"## Watchman Sweep Complete\nSwept {len(readiness_cards)} contracts."
    )

    return readiness_cards, sweep_result, sweep_status


@app.cell
def __(mo, readiness_cards):
    rows = []
    for card in readiness_cards:
        rows.append(
            {
                "Contract": card.contract,
                "Status": card.status,
                "Session": card.session_state,
                "VWAP Posture": card.vwap_posture,
                "Value Location": card.value_location,
                "Level Proximity": card.level_proximity,
                "Trigger": card.trigger_state,
                "Macro State": card.macro_state,
                "Event Risk": card.event_risk,
                "Hard Lockouts": ", ".join(card.hard_lockouts) if card.hard_lockouts else "—",
                "Awareness": ", ".join(card.awareness_items) if card.awareness_items else "—",
                "Missing Context": ", ".join(card.missing_context) if card.missing_context else "—",
            }
        )
    readiness_matrix = mo.ui.table(rows, label="Readiness Matrix")

    return readiness_matrix, rows


@app.cell
def __(ReadinessCard, mo, readiness_cards):
    contract_options = [card.contract for card in readiness_cards]
    selected_contract = mo.ui.dropdown(
        options=contract_options,
        value=contract_options[0] if contract_options else None,
        label="Select Contract",
    )
    card_by_contract = {card.contract: card for card in readiness_cards}
    selected_card = card_by_contract.get(selected_contract.value)

    def format_items(items: tuple[str, ...]) -> str:
        return ", ".join(items) if items else "—"

    status_icon = {
        "ready": "🟢",
        "caution": "🟡",
        "blocked": "🔴",
    }

    detail_markdown = mo.md(
        (
            f"## Contract Detail: {selected_card.contract}\n"
            f"{status_icon[selected_card.status]} **Status:** {selected_card.status}\n\n"
            f"- Session: `{selected_card.session_state}`\n"
            f"- VWAP Posture: `{selected_card.vwap_posture}`\n"
            f"- Value Location: `{selected_card.value_location}`\n"
            f"- Level Proximity: `{selected_card.level_proximity}`\n"
            f"- Trigger State: `{selected_card.trigger_state}`\n"
            f"- Trigger Proximity: `{selected_card.trigger_proximity_summary}`\n"
            f"- Macro State: `{selected_card.macro_state}`\n"
            f"- Event Risk: `{selected_card.event_risk}`\n"
            f"- Hard Lockouts: {format_items(selected_card.hard_lockouts)}\n"
            f"- Awareness: {format_items(selected_card.awareness_items)}\n"
            f"- Missing Context: {format_items(selected_card.missing_context)}\n"
        )
        if isinstance(selected_card, ReadinessCard)
        else "## Contract Detail\nNo contract selected."
    )

    return card_by_contract, detail_markdown, selected_card, selected_contract


@app.cell
def __(mo, Path):
    from ninjatradebuilder.logging_record import DEFAULT_LOG_PATH, read_log_records
    from ninjatradebuilder.view_models import LogHistoryRow, log_history_rows_from_records

    log_path = Path(__file__).resolve().parent.parent / DEFAULT_LOG_PATH
    all_records = read_log_records(log_path)
    record_count = len(all_records)
    history_load_status = mo.md(
        f"## Run History\nLoaded **{record_count}** log record(s) from `{log_path}`."
    )

    return (
        DEFAULT_LOG_PATH,
        LogHistoryRow,
        all_records,
        history_load_status,
        log_history_rows_from_records,
        log_path,
        read_log_records,
    )


@app.cell
def __(all_records, log_history_rows_from_records, mo):
    unique_contracts = sorted({r.contract for r in all_records})
    contract_filter_options = ["All"] + unique_contracts
    history_contract_filter = mo.ui.dropdown(
        options=contract_filter_options,
        value="All",
        label="Filter by Contract",
    )

    filter_value = history_contract_filter.value
    if filter_value == "All":
        filtered_rows = log_history_rows_from_records(all_records)
    else:
        filtered_rows = log_history_rows_from_records(
            all_records, contract_filter=filter_value
        )

    history_table_data = [
        {
            "Run ID": row.run_id[:8] + "…",
            "Logged At": row.logged_at,
            "Contract": row.contract,
            "Run Type": row.run_type,
            "Status": row.watchman_status,
            "Trigger": row.trigger_family,
            "VWAP": row.vwap_posture,
            "Value Loc": row.value_location,
            "Level Prox": row.level_proximity,
            "Event Risk": row.event_risk,
            "Decision": row.final_decision,
            "Notes": row.notes,
        }
        for row in filtered_rows
    ]
    history_table = mo.ui.table(
        history_table_data,
        label=f"Run History ({len(filtered_rows)} records)",
    )

    return (
        contract_filter_options,
        filter_value,
        filtered_rows,
        history_contract_filter,
        history_table,
        history_table_data,
        unique_contracts,
    )


@app.cell
def __(all_records, mo):
    history_empty_notice = (
        mo.md(
            "> **No run history found.** Use [sweep_watchman_and_log](cci:1://file:///C:/Users/stuar/Documents/GitHub/ninjaTweek/src/ninjatradebuilder/execution_facade.py:134:0-154:33) or "
            "[run_pipeline_and_log](cci:1://file:///C:/Users/stuar/Documents/GitHub/ninjaTweek/src/ninjatradebuilder/execution_facade.py:197:0-238:34) from the execution facade to generate log entries."
        )
        if not all_records
        else mo.md("")
    )

    return (history_empty_notice,)


if __name__ == "__main__":
    app.run()
