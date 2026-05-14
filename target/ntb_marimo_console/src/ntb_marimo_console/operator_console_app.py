import marimo

__generated_with = "0.23.5"
app = marimo.App(width="full")


with app.setup:
    def optional_thesis_reference_from_form(submitted, thesis_cls):
        def _blank_string_to_none(value):
            if value is None:
                return None
            text = str(value).strip()
            return text if text else None

        result_id = _blank_string_to_none(submitted.get("pipeline_result_id"))
        trigger_name = _blank_string_to_none(submitted.get("trigger_name"))
        trigger_state = _blank_string_to_none(submitted.get("trigger_state"))
        supplied = (result_id, trigger_name, trigger_state)
        if not any(supplied):
            return None, None
        if not all(supplied):
            return None, "Thesis reference requires result id, trigger name, and trigger state."
        try:
            return (
                thesis_cls(
                    pipeline_result_id=result_id,
                    trigger_name=trigger_name,
                    trigger_state=trigger_state,
                ),
                None,
            )
        except ValueError as exc:
            return None, str(exc)


    def resolve_cockpit_runtime_snapshot_producer(
        cached_producer,
        *,
        operator_runtime_mode,
        live_runtime_starter=None,
        non_live_producer_builder=None,
    ):
        """Resolve the read-only runtime snapshot producer for a cockpit session.

        Called once per session with the Marimo-state-cached producer:

        * If a producer is already cached, it is returned unchanged — the live
          runtime is NOT started again on refresh/render and there is no repeated
          Schwab login per refresh.
        * On first resolution (``cached_producer is None``) in explicit
          ``OPERATOR_LIVE_RUNTIME`` mode, the operator-owned live runtime is started
          and registered exactly once; the returned producer reads that runtime's
          cache read-only. If the live start fails the producer is fail-closed
          (live unavailable/error), never fixture data.
        * Otherwise the non-live producer is built (default fixture/non-live path).
        """

        if cached_producer is not None:
            return cached_producer

        from ntb_marimo_console.live_cockpit_runtime import start_live_cockpit_runtime
        from ntb_marimo_console.operator_live_runtime import (
            OPERATOR_LIVE_RUNTIME,
            build_operator_runtime_snapshot_producer_from_env,
        )

        if live_runtime_starter is None:
            live_runtime_starter = start_live_cockpit_runtime
        if non_live_producer_builder is None:
            non_live_producer_builder = build_operator_runtime_snapshot_producer_from_env

        if operator_runtime_mode == OPERATOR_LIVE_RUNTIME:
            return live_runtime_starter().producer
        return non_live_producer_builder()


@app.cell
def _():
    import marimo as mo

    from ntb_marimo_console.active_trade import ActiveTradeRegistry
    from ntb_marimo_console.anchor_inputs import AnchorInputRegistry
    from ntb_marimo_console.operator_notes import OperatorNotesRegistry
    from ntb_marimo_console.operator_live_runtime import (
        operator_runtime_mode_from_env,
    )
    from ntb_marimo_console.session_lifecycle import (
        clear_retained_evidence,
        refresh_runtime_snapshot,
        load_session_lifecycle_from_env,
        reload_current_profile,
        request_cockpit_manual_query,
        request_query_action,
        reset_session,
        switch_profile,
    )

    get_lifecycle, set_lifecycle = mo.state(None)
    get_runtime_snapshot_producer, set_runtime_snapshot_producer = mo.state(None)
    get_pending_cockpit_query_contract, set_pending_cockpit_query_contract = mo.state("ES")
    get_pending_profile_id, set_pending_profile_id = mo.state(None)
    get_active_trade_registry, set_active_trade_registry = mo.state(None)
    get_anchor_input_registry, set_anchor_input_registry = mo.state(None)
    get_operator_notes_registry, set_operator_notes_registry = mo.state(None)
    get_premarket_manual_sections, set_premarket_manual_sections = mo.state({})
    operator_runtime_mode = operator_runtime_mode_from_env()
    runtime_snapshot_producer = get_runtime_snapshot_producer()
    if runtime_snapshot_producer is None:
        runtime_snapshot_producer = resolve_cockpit_runtime_snapshot_producer(
            runtime_snapshot_producer,
            operator_runtime_mode=operator_runtime_mode,
        )
        set_runtime_snapshot_producer(runtime_snapshot_producer)
    active_trade_registry = get_active_trade_registry()
    if active_trade_registry is None:
        active_trade_registry = ActiveTradeRegistry()
        set_active_trade_registry(active_trade_registry)
    anchor_input_registry = get_anchor_input_registry()
    if anchor_input_registry is None:
        anchor_input_registry = AnchorInputRegistry()
        set_anchor_input_registry(anchor_input_registry)
    operator_notes_registry = get_operator_notes_registry()
    if operator_notes_registry is None:
        operator_notes_registry = OperatorNotesRegistry()
        set_operator_notes_registry(operator_notes_registry)

    lifecycle = get_lifecycle()
    if lifecycle is None:
        lifecycle = load_session_lifecycle_from_env(
            default_mode="fixture_demo",
            runtime_snapshot_producer=runtime_snapshot_producer,
            operator_runtime_mode=operator_runtime_mode,
        )
        set_lifecycle(lifecycle)
        startup = lifecycle.shell.get("startup", {})
        if isinstance(startup, dict):
            _initial_profile_id = startup.get("selected_profile_id")
            if _initial_profile_id is not None:
                set_pending_profile_id(str(_initial_profile_id))
    return (
        active_trade_registry,
        anchor_input_registry,
        clear_retained_evidence,
        get_pending_cockpit_query_contract,
        get_pending_profile_id,
        get_premarket_manual_sections,
        lifecycle,
        mo,
        operator_notes_registry,
        refresh_runtime_snapshot,
        reload_current_profile,
        request_cockpit_manual_query,
        request_query_action,
        reset_session,
        set_active_trade_registry,
        set_anchor_input_registry,
        set_lifecycle,
        set_operator_notes_registry,
        set_pending_cockpit_query_contract,
        set_pending_profile_id,
        set_premarket_manual_sections,
        switch_profile,
    )


@app.cell
def _(
    active_trade_registry,
    get_pending_cockpit_query_contract,
    get_pending_profile_id,
    get_premarket_manual_sections,
    lifecycle,
    mo,
    set_pending_cockpit_query_contract,
    set_pending_profile_id,
):
    from collections.abc import Mapping as _Mapping

    from ntb_marimo_console.primary_cockpit import primary_cockpit_surface_key

    controls_shell = lifecycle.shell
    controls_startup_panel = controls_shell.get("startup")
    controls_runtime_panel = controls_shell.get("runtime")
    controls_workflow_panel = controls_shell.get("workflow")
    controls_lifecycle_panel = controls_shell.get("lifecycle")

    if not isinstance(controls_startup_panel, _Mapping):
        controls_startup_panel = {}
    if not isinstance(controls_runtime_panel, _Mapping):
        controls_runtime_panel = {}
    if not isinstance(controls_workflow_panel, _Mapping):
        controls_workflow_panel = {}
    if not isinstance(controls_lifecycle_panel, _Mapping):
        controls_lifecycle_panel = {}

    query_available = controls_workflow_panel.get("query_action_available") is True
    reset_available = controls_lifecycle_panel.get("reset_available") is True
    reload_available = controls_lifecycle_panel.get("reload_available") is True
    selected_profile_id = str(controls_startup_panel.get("selected_profile_id", "<unresolved>"))
    supported_profiles = controls_startup_panel.get("supported_profiles")
    profile_options: dict[str, str] = {}
    profile_label_by_id: dict[str, str] = {}
    if isinstance(supported_profiles, list):
        for item in supported_profiles:
            if not isinstance(item, _Mapping):
                continue
            _option_profile_id = str(item.get("profile_id", "<unresolved>"))
            label = (
                f"{_option_profile_id} | {item.get('profile_kind', item.get('runtime_mode', '<unresolved>'))} | "
                f"{item.get('contract', '<unresolved>')} | {item.get('session_date', '<unresolved>')}"
            )
            profile_options[label] = _option_profile_id
            if _option_profile_id not in profile_label_by_id:
                profile_label_by_id[_option_profile_id] = label

    pending_profile_id = get_pending_profile_id()
    if pending_profile_id not in profile_label_by_id:
        pending_profile_id = selected_profile_id if selected_profile_id in profile_label_by_id else None
        if pending_profile_id is not None:
            set_pending_profile_id(pending_profile_id)
    pending_profile_label = profile_label_by_id.get(pending_profile_id) if pending_profile_id is not None else None

    profile_selector = mo.ui.dropdown(
        options=profile_options,
        value=pending_profile_label,
        label="Supported Profile",
        on_change=set_pending_profile_id,
        full_width=True,
    )
    switch_available = bool(profile_options) and pending_profile_id is not None and pending_profile_id != selected_profile_id

    cockpit_rows: dict[str, dict] = {}
    _surfaces = controls_shell.get("surfaces")
    if isinstance(_surfaces, _Mapping):
        cockpit_surface = _surfaces.get(primary_cockpit_surface_key(controls_shell))
        if isinstance(cockpit_surface, _Mapping):
            raw_rows = cockpit_surface.get("rows")
            if isinstance(raw_rows, list):
                for row in raw_rows:
                    if isinstance(row, _Mapping) and row.get("contract") is not None:
                        cockpit_rows[str(row.get("contract"))] = dict(row)
    cockpit_query_options = ["ES", "NQ", "CL", "6E", "MGC"]
    pending_cockpit_query_contract = get_pending_cockpit_query_contract()
    if pending_cockpit_query_contract not in cockpit_query_options:
        pending_cockpit_query_contract = "ES"
        set_pending_cockpit_query_contract(pending_cockpit_query_contract)
    selected_cockpit_query_row = cockpit_rows.get(str(pending_cockpit_query_contract), {})
    cockpit_query_available = selected_cockpit_query_row.get("query_action_state") == "ENABLED"
    cockpit_query_selector = mo.ui.dropdown(
        options=cockpit_query_options,
        value=str(pending_cockpit_query_contract),
        label="Manual Query Contract",
        on_change=set_pending_cockpit_query_contract,
        full_width=True,
    )
    cockpit_query_button = mo.ui.run_button(
        label="Submit Preserved Pipeline Query",
        kind="success" if cockpit_query_available else "neutral",
        disabled=not cockpit_query_available,
        tooltip=(
            "Submits the selected contract through the preserved pipeline boundary."
            if cockpit_query_available
            else str(selected_cockpit_query_row.get("query_disabled_reason") or "Manual query is blocked for this contract.")
        ),
        full_width=True,
    )

    query_button = mo.ui.run_button(
        label="Run bounded query for loaded snapshot",
        kind="success" if query_available else "neutral",
        disabled=not query_available,
        tooltip=(
            "Runs the bounded Phase 1 pipeline against the currently loaded snapshot."
            if query_available
            else "Live query is blocked until the current loaded snapshot is eligible."
        ),
        full_width=True,
    )
    reset_button = mo.ui.run_button(
        label="Reset Session",
        kind="warn" if reset_available else "neutral",
        disabled=not reset_available,
        tooltip=(
            "Clears the bounded query, Decision Review, and Audit / Replay state while keeping the current profile loaded."
            if reset_available
            else "Reset becomes available only after a valid profile context is loaded."
        ),
        full_width=True,
    )
    reload_button = mo.ui.run_button(
        label="Reload Current Profile",
        kind="neutral",
        disabled=not reload_available,
        tooltip=(
            "Reruns preflight and reloads the current profile from its declared artifact source."
            if reload_available
            else "Reload is unavailable until a supported profile is selected."
        ),
        full_width=True,
    )
    runtime_refresh = mo.ui.refresh(
        options=["15s"],
        default_interval="15s",
        label="Runtime Cache Refresh",
    )
    switch_button = mo.ui.run_button(
        label="Switch To Selected Profile",
        kind="neutral",
        disabled=not switch_available,
        tooltip=(
            "Reruns preflight and reloads the selected supported profile as a fresh session."
            if switch_available
            else "Select a different supported profile to run a profile switch."
        ),
        full_width=True,
    )
    clear_retained_button = mo.ui.run_button(
        label="Clear Retained Evidence",
        kind="warn",
        tooltip=(
            "Clears only the durable retained evidence file. "
            "Current-session evidence remains visible until restart or subsequent actions."
        ),
        full_width=True,
    )
    operator_live_mode = str(controls_runtime_panel.get("operator_live_runtime_mode", "SAFE_NON_LIVE"))
    active_trade_controls_enabled = operator_live_mode == "OPERATOR_LIVE_RUNTIME"
    active_trade_form = mo.ui.form(
        mo.ui.dictionary(
            {
                "contract": mo.ui.dropdown(
                    options=["ES", "NQ", "CL", "6E", "MGC"],
                    value="ES",
                    label="Contract",
                    full_width=True,
                ),
                "direction": mo.ui.radio(
                    options=["long", "short"],
                    value="long",
                    label="Direction",
                    inline=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "entry_price": mo.ui.number(
                    start=0,
                    step=0.01,
                    value=None,
                    label="Entry Price",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "stop_loss": mo.ui.number(
                    start=0,
                    step=0.01,
                    value=None,
                    label="Stop Loss",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "target": mo.ui.number(
                    start=0,
                    step=0.01,
                    value=None,
                    label="Target",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "pipeline_result_id": mo.ui.text(
                    label="Thesis Result ID",
                    placeholder="optional pipeline result id",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "trigger_name": mo.ui.text(
                    label="Thesis Trigger",
                    placeholder="optional trigger name",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "trigger_state": mo.ui.text(
                    label="Thesis State",
                    placeholder="optional trigger state",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "operator_notes": mo.ui.text_area(
                    label="Operator Notes",
                    placeholder="optional notes",
                    rows=3,
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
            }
        ),
        submit_button_label="Record Active Trade",
        submit_button_disabled=not active_trade_controls_enabled,
        clear_on_submit=True,
        show_clear_button=True,
        label="Record Active Trade",
    )
    open_trade_options = {
        f"{trade.contract} {trade.direction} @ {trade.entry_price} | {trade.trade_id}": trade.trade_id
        for trade in active_trade_registry.list(status="open")
    }
    active_trade_action_selector = mo.ui.dropdown(
        options=open_trade_options,
        value=None,
        label="Open Trade",
        full_width=True,
    )
    active_trade_close_button = mo.ui.run_button(
        label="Mark Closed",
        kind="neutral",
        disabled=not active_trade_controls_enabled or not bool(open_trade_options),
        tooltip="Records an operator annotation only. No order or broker action is sent.",
        full_width=True,
    )
    active_trade_stopped_button = mo.ui.run_button(
        label="Mark Stopped",
        kind="warn",
        disabled=not active_trade_controls_enabled or not bool(open_trade_options),
        tooltip="Records an operator annotation only. No order or broker action is sent.",
        full_width=True,
    )
    anchor_input_form = mo.ui.form(
        mo.ui.dictionary(
            {
                "contract": mo.ui.dropdown(
                    options=["NQ", "CL", "6E", "MGC"],
                    value="NQ",
                    label="Contract",
                    full_width=True,
                ),
                "key_levels": mo.ui.text(
                    label="Key Levels",
                    placeholder="comma-separated levels",
                    full_width=True,
                ),
                "session_high": mo.ui.number(
                    step=0.01,
                    value=None,
                    label="Session High",
                    full_width=True,
                ),
                "session_low": mo.ui.number(
                    step=0.01,
                    value=None,
                    label="Session Low",
                    full_width=True,
                ),
                "correlation_anchor": mo.ui.dropdown(
                    options=["ES", "NQ", "CL", "6E", "MGC"],
                    value="ES",
                    label="Correlation Anchor",
                    full_width=True,
                ),
                "operator_note": mo.ui.text_area(
                    label="Operator Note",
                    placeholder="optional session-planning context",
                    rows=3,
                    full_width=True,
                ),
            }
        ),
        submit_button_label="Save Anchor Inputs",
        clear_on_submit=True,
        show_clear_button=True,
        label="Cross-Asset Anchor Inputs",
    )
    operator_notes_form = mo.ui.form(
        mo.ui.dictionary(
            {
                "content": mo.ui.text_area(
                    label="Note",
                    placeholder="session observation, market context, or journal entry",
                    rows=4,
                    full_width=True,
                ),
                "category": mo.ui.dropdown(
                    options=["pre_market", "intraday", "post_session", "general"],
                    value="general",
                    label="Category",
                    full_width=True,
                ),
                "contract": mo.ui.dropdown(
                    options={
                        "Session": "",
                        "ES": "ES",
                        "NQ": "NQ",
                        "CL": "CL",
                        "6E": "6E",
                        "MGC": "MGC",
                    },
                    value="Session",
                    label="Contract",
                    full_width=True,
                ),
                "tags": mo.ui.text(
                    label="Tags",
                    placeholder="comma-separated",
                    full_width=True,
                ),
            }
        ),
        submit_button_label="Add Operator Note",
        clear_on_submit=True,
        show_clear_button=True,
        label="Operator Notes",
    )
    premarket_manual_sections = get_premarket_manual_sections() or {}
    if not isinstance(premarket_manual_sections, _Mapping):
        premarket_manual_sections = {}
    premarket_brief_form = mo.ui.form(
        mo.ui.dictionary(
            {
                "prior_session": mo.ui.text_area(
                    label="Prior Session",
                    value=str(premarket_manual_sections.get("prior_session") or ""),
                    placeholder="prior day high/low, settlement, value area, notable levels",
                    rows=3,
                    full_width=True,
                ),
                "overnight_range": mo.ui.text_area(
                    label="Overnight Range",
                    value=str(premarket_manual_sections.get("overnight_range") or ""),
                    placeholder="overnight high/low, acceptance/rejection, inventory tone",
                    rows=3,
                    full_width=True,
                ),
                "economic_calendar": mo.ui.text_area(
                    label="Economic Calendar",
                    value=str(premarket_manual_sections.get("economic_calendar") or ""),
                    placeholder="scheduled releases, speaker risk, settlement/time windows",
                    rows=3,
                    full_width=True,
                ),
                "correlation_context": mo.ui.text_area(
                    label="Correlation Context",
                    value=str(premarket_manual_sections.get("correlation_context") or ""),
                    placeholder="ES/DXY/yields/crude/euro context relevant to the session",
                    rows=3,
                    full_width=True,
                ),
            }
        ),
        submit_button_label="Save Premarket Brief Inputs",
        clear_on_submit=False,
        show_clear_button=False,
        label="Premarket Brief Inputs",
    )

    profile_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Profile Selector",
                        f"- Active Profile: `{selected_profile_id}`",
                        "- Only supported profiles are selectable here.",
                        "- A completed switch clears bounded query, Decision Review, and Audit / Replay state from the prior profile.",
                    ]
                )
            ),
            profile_selector,
            switch_button,
        ]
    )
    evidence_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Retained Evidence",
                        "- This control clears only the durable retained evidence ledger under the target-owned `.state` path.",
                        "- Current-session evidence remains readable in this app session until restart or subsequent actions.",
                    ]
                )
            ),
            clear_retained_button,
        ]
    )
    active_trade_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Active Trade Controls",
                        "- Records operator-entered trade annotations only.",
                        "- The console does not submit orders, execute trades, or contact a broker from this surface.",
                    ]
                )
            ),
            active_trade_form,
            active_trade_action_selector,
            mo.hstack([active_trade_close_button, active_trade_stopped_button], widths="equal"),
        ],
        gap=0.5,
    )
    anchor_input_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Anchor Input Controls",
                        "- Operator-supplied context for NQ, CL, 6E, and MGC.",
                        "- ES is the primary anchor contract and is intentionally not an input target.",
                    ]
                )
            ),
            anchor_input_form,
        ],
        gap=0.5,
    )
    operator_notes_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Operator Notes Controls",
                        "- Records session-level journal entries and market context.",
                        "- Notes are annotations only and do not change engine decisions or query readiness.",
                    ]
                )
            ),
            operator_notes_form,
        ],
        gap=0.5,
    )
    premarket_brief_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Premarket Brief Controls",
                        "- Adds session-planning context only.",
                        "- Missing entries remain placeholders and do not block readiness.",
                    ]
                )
            ),
            premarket_brief_form,
        ],
        gap=0.5,
    )
    cockpit_manual_query_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Manual Query",
                        f"- Selected Contract: `{pending_cockpit_query_contract}`",
                        f"- Action State: `{selected_cockpit_query_row.get('query_action_state', 'DISABLED')}`",
                    ]
                )
            ),
            cockpit_query_selector,
            cockpit_query_button,
        ],
        gap=0.5,
    )

    lifecycle_controls = mo.vstack(
        [
            runtime_refresh,
            mo.hstack([reload_button, reset_button], widths="equal"),
        ]
    )
    return (
        active_trade_action_selector,
        active_trade_close_button,
        active_trade_controls,
        active_trade_form,
        active_trade_stopped_button,
        anchor_input_controls,
        anchor_input_form,
        clear_retained_button,
        controls_shell,
        controls_startup_panel,
        cockpit_manual_query_controls,
        cockpit_query_button,
        cockpit_query_selector,
        evidence_controls,
        lifecycle_controls,
        operator_notes_controls,
        operator_notes_form,
        premarket_brief_controls,
        premarket_brief_form,
        profile_controls,
        profile_selector,
        query_available,
        query_button,
        reload_available,
        reload_button,
        reset_available,
        reset_button,
        runtime_refresh,
        selected_profile_id,
        pending_cockpit_query_contract,
        switch_available,
        switch_button,
    )


@app.cell
def _(
    active_trade_action_selector,
    active_trade_close_button,
    active_trade_form,
    active_trade_registry,
    active_trade_stopped_button,
    anchor_input_form,
    anchor_input_registry,
    clear_retained_button,
    clear_retained_evidence,
    controls_shell,
    controls_startup_panel,
    cockpit_query_button,
    get_premarket_manual_sections,
    lifecycle,
    operator_notes_form,
    operator_notes_registry,
    premarket_brief_form,
    profile_selector,
    query_available,
    query_button,
    refresh_runtime_snapshot,
    reload_available,
    reload_button,
    reload_current_profile,
    request_cockpit_manual_query,
    request_query_action,
    reset_available,
    reset_button,
    reset_session,
    runtime_refresh,
    selected_profile_id,
    pending_cockpit_query_contract,
    set_active_trade_registry,
    set_anchor_input_registry,
    set_lifecycle,
    set_operator_notes_registry,
    set_pending_profile_id,
    set_premarket_manual_sections,
    switch_available,
    switch_button,
    switch_profile,
):
    from collections.abc import Mapping as _Mapping
    from copy import deepcopy
    from datetime import datetime, timezone

    from ntb_marimo_console.active_trade import ThesisReference
    from ntb_marimo_console.anchor_inputs import (
        anchor_inputs_payload_for_pipeline,
        parse_key_levels_text,
    )
    from ntb_marimo_console.market_data.stream_cache import StreamCacheSnapshot
    from ntb_marimo_console.market_data.stream_manager import StreamManagerSnapshot
    from ntb_marimo_console.operator_notes import parse_tags_text
    from ntb_marimo_console.premarket_brief import build_premarket_brief
    from ntb_marimo_console.viewmodels.mappers import active_trade_vms_from_registry, timeline_events_from_session

    def _cache_snapshot_from_runtime(runtime_snapshot, snapshot_type):
        """Extract a StreamCacheSnapshot from the runtime snapshot result."""
        if runtime_snapshot is None:
            return None
        snapshot = getattr(runtime_snapshot, "snapshot", None)
        if snapshot is None:
            return None
        if isinstance(snapshot, snapshot_type):
            cache = getattr(snapshot, "cache", None)
            if isinstance(cache, StreamCacheSnapshot):
                return cache
        if isinstance(snapshot, StreamCacheSnapshot):
            return snapshot
        return None

    def _float_or_none(value):
        """Convert a value to float, returning None if empty or invalid."""
        if value is None:
            return None
        try:
            result = float(value)
            return result if result == result else None  # NaN check
        except (TypeError, ValueError):
            return None

    def _positive_float_or_none(value):
        """Convert to float, returning None if not positive."""
        result = _float_or_none(value)
        if result is not None and result > 0:
            return result
        return None

    def _blank_string_to_none(value):
        """Return None if value is empty/blank string, otherwise str."""
        if value is None:
            return None
        s = str(value).strip()
        return s if s else None

    current_lifecycle = lifecycle
    switch_target = profile_selector.value

    if switch_button.value and switch_available and switch_target is not None:
        switched = switch_profile(lifecycle, str(switch_target))
        set_lifecycle(switched)
        current_lifecycle = switched
        startup_after_switch = switched.shell.get("startup", {})
        if isinstance(startup_after_switch, _Mapping):
            pending_after_switch = startup_after_switch.get("selected_profile_id")
            if pending_after_switch is not None:
                set_pending_profile_id(str(pending_after_switch))
    elif clear_retained_button.value:
        current_lifecycle = clear_retained_evidence(lifecycle)
        set_lifecycle(current_lifecycle)
    elif reload_button.value and reload_available:
        current_lifecycle = reload_current_profile(lifecycle)
        set_lifecycle(current_lifecycle)
    elif reset_button.value and reset_available:
        current_lifecycle = reset_session(lifecycle)
        set_lifecycle(current_lifecycle)
    elif cockpit_query_button.value:
        current_lifecycle = request_cockpit_manual_query(
            lifecycle,
            str(pending_cockpit_query_contract),
        )
        set_lifecycle(current_lifecycle)
    elif query_button.value and query_available:
        current_lifecycle = request_query_action(lifecycle)
        set_lifecycle(current_lifecycle)
    elif runtime_refresh.value:
        current_lifecycle = refresh_runtime_snapshot(lifecycle)
        set_lifecycle(current_lifecycle)

    anchor_input_status = "ready"
    anchor_input_message = "Operator-supplied context only; preserved engine remains decision authority."
    submitted_anchor = anchor_input_form.value
    if isinstance(submitted_anchor, _Mapping):
        try:
            anchor_input_registry.set(
                contract=str(submitted_anchor.get("contract") or "NQ"),
                key_levels=parse_key_levels_text(str(submitted_anchor.get("key_levels") or "")),
                session_high=_float_or_none(submitted_anchor.get("session_high")),
                session_low=_float_or_none(submitted_anchor.get("session_low")),
                correlation_anchor=str(submitted_anchor.get("correlation_anchor") or "ES"),
                operator_note=str(submitted_anchor.get("operator_note") or ""),
            )
        except ValueError as exc:
            anchor_input_status = "invalid"
            anchor_input_message = str(exc)
        else:
            set_anchor_input_registry(anchor_input_registry)

    operator_notes_status = "ready"
    operator_notes_message = "Session journal entries are operator annotations only."
    active_trade_status = "ready"
    active_trade_message = "Operator-recorded annotations only; P&L is a display calculation and execution remains manual."
    _premarket_manual_sections = get_premarket_manual_sections() or {}
    if not isinstance(_premarket_manual_sections, _Mapping):
        _premarket_manual_sections = {}
    submitted_premarket_brief = premarket_brief_form.value
    if isinstance(submitted_premarket_brief, _Mapping):
        _premarket_manual_sections = {
            key: str(submitted_premarket_brief.get(key) or "").strip()
            for key in ("prior_session", "overnight_range", "economic_calendar", "correlation_context")
            if str(submitted_premarket_brief.get(key) or "").strip()
        }
        set_premarket_manual_sections(_premarket_manual_sections)

    submitted_note = operator_notes_form.value
    if isinstance(submitted_note, _Mapping):
        note_content = str(submitted_note.get("content") or "").strip()
        if note_content:
            try:
                operator_notes_registry.add(
                    content=note_content,
                    category=str(submitted_note.get("category") or "general"),
                    contract=_blank_string_to_none(submitted_note.get("contract")),
                    tags=parse_tags_text(str(submitted_note.get("tags") or "")),
                )
            except ValueError as exc:
                operator_notes_status = "invalid"
                operator_notes_message = str(exc)
            else:
                set_operator_notes_registry(operator_notes_registry)

    submitted_trade = active_trade_form.value
    if isinstance(submitted_trade, _Mapping):
        entry_price = _positive_float_or_none(submitted_trade.get("entry_price"))
        if entry_price is not None:
            thesis_reference, thesis_error = optional_thesis_reference_from_form(submitted_trade, ThesisReference)
            if thesis_error is not None:
                active_trade_status = "invalid"
                active_trade_message = thesis_error
            else:
                try:
                    active_trade_registry.add(
                        contract=str(submitted_trade.get("contract") or "ES"),
                        direction=str(submitted_trade.get("direction") or "long"),
                        entry_price=entry_price,
                        stop_loss=_positive_float_or_none(submitted_trade.get("stop_loss")),
                        target=_positive_float_or_none(submitted_trade.get("target")),
                        thesis_reference=thesis_reference,
                        operator_notes=str(submitted_trade.get("operator_notes") or ""),
                    )
                except ValueError as exc:
                    active_trade_status = "invalid"
                    active_trade_message = str(exc)
                else:
                    set_active_trade_registry(active_trade_registry)

    selected_active_trade_id = active_trade_action_selector.value
    if (
        selected_active_trade_id is not None
        and active_trade_close_button.value
    ):
        active_trade_registry.close(
            str(selected_active_trade_id),
            status="closed",
            close_reason="operator_marked_closed",
        )
        set_active_trade_registry(active_trade_registry)
    elif (
        selected_active_trade_id is not None
        and active_trade_stopped_button.value
    ):
        active_trade_registry.close(
            str(selected_active_trade_id),
            status="stopped",
            close_reason="operator_marked_stopped",
        )
        set_active_trade_registry(active_trade_registry)

    shell = deepcopy(current_lifecycle.shell if current_lifecycle is not None else controls_shell)
    cache_snapshot = _cache_snapshot_from_runtime(current_lifecycle.runtime_snapshot, StreamManagerSnapshot)
    if cache_snapshot is None:
        cache_snapshot = StreamCacheSnapshot(
            generated_at=datetime.now(timezone.utc).isoformat(),
            provider="active_trade_surface",
            provider_status="blocked",
            cache_max_age_seconds=15.0,
            records=(),
            blocking_reasons=("active_trade_live_cache_unavailable",),
            stale_symbols=(),
        )
    active_trade_rows = [
        item.to_dict()
        for item in active_trade_vms_from_registry(active_trade_registry, cache_snapshot)
    ]
    shell["active_trades"] = {
        "status": active_trade_status,
        "rows": active_trade_rows,
        "message": active_trade_message,
    }
    anchor_payload = anchor_inputs_payload_for_pipeline(anchor_input_registry)
    shell["anchor_inputs"] = {
        "status": anchor_input_status,
        "rows": list(anchor_payload["anchors"].values()) if isinstance(anchor_payload.get("anchors"), dict) else [],
        "message": anchor_input_message,
        "integration_status": anchor_payload["integration_status"],
    }
    shell["operator_anchor_inputs"] = anchor_payload
    note_rows = [note.to_dict() for note in operator_notes_registry.list()]
    shell["operator_notes"] = {
        "status": operator_notes_status if note_rows or operator_notes_status == "invalid" else "empty",
        "rows": note_rows,
        "message": operator_notes_message,
        "export_json": operator_notes_registry.export_json(),
    }
    premarket_brief = build_premarket_brief(
        session_date=str(controls_startup_panel.get("session_date", "unknown")),
        anchor_inputs=anchor_input_registry,
        operator_notes=operator_notes_registry,
        manual_sections=_premarket_manual_sections,
    )
    shell["premarket_brief_enrichment"] = premarket_brief.to_dict()
    _surfaces = shell.get("surfaces")
    if isinstance(_surfaces, dict):
        premarket_panel = _surfaces.get("pre_market_brief")
        if isinstance(premarket_panel, dict):
            premarket_panel["enrichment"] = premarket_brief.to_dict()
        audit_panel = _surfaces.get("audit_replay")
        if isinstance(audit_panel, dict):
            existing_rows = audit_panel.get("timeline_events")
            existing_timeline_rows = existing_rows if isinstance(existing_rows, list) else []
            timeline_events = timeline_events_from_session(
                active_trade_registry=active_trade_registry,
                operator_notes_registry=operator_notes_registry,
                anchor_input_registry=anchor_input_registry,
                session_timestamp=str(controls_startup_panel.get("session_date", "unknown")),
            )
            combined_timeline_rows = [
                *(row for row in existing_timeline_rows if isinstance(row, dict)),
                *(event.to_dict() for event in timeline_events),
            ]
            audit_panel["timeline_status"] = "ready" if combined_timeline_rows else "empty"
            audit_panel["timeline_events"] = combined_timeline_rows
            audit_panel["timeline_filters"] = {
                "event_types": sorted(
                    {
                        str(row.get("event_type"))
                        for row in combined_timeline_rows
                        if row.get("event_type") is not None
                    }
                ),
                "contracts": sorted(
                    {
                        str(row.get("contract"))
                        for row in combined_timeline_rows
                        if row.get("contract") is not None
                    }
                ),
            }
    workflow = shell.get("workflow")
    if isinstance(workflow, dict):
        workflow["operator_anchor_inputs_status"] = (
            "available" if anchor_input_registry.list() else "not_supplied"
        )
        workflow["operator_anchor_inputs_integration"] = anchor_payload["integration_status"]
        workflow["operator_notes_status"] = "available" if note_rows else "empty"
    _runtime_panel = controls_shell.get("runtime")
    if not isinstance(_runtime_panel, _Mapping):
        _runtime_panel = {}
    # Under the explicit OPERATOR_LIVE_RUNTIME opt-in the runtime panel carries
    # live-observation console identity labels; prefer them so the console
    # context summary never reports fixture/demo identity in live mode.
    mode = str(
        _runtime_panel.get("console_identity_mode_label")
        or controls_startup_panel.get("runtime_mode", "<unresolved>")
    )
    profile_id = selected_profile_id
    running_as = str(
        _runtime_panel.get("console_identity_running_as")
        or controls_startup_panel.get("running_as", "<unresolved>")
    )
    return mode, profile_id, running_as, shell


@app.cell
def _(
    active_trade_controls,
    anchor_input_controls,
    cockpit_manual_query_controls,
    evidence_controls,
    lifecycle_controls,
    mo,
    mode,
    operator_notes_controls,
    premarket_brief_controls,
    profile_controls,
    profile_id,
    query_button,
    running_as,
    shell,
):
    from ntb_marimo_console.ui.marimo_phase1_renderer import (
        render_phase1_console,
        render_watchman_gate_stop_output,
    )

    stop_output = render_watchman_gate_stop_output(
        shell,
        heading="NTB Marimo Operator Console",
        mode_summary=(
            "Explicit profile-driven operator console with startup preflight, in-session workflow gating, "
            "and repeatable manual lifecycle controls.\n\n"
            f"- Selected profile: `{profile_id}`.\n"
            f"- Runtime mode: `{mode}`.\n"
            f"- Running as: `{running_as}`.\n"
            "- Startup Status confirms whether the console is actually ready.\n"
            "- Session Lifecycle shows whether the current profile was freshly reloaded, reset, or left unchanged.\n"
            "- Recent Session Evidence shows bounded, ordered evidence for the active and recently used profiles.\n"
            "- Restored Prior Run versus Current Session labels keep persisted evidence truthful across app restarts.\n"
            "- Session Workflow shows whether live query is blocked, eligible, requested, completed, or failed.\n"
            "- Supported Profile Operations lists all supported profiles plus blocked candidate contracts.\n"
            "- Profile Selector switches only between supported profiles and fails closed when validation does not complete.\n"
            "- Reload Current Profile reruns preflight and reloads the declared source artifacts for the selected profile.\n"
            "- Reset Session clears bounded query state without changing the selected profile.\n"
            "- The live-query action runs only against the currently loaded bounded snapshot.\n"
            "- It does not place orders, imply fills, or bypass fail-closed gating.\n"
            "- Debug JSON stays secondary only."
        ),
        lifecycle_control_panel=lifecycle_controls,
        profile_control_panel=profile_controls,
        evidence_control_panel=evidence_controls,
        active_trade_control_panel=active_trade_controls,
        anchor_input_control_panel=anchor_input_controls,
        operator_notes_control_panel=operator_notes_controls,
        premarket_brief_control_panel=premarket_brief_controls,
    )
    mo.stop(stop_output is not None, stop_output)

    rendered = render_phase1_console(
        shell,
        heading="NTB Marimo Operator Console",
        mode_summary=(
            "Explicit profile-driven operator console with startup preflight, in-session workflow gating, "
            "and repeatable manual lifecycle controls.\n\n"
            f"- Selected profile: `{profile_id}`.\n"
            f"- Runtime mode: `{mode}`.\n"
            f"- Running as: `{running_as}`.\n"
            "- Startup Status confirms whether the console is actually ready.\n"
            "- Session Lifecycle shows whether the current profile was freshly reloaded, reset, or left unchanged.\n"
            "- Recent Session Evidence shows bounded, ordered evidence for the active and recently used profiles.\n"
            "- Restored Prior Run versus Current Session labels keep persisted evidence truthful across app restarts.\n"
            "- Session Workflow shows whether live query is blocked, eligible, requested, completed, or failed.\n"
            "- Supported Profile Operations lists all supported profiles plus blocked candidate contracts.\n"
            "- Profile Selector switches only between supported profiles and fails closed when validation does not complete.\n"
            "- Reload Current Profile reruns preflight and reloads the declared source artifacts for the selected profile.\n"
            "- Reset Session clears bounded query state without changing the selected profile.\n"
            "- The live-query action runs only against the currently loaded bounded snapshot.\n"
            "- It does not place orders, imply fills, or bypass fail-closed gating.\n"
            "- Debug JSON stays secondary only."
        ),
        query_action_control=query_button,
        lifecycle_control_panel=lifecycle_controls,
        profile_control_panel=profile_controls,
        evidence_control_panel=evidence_controls,
        active_trade_control_panel=active_trade_controls,
        anchor_input_control_panel=anchor_input_controls,
        operator_notes_control_panel=operator_notes_controls,
        premarket_brief_control_panel=premarket_brief_controls,
        cockpit_manual_query_control_panel=cockpit_manual_query_controls,
    )
    rendered
    return (rendered,)


if __name__ == "__main__":
    app.run()
