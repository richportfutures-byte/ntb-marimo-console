from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from .runtime_profiles import list_runtime_profiles

ProfileSwitchStatus = Literal["supported", "blocked", "unsupported", "already_active"]

_RUNTIME_MODE_LABELS: Final[dict[str, str]] = {
    "fixture_demo": "Fixture/Demo",
    "preserved_engine": "Preserved Engine",
}

_PROFILE_KIND_LABELS: Final[dict[str, str]] = {
    "fixture_demo": "Demo",
    "preserved_engine": "Preserved",
}

_BLOCK_REASON_LABELS: Final[dict[str, str]] = {
    "blocked_missing_authoritative_artifacts": "Missing authoritative artifacts",
    "blocked_incomplete_profile_template": "Incomplete profile template",
    "blocked_prompt_adapter_unavailable": "Prompt/adapter mapping unavailable",
    "blocked_unsupported_query_observable_contract": "Unsupported query observable contract",
    "blocked_missing_numeric_cross_asset_source": "Missing numeric cross-asset source",
    "blocked_runtime_preflight": "Strict preflight blocked",
    "blocked_runtime_assembly": "Runtime assembly blocked",
}


@dataclass(frozen=True)
class SupportedProfileDescriptor:
    profile_id: str
    runtime_mode: str
    runtime_mode_label: str
    profile_kind: str
    contract: str
    session_date: str
    active: bool

    @property
    def selection_label(self) -> str:
        active_suffix = " | active" if self.active else ""
        return (
            f"{self.profile_id} | {self.profile_kind} | {self.contract} | "
            f"{self.session_date}{active_suffix}"
        )


@dataclass(frozen=True)
class CandidateProfileDescriptor:
    contract: str
    profile_id: str
    status: str
    reason_category: str
    reason_label: str
    summary: str


@dataclass(frozen=True)
class ProfileOperationsSnapshot:
    current_profile_id: str | None
    supported_profiles: tuple[SupportedProfileDescriptor, ...]
    candidate_profiles: tuple[CandidateProfileDescriptor, ...]
    audit_available: bool
    audit_summary: str

    @property
    def selectable_profile_ids(self) -> tuple[str, ...]:
        return tuple(profile.profile_id for profile in self.supported_profiles)


@dataclass(frozen=True)
class ProfileSwitchEvaluation:
    requested_profile_id: str
    current_profile_id: str | None
    status: ProfileSwitchStatus
    summary: str
    next_action: str
    selected_profile: SupportedProfileDescriptor | None = None
    candidate_profile: CandidateProfileDescriptor | None = None


def build_profile_operations_snapshot(
    *,
    current_profile_id: str | None = None,
) -> ProfileOperationsSnapshot:
    supported_profiles = tuple(
        SupportedProfileDescriptor(
            profile_id=profile.profile_id,
            runtime_mode=profile.runtime_mode,
            runtime_mode_label=runtime_mode_label(profile.runtime_mode),
            profile_kind=profile_kind_label(profile.runtime_mode),
            contract=profile.contract,
            session_date=profile.session_date,
            active=profile.profile_id == current_profile_id,
        )
        for profile in list_runtime_profiles()
    )

    candidate_profiles: tuple[CandidateProfileDescriptor, ...] = tuple()
    audit_available = True
    audit_summary = "Candidate profile status reflects the current preserved-contract audit."
    try:
        from .preserved_contract_onboarding import build_contract_eligibility_snapshot

        audit_snapshot = build_contract_eligibility_snapshot()
        candidate_profiles = tuple(
            CandidateProfileDescriptor(
                contract=result.contract,
                profile_id=result.profile_id,
                status=result.status,
                reason_category=result.reason_category,
                reason_label=blocked_reason_label(result.reason_category),
                summary=result.summary,
            )
            for result in (*audit_snapshot.viable_to_onboard_now, *audit_snapshot.blocked)
        )
    except Exception as exc:
        audit_available = False
        audit_summary = (
            "Candidate profile audit is unavailable until the preserved-contract audit "
            f"dependencies load cleanly: {exc}"
        )

    return ProfileOperationsSnapshot(
        current_profile_id=current_profile_id,
        supported_profiles=supported_profiles,
        candidate_profiles=candidate_profiles,
        audit_available=audit_available,
        audit_summary=audit_summary,
    )


def evaluate_profile_switch(
    requested_profile_id: str,
    *,
    current_profile_id: str | None = None,
) -> ProfileSwitchEvaluation:
    snapshot = build_profile_operations_snapshot(current_profile_id=current_profile_id)

    if current_profile_id is not None and requested_profile_id == current_profile_id:
        return ProfileSwitchEvaluation(
            requested_profile_id=requested_profile_id,
            current_profile_id=current_profile_id,
            status="already_active",
            summary=(
                f"Profile switch blocked because {requested_profile_id} is already the active profile. "
                "No session state was changed."
            ),
            next_action="Select a different supported profile before requesting a profile switch.",
        )

    for profile in snapshot.supported_profiles:
        if profile.profile_id == requested_profile_id:
            return ProfileSwitchEvaluation(
                requested_profile_id=requested_profile_id,
                current_profile_id=current_profile_id,
                status="supported",
                summary=(
                    f"Profile {requested_profile_id} is supported and selectable. "
                    "Switching reruns preflight and rebuilds the session from that profile's declared artifacts."
                ),
                next_action="Run the profile switch and wait for the validation result.",
                selected_profile=profile,
            )

    for candidate in snapshot.candidate_profiles:
        if candidate.profile_id == requested_profile_id:
            return ProfileSwitchEvaluation(
                requested_profile_id=requested_profile_id,
                current_profile_id=current_profile_id,
                status="blocked",
                summary=(
                    f"Profile switch blocked because {requested_profile_id} is not currently supported. "
                    f"{candidate.reason_label}: {candidate.summary}"
                ),
                next_action=(
                    "Keep operating on one of the supported profiles until the blocked contract's "
                    "audit reason is resolved."
                ),
                candidate_profile=candidate,
            )

    supported_ids = ", ".join(snapshot.selectable_profile_ids)
    return ProfileSwitchEvaluation(
        requested_profile_id=requested_profile_id,
        current_profile_id=current_profile_id,
        status="unsupported",
        summary=(
            f"Profile switch blocked because {requested_profile_id} is not in the supported profile registry. "
            f"Supported profile ids: {supported_ids}"
        ),
        next_action="Select one of the supported profile ids shown in Supported Profiles.",
    )


def runtime_mode_label(runtime_mode: str) -> str:
    return _RUNTIME_MODE_LABELS.get(runtime_mode, runtime_mode)


def profile_kind_label(runtime_mode: str) -> str:
    return _PROFILE_KIND_LABELS.get(runtime_mode, runtime_mode)


def blocked_reason_label(reason_category: str) -> str:
    return _BLOCK_REASON_LABELS.get(reason_category, reason_category.replace("_", " ").title())
