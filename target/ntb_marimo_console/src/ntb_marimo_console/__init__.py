__all__ = ["Phase1AppDependencies", "build_phase1_app", "build_phase1_payload"]


def __getattr__(name: str) -> object:
    if name in __all__:
        from . import app as app_module

        return getattr(app_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
