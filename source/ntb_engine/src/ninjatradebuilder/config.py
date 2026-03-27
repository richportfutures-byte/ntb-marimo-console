from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
DEFAULT_GEMINI_TIMEOUT_SECONDS = 20
MIN_GEMINI_TIMEOUT_SECONDS = 10
DEFAULT_GEMINI_MAX_RETRIES = 1
DEFAULT_GEMINI_RETRY_INITIAL_DELAY_SECONDS = 1.0
DEFAULT_GEMINI_RETRY_MAX_DELAY_SECONDS = 4.0

MODEL_ENV_VAR = "NINJATRADEBUILDER_GEMINI_MODEL"
TIMEOUT_ENV_VAR = "NINJATRADEBUILDER_GEMINI_TIMEOUT_SECONDS"
MAX_RETRIES_ENV_VAR = "NINJATRADEBUILDER_GEMINI_MAX_RETRIES"
RETRY_INITIAL_DELAY_ENV_VAR = "NINJATRADEBUILDER_GEMINI_RETRY_INITIAL_DELAY_SECONDS"
RETRY_MAX_DELAY_ENV_VAR = "NINJATRADEBUILDER_GEMINI_RETRY_MAX_DELAY_SECONDS"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GeminiStartupConfig:
    api_key: str
    model: str
    timeout_seconds: int
    max_retries: int
    retry_initial_delay_seconds: float
    retry_max_delay_seconds: float

    @property
    def total_attempts(self) -> int:
        return self.max_retries + 1


def _read_int_env(name: str, default: int, *, minimum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return value


def _read_float_env(name: str, default: float, *, minimum: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return value


def load_gemini_startup_config(*, model: str | None = None) -> GeminiStartupConfig:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ConfigError("GEMINI_API_KEY is required for CLI execution.")

    resolved_model = (model or os.getenv(MODEL_ENV_VAR) or DEFAULT_GEMINI_MODEL).strip()
    if not resolved_model:
        raise ConfigError("Gemini model name must be non-empty.")

    timeout_seconds = _read_int_env(
        TIMEOUT_ENV_VAR,
        DEFAULT_GEMINI_TIMEOUT_SECONDS,
        minimum=MIN_GEMINI_TIMEOUT_SECONDS,
    )
    max_retries = _read_int_env(
        MAX_RETRIES_ENV_VAR,
        DEFAULT_GEMINI_MAX_RETRIES,
        minimum=0,
    )
    retry_initial_delay_seconds = _read_float_env(
        RETRY_INITIAL_DELAY_ENV_VAR,
        DEFAULT_GEMINI_RETRY_INITIAL_DELAY_SECONDS,
        minimum=0.0,
    )
    retry_max_delay_seconds = _read_float_env(
        RETRY_MAX_DELAY_ENV_VAR,
        DEFAULT_GEMINI_RETRY_MAX_DELAY_SECONDS,
        minimum=0.0,
    )
    if retry_max_delay_seconds < retry_initial_delay_seconds:
        raise ConfigError(
            f"{RETRY_MAX_DELAY_ENV_VAR} must be >= {RETRY_INITIAL_DELAY_ENV_VAR}."
        )

    return GeminiStartupConfig(
        api_key=api_key,
        model=resolved_model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_initial_delay_seconds=retry_initial_delay_seconds,
        retry_max_delay_seconds=retry_max_delay_seconds,
    )
