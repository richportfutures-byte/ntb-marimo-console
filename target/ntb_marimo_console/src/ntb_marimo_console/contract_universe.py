from __future__ import annotations

from typing import Final


FINAL_TARGET_CONTRACTS: Final[tuple[str, ...]] = ("ES", "NQ", "CL", "6E", "MGC")
EXCLUDED_FINAL_TARGET_CONTRACTS: Final[tuple[str, ...]] = ("ZN", "GC")
LEGACY_HISTORICAL_CONTRACTS: Final[tuple[str, ...]] = ()
NEVER_SUPPORTED_CONTRACTS: Final[tuple[str, ...]] = ("GC",)


def normalize_contract_symbol(contract: str) -> str:
    return contract.strip().upper()


def final_target_contracts() -> tuple[str, ...]:
    return FINAL_TARGET_CONTRACTS


def excluded_final_target_contracts() -> tuple[str, ...]:
    return EXCLUDED_FINAL_TARGET_CONTRACTS


def legacy_historical_contracts() -> tuple[str, ...]:
    return LEGACY_HISTORICAL_CONTRACTS


def never_supported_contracts() -> tuple[str, ...]:
    return NEVER_SUPPORTED_CONTRACTS


def is_final_target_contract(contract: str) -> bool:
    return normalize_contract_symbol(contract) in FINAL_TARGET_CONTRACTS


def is_excluded_final_target_contract(contract: str) -> bool:
    return normalize_contract_symbol(contract) in EXCLUDED_FINAL_TARGET_CONTRACTS


def is_legacy_historical_contract(contract: str) -> bool:
    return normalize_contract_symbol(contract) in LEGACY_HISTORICAL_CONTRACTS


def is_never_supported_contract(contract: str) -> bool:
    return normalize_contract_symbol(contract) in NEVER_SUPPORTED_CONTRACTS


def contract_policy_label(contract: str) -> str:
    normalized = normalize_contract_symbol(contract)
    if normalized in FINAL_TARGET_CONTRACTS:
        return "final_target"
    if normalized in NEVER_SUPPORTED_CONTRACTS:
        return "never_supported_excluded"
    if normalized in EXCLUDED_FINAL_TARGET_CONTRACTS:
        return "excluded"
    if normalized in LEGACY_HISTORICAL_CONTRACTS:
        return "legacy_historical_excluded"
    return "unknown"
