from pathlib import Path

import marimo

import app


def test_app_import_exposes_marimo_app():
    assert isinstance(app.app, marimo.App)


def test_operator_modes_are_present_in_app_source():
    source = Path("app.py").read_text()
    assert "Pre-Market Brief" in source
    assert "Live Pipeline" in source
    assert "Readiness Matrix" in source
