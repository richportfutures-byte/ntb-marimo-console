__all__ = [
    "AuditReplayStore",
    "FixtureAuditReplayStore",
    "FixturePreMarketArtifactStore",
    "FixtureRunHistoryStore",
    "JsonlAuditReplayStore",
    "JsonlRunHistoryStore",
    "PipelineBackend",
    "PreMarketArtifactStore",
    "PreservedEngineBackend",
    "RunHistoryStore",
    "TriggerEvaluation",
    "TriggerEvaluationBundle",
    "TriggerEvaluator",
    "TriggerSpec",
    "UnavailableEngineBackend",
    "trigger_specs_from_brief",
]


def __getattr__(name: str) -> object:
    if name in {
        "AuditReplayStore",
        "PipelineBackend",
        "PreMarketArtifactStore",
        "RunHistoryStore",
        "TriggerEvaluation",
        "TriggerSpec",
    }:
        from . import contracts

        return getattr(contracts, name)
    if name in {"FixtureAuditReplayStore", "JsonlAuditReplayStore"}:
        from . import audit_replay_store

        return getattr(audit_replay_store, name)
    if name == "FixturePreMarketArtifactStore":
        from . import premarket_store

        return getattr(premarket_store, name)
    if name in {"PreservedEngineBackend", "UnavailableEngineBackend"}:
        from . import preserved_engine_backend

        return getattr(preserved_engine_backend, name)
    if name in {"FixtureRunHistoryStore", "JsonlRunHistoryStore"}:
        from . import run_history_store

        return getattr(run_history_store, name)
    if name in {"TriggerEvaluationBundle", "TriggerEvaluator"}:
        from . import trigger_evaluator

        return getattr(trigger_evaluator, name)
    if name == "trigger_specs_from_brief":
        from . import trigger_specs

        return getattr(trigger_specs, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
