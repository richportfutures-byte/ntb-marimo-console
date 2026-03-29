from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from .adapters.contracts import RuntimeMode
from .bootstrap import platform_bootstrap_command
from .demo_fixture_runtime import build_runtime_inputs_for_profile, default_fixtures_root, load_json_object
from .runtime_modes import validate_preserved_runtime_inputs
from .runtime_profiles import RuntimeProfile

DIAG_UNSUPPORTED_PROFILE = "unsupported_profile"
DIAG_INCOMPLETE_PROFILE_DEFINITION = "incomplete_profile_definition"
DIAG_MISSING_ARTIFACT_FILES = "missing_artifact_files"
DIAG_INVALID_ARTIFACT_CONTRACT = "invalid_artifact_contract"
DIAG_MISSING_DEPENDENCY = "missing_dependency"
DIAG_ADAPTER_RESOLUTION_FAILURE = "adapter_resolution_failure"
DIAG_LAUNCH_PREFLIGHT_MISMATCH = "launch_preflight_mismatch"
DIAG_RUNTIME_ASSEMBLY_FAILURE = "runtime_assembly_failure"


class RuntimeDiagnosticError(RuntimeError):
    def __init__(self, *, category: str, summary: str, remedy: str) -> None:
        super().__init__(summary)
        self.category = category
        self.summary = summary
        self.remedy = remedy


@dataclass(frozen=True)
class LaunchRequest:
    mode: RuntimeMode
    profile: RuntimeProfile
    lockout: bool
    fixtures_root: Path | None
    adapter_binding: str | None

    @property
    def artifacts_root(self) -> Path:
        base_root = self.fixtures_root or default_fixtures_root()
        return self.profile.resolve_artifact_root(base_root)


@dataclass(frozen=True)
class ArtifactSnapshotEntry:
    label: str
    path: str
    exists: bool
    size_bytes: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class ArtifactSourceSnapshot:
    profile_id: str
    artifact_root: str
    entries: tuple[ArtifactSnapshotEntry, ...]

    @property
    def signature(self) -> tuple[tuple[str, bool, int | None, int | None], ...]:
        return tuple(
            (entry.path, entry.exists, entry.size_bytes, entry.mtime_ns)
            for entry in self.entries
        )


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    category: str
    passed: bool
    summary: str
    remedy: str


@dataclass(frozen=True)
class PreflightReport:
    request: LaunchRequest | None
    requested_profile_id: str | None
    requested_mode: str | None
    checks: tuple[DiagnosticCheck, ...]
    passed: bool
    resolved_adapter: object | None = None


class PreflightFailedError(RuntimeError):
    def __init__(self, report: PreflightReport) -> None:
        super().__init__(render_preflight_report(report))
        self.report = report


def resolve_model_adapter_binding(adapter_ref: str | None, *, profile_id: str) -> object:
    if not adapter_ref:
        raise RuntimeDiagnosticError(
            category=DIAG_ADAPTER_RESOLUTION_FAILURE,
            summary=f"Runtime profile {profile_id} requires a model adapter binding.",
            remedy="Set NTB_MODEL_ADAPTER_REF or define default_model_adapter_ref in the selected profile.",
        )

    module_name, _, attribute_name = adapter_ref.partition(":")
    if not module_name or not attribute_name:
        raise RuntimeDiagnosticError(
            category=DIAG_ADAPTER_RESOLUTION_FAILURE,
            summary="NTB_MODEL_ADAPTER_REF must use package.module:attribute format.",
            remedy="Fix the adapter binding so it points at a module path and adapter attribute.",
        )

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeDiagnosticError(
            category=DIAG_ADAPTER_RESOLUTION_FAILURE,
            summary=f"Could not import adapter module {module_name}.",
            remedy="Bootstrap the target environment and verify the adapter module is on PYTHONPATH.",
        ) from exc

    adapter = getattr(module, attribute_name, None)
    if adapter is None or not callable(getattr(adapter, "generate_structured", None)):
        raise RuntimeDiagnosticError(
            category=DIAG_ADAPTER_RESOLUTION_FAILURE,
            summary=f"Adapter binding {adapter_ref} does not expose callable generate_structured(...).",
            remedy="Point NTB_MODEL_ADAPTER_REF at an adapter object that implements generate_structured(...).",
        )
    return adapter


def build_preflight_report(request: LaunchRequest) -> PreflightReport:
    checks: list[DiagnosticCheck] = []
    resolved_adapter: object | None = None

    checks.append(
        DiagnosticCheck(
            name="profile_selection",
            category="profile_selection",
            passed=True,
            summary=f"Selected runtime profile {request.profile.profile_id}.",
            remedy="None.",
        )
    )
    checks.append(
        DiagnosticCheck(
            name="profile_definition",
            category="profile_definition",
            passed=True,
            summary=f"Runtime profile {request.profile.profile_id} is internally complete.",
            remedy="None.",
        )
    )

    dependency_check = _dependency_check(request.mode)
    checks.append(dependency_check)

    artifact_check = _artifact_paths_check(request)
    checks.append(artifact_check)

    adapter_check = _adapter_check(request)
    checks.append(adapter_check)
    if adapter_check.passed and request.mode == "preserved_engine":
        resolved_adapter = resolve_model_adapter_binding(
            request.adapter_binding,
            profile_id=request.profile.profile_id,
        )

    if artifact_check.passed:
        contract_check = _artifact_contract_check(request)
    else:
        contract_check = DiagnosticCheck(
            name="artifact_contract",
            category=DIAG_MISSING_ARTIFACT_FILES,
            passed=False,
            summary="Artifact contract validation did not run because required files are missing.",
            remedy="Restore the missing files first, then rerun preflight.",
        )
    checks.append(contract_check)

    passed = all(check.passed for check in checks)
    return PreflightReport(
        request=request,
        requested_profile_id=request.profile.profile_id,
        requested_mode=request.mode,
        checks=tuple(checks),
        passed=passed,
        resolved_adapter=resolved_adapter,
    )


def build_failed_preflight_report(
    *,
    requested_profile_id: str | None,
    requested_mode: str | None,
    error: RuntimeDiagnosticError,
) -> PreflightReport:
    check = DiagnosticCheck(
        name="launch_request",
        category=error.category,
        passed=False,
        summary=error.summary,
        remedy=error.remedy,
    )
    return PreflightReport(
        request=None,
        requested_profile_id=requested_profile_id,
        requested_mode=requested_mode,
        checks=(check,),
        passed=False,
    )


def build_runtime_failure_report(
    report: PreflightReport,
    *,
    summary: str,
    remedy: str,
) -> PreflightReport:
    check = DiagnosticCheck(
        name="runtime_assembly",
        category=DIAG_RUNTIME_ASSEMBLY_FAILURE,
        passed=False,
        summary=summary,
        remedy=remedy,
    )
    return PreflightReport(
        request=report.request,
        requested_profile_id=report.requested_profile_id,
        requested_mode=report.requested_mode,
        checks=tuple((*report.checks, check)),
        passed=False,
        resolved_adapter=report.resolved_adapter,
    )


def runtime_identity_payload(report: PreflightReport) -> dict[str, object]:
    if report.request is None:
        return {
            "profile_id": report.requested_profile_id or "<unresolved>",
            "runtime_mode": report.requested_mode or "<unresolved>",
            "artifact_root": "<unresolved>",
            "adapter_binding": "<unresolved>",
            "runtime_backend": "<unresolved>",
            "preflight_passed": False,
            "preflight_status": "FAIL",
            "preflight_checks": [_check_payload(check) for check in report.checks],
        }

    request = report.request
    return {
        "profile_id": request.profile.profile_id,
        "runtime_mode": request.mode,
        "contract": request.profile.contract,
        "session_date": request.profile.session_date,
        "artifact_root": str(request.artifacts_root),
        "adapter_binding": request.adapter_binding or "not_required",
        "runtime_backend": (
            "fixture_demo"
            if request.mode == "fixture_demo"
            else "preserved_engine_backed"
        ),
        "preflight_passed": report.passed,
        "preflight_status": "PASS" if report.passed else "FAIL",
        "preflight_checks": [_check_payload(check) for check in report.checks],
    }


def render_preflight_report(report: PreflightReport) -> str:
    lines = [
        f"Runtime Preflight: {'PASS' if report.passed else 'FAIL'}",
        f"- Requested Profile: `{report.requested_profile_id or '<unset>'}`",
        f"- Requested Mode: `{report.requested_mode or '<unset>'}`",
    ]
    identity = runtime_identity_payload(report)
    lines.extend(
        [
            f"- Resolved Runtime Mode: `{identity.get('runtime_mode', '<unresolved>')}`",
            f"- Contract: `{identity.get('contract', '<unresolved>')}`",
            f"- Session Date: `{identity.get('session_date', '<unresolved>')}`",
            f"- Artifact Root: `{identity.get('artifact_root', '<unresolved>')}`",
            f"- Adapter Binding: `{identity.get('adapter_binding', '<unresolved>')}`",
        ]
    )
    lines.append("- Checks:")
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"  - [{status}] {check.name}: {check.summary}")
        if not check.passed:
            lines.append(f"    Remedy: {check.remedy}")
    return "\n".join(lines)


def declared_artifact_paths(request: LaunchRequest) -> tuple[tuple[str, Path], ...]:
    return _required_artifact_paths(request)


def build_artifact_source_snapshot(request: LaunchRequest) -> ArtifactSourceSnapshot:
    entries: list[ArtifactSnapshotEntry] = []
    for label, path in declared_artifact_paths(request):
        stat_result = path.stat() if path.exists() else None
        entries.append(
            ArtifactSnapshotEntry(
                label=label,
                path=str(path),
                exists=path.exists(),
                size_bytes=None if stat_result is None else stat_result.st_size,
                mtime_ns=None if stat_result is None else stat_result.st_mtime_ns,
            )
        )
    return ArtifactSourceSnapshot(
        profile_id=request.profile.profile_id,
        artifact_root=str(request.artifacts_root),
        entries=tuple(entries),
    )


def _dependency_check(mode: RuntimeMode) -> DiagnosticCheck:
    required_modules = ["marimo", "ntb_marimo_console"]
    if mode == "preserved_engine":
        required_modules.extend(["ninjatradebuilder", "pydantic"])

    missing: list[str] = []
    for module_name in required_modules:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(module_name)

    if missing:
        missing_text = ", ".join(missing)
        return DiagnosticCheck(
            name="dependency_imports",
            category=DIAG_MISSING_DEPENDENCY,
            passed=False,
            summary=f"Missing required imports: {missing_text}.",
            remedy=(
                f"Run {platform_bootstrap_command()} and verify the target .venv plus "
                "workspace path bootstrap are intact."
            ),
        )

    return DiagnosticCheck(
        name="dependency_imports",
        category="dependency_imports",
        passed=True,
        summary="Required runtime dependencies are importable.",
        remedy="None.",
    )


def _artifact_paths_check(request: LaunchRequest) -> DiagnosticCheck:
    missing: list[str] = []
    for label, path in _required_artifact_paths(request):
        if not path.exists():
            missing.append(f"{label}: {path}")

    if missing:
        return DiagnosticCheck(
            name="artifact_paths",
            category=DIAG_MISSING_ARTIFACT_FILES,
            passed=False,
            summary="Missing required artifact files.",
            remedy="Verify NTB_FIXTURES_ROOT, refresh preserved artifacts if needed, and restore the missing files:\n"
            + "\n".join(f"      - {item}" for item in missing),
        )

    return DiagnosticCheck(
        name="artifact_paths",
        category="artifact_paths",
        passed=True,
        summary=f"Declared artifacts exist under {request.artifacts_root}.",
        remedy="None.",
    )


def _adapter_check(request: LaunchRequest) -> DiagnosticCheck:
    if request.mode == "fixture_demo":
        return DiagnosticCheck(
            name="adapter_binding",
            category="adapter_binding",
            passed=True,
            summary="Fixture profile does not require a model adapter binding.",
            remedy="None.",
        )

    try:
        resolve_model_adapter_binding(
            request.adapter_binding,
            profile_id=request.profile.profile_id,
        )
    except RuntimeDiagnosticError as exc:
        return DiagnosticCheck(
            name="adapter_binding",
            category=exc.category,
            passed=False,
            summary=exc.summary,
            remedy=exc.remedy,
        )

    return DiagnosticCheck(
        name="adapter_binding",
        category="adapter_binding",
        passed=True,
        summary=f"Adapter binding {request.adapter_binding} resolved successfully.",
        remedy="None.",
    )


def _artifact_contract_check(request: LaunchRequest) -> DiagnosticCheck:
    try:
        packet_bundle = None
        if request.mode == "preserved_engine":
            packet_bundle = load_json_object(request.profile.packet_bundle_path(request.artifacts_root))
        inputs = build_runtime_inputs_for_profile(
            request.artifacts_root,
            profile=request.profile,
            lockout=request.lockout,
            packet_bundle=packet_bundle,
        )
        if request.mode == "preserved_engine":
            validate_preserved_runtime_inputs(inputs, profile=request.profile)
    except Exception as exc:
        return DiagnosticCheck(
            name="artifact_contract",
            category=DIAG_INVALID_ARTIFACT_CONTRACT,
            passed=False,
            summary=f"Artifacts for profile {request.profile.profile_id} did not satisfy the runtime contract: {exc}",
            remedy="Inspect the selected artifacts, refresh preserved fixtures if appropriate, and replace malformed inputs rather than relaxing validation.",
        )

    return DiagnosticCheck(
        name="artifact_contract",
        category="artifact_contract",
        passed=True,
        summary=f"Artifacts for profile {request.profile.profile_id} satisfy the current runtime contract.",
        remedy="None.",
    )


def _required_artifact_paths(request: LaunchRequest) -> tuple[tuple[str, Path], ...]:
    profile = request.profile
    root = request.artifacts_root
    paths: list[tuple[str, Path]] = [
        ("pre-market packet", profile.premarket_packet_path(root)),
        ("pre-market brief", profile.premarket_brief_path(root)),
        ("live snapshot (armed)", profile.live_snapshot_path(root, lockout=False)),
        ("live snapshot (lockout)", profile.live_snapshot_path(root, lockout=True)),
        ("pipeline query", profile.pipeline_query_path(root)),
        ("run history", _resolve_history_path(root, profile)),
    ]

    if request.mode == "fixture_demo":
        paths.extend(
            [
                ("watchman context (armed)", profile.watchman_context_path(root, lockout=False)),
                ("watchman context (lockout)", profile.watchman_context_path(root, lockout=True)),
                ("pipeline summary", profile.pipeline_result_path(root)),
            ]
        )
    else:
        paths.append(("packet bundle", profile.packet_bundle_path(root)))
    return tuple(paths)


def _resolve_history_path(artifacts_root: Path, profile: RuntimeProfile) -> Path:
    dated_path = (
        artifacts_root
        / "history"
        / profile.artifact_contract_dir
        / f"run_history.{profile.session_date}.fixture.json"
    )
    if dated_path.exists():
        return dated_path
    return artifacts_root / "history" / profile.artifact_contract_dir / "run_history.fixture.json"


def _check_payload(check: DiagnosticCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "category": check.category,
        "passed": check.passed,
        "summary": check.summary,
        "remedy": check.remedy,
    }
