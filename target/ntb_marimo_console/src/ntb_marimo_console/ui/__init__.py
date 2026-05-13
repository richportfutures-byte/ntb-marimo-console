__all__ = [
    "AppShellPayload",
    "build_app_shell",
    "build_phase1_render_plan",
    "render_phase1_console",
]


def __getattr__(name: str) -> object:
    if name in {"AppShellPayload", "build_app_shell"}:
        from . import app_shell

        return getattr(app_shell, name)
    if name in {"build_phase1_render_plan", "render_phase1_console"}:
        from . import marimo_phase1_renderer

        return getattr(marimo_phase1_renderer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
