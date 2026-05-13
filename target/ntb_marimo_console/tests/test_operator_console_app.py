from __future__ import annotations


def test_operator_console_app_root_import_smoke() -> None:
    import ntb_marimo_console.operator_console_app as app_mod

    assert getattr(app_mod, "app", None) is not None


def test_partial_thesis_reference_form_payload_returns_validation_without_raise() -> None:
    import ntb_marimo_console.operator_console_app as app_mod
    from ntb_marimo_console.active_trade import ThesisReference

    thesis, error = app_mod.optional_thesis_reference_from_form(
        {
            "pipeline_result_id": "pipeline-result-fixture-001",
            "trigger_name": "",
            "trigger_state": "",
        },
        ThesisReference,
    )

    assert thesis is None
    assert error == "Thesis reference requires result id, trigger name, and trigger state."


def test_complete_thesis_reference_form_payload_builds_reference() -> None:
    import ntb_marimo_console.operator_console_app as app_mod
    from ntb_marimo_console.active_trade import ThesisReference

    thesis, error = app_mod.optional_thesis_reference_from_form(
        {
            "pipeline_result_id": "pipeline-result-fixture-001",
            "trigger_name": "fixture-trigger",
            "trigger_state": "QUERY_READY",
        },
        ThesisReference,
    )

    assert error is None
    assert thesis is not None
    assert thesis.pipeline_result_id == "pipeline-result-fixture-001"
