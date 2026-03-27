from __future__ import annotations

import importlib
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .models import (
    CLContractExtensionInput,
    CLDatabentoHistoricalRequest,
    CLEiaTimingRequest,
    CLHistoricalDataInput,
    CLManualOverlayInput,
    ESBreadthSourceInput,
    ESCalendarSourceInput,
    ESCumulativeDeltaSourceInput,
    ESDatabentoCumulativeDeltaRequest,
    ESDatabentoHistoricalRequest,
    ESHistoricalDataInput,
    ESIndexCashToneSourceInput,
    ESManualOverlayInput,
    HistoricalBar,
    HistoricalObservedVolumeInput,
    HistoricalSessionRangeInput,
    MGCContractExtensionInput,
    MGCDatabentoHistoricalRequest,
    MGCHistoricalDataInput,
    MGCManualOverlayInput,
    NQContractExtensionInput,
    NQDatabentoHistoricalRequest,
    NQHistoricalDataInput,
    NQManualOverlayInput,
    NQRelativeStrengthComparisonInput,
    SixEContractExtensionInput,
    SixEDatabentoHistoricalRequest,
    SixEHistoricalDataInput,
    SixEManualOverlayInput,
    VolumeProfileLevel,
    ZNContractExtensionInput,
    ZNCash10YYieldSourceInput,
    ZNFredCash10YYieldRequest,
    ZNHistoricalDataInput,
    ZNManualOverlayInput,
)


class PacketCompilerSourceError(ValueError):
    pass


ET = ZoneInfo("America/New_York")
ES_RTH_START = time(9, 30)
ES_RTH_END = time(16, 0)
CL_RTH_START = time(9, 0)
CL_RTH_END = time(14, 30)
MGC_RTH_START = time(8, 20)
MGC_RTH_END = time(13, 15)
SIX_E_ASIA_START_UTC = time(0, 0)
SIX_E_ASIA_END_UTC = time(6, 59)
SIX_E_LONDON_START_UTC = time(7, 0)
SIX_E_LONDON_END_UTC = time(12, 59)
SIX_E_NY_START_UTC = time(13, 0)
SIX_E_NY_END_UTC = time(17, 0)
DEFAULT_DATABENTO_API_KEY_ENV_VAR = "DATABENTO_API_KEY"
DEFAULT_EIA_API_KEY_ENV_VAR = "EIA_API_KEY"
DEFAULT_FRED_API_KEY_ENV_VAR = "FRED_API_KEY"
DEFAULT_DATABENTO_LOOKBACK_CALENDAR_DAYS = 45


def _load_json_file(path: Path) -> object:
    if not path.is_file():
        raise PacketCompilerSourceError(f"Source file does not exist: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PacketCompilerSourceError(f"Source file did not contain valid JSON: {path}") from exc


@dataclass(frozen=True)
class JsonHistoricalMarketDataSource:
    path: Path

    def load_es_input(self) -> ESHistoricalDataInput:
        payload = _load_json_file(self.path)
        try:
            return ESHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Historical ES source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCLHistoricalMarketDataSource:
    path: Path

    def load_cl_input(self) -> CLHistoricalDataInput:
        payload = _load_json_file(self.path)
        try:
            return CLHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Historical CL source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonZNHistoricalMarketDataSource:
    path: Path

    def load_zn_input(self) -> ZNHistoricalDataInput:
        payload = _load_json_file(self.path)
        try:
            return ZNHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Historical ZN source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonNQHistoricalMarketDataSource:
    path: Path

    def load_nq_input(self) -> NQHistoricalDataInput:
        payload = _load_json_file(self.path)
        try:
            return NQHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Historical NQ source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonSixEHistoricalMarketDataSource:
    path: Path

    def load_six_e_input(self) -> SixEHistoricalDataInput:
        payload = _load_json_file(self.path)
        try:
            return SixEHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Historical 6E source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonMGCHistoricalMarketDataSource:
    path: Path

    def load_mgc_input(self) -> MGCHistoricalDataInput:
        payload = _load_json_file(self.path)
        try:
            return MGCHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Historical MGC source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCLDatabentoHistoricalRequestSource:
    path: Path

    def load_cl_request(self) -> CLDatabentoHistoricalRequest:
        payload = _load_json_file(self.path)
        try:
            return CLDatabentoHistoricalRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Databento CL historical request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonNQDatabentoHistoricalRequestSource:
    path: Path

    def load_nq_request(self) -> NQDatabentoHistoricalRequest:
        payload = _load_json_file(self.path)
        try:
            return NQDatabentoHistoricalRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Databento NQ historical request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonSixEDatabentoHistoricalRequestSource:
    path: Path

    def load_six_e_request(self) -> SixEDatabentoHistoricalRequest:
        payload = _load_json_file(self.path)
        try:
            return SixEDatabentoHistoricalRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Databento 6E historical request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonMGCDatabentoHistoricalRequestSource:
    path: Path

    def load_mgc_request(self) -> MGCDatabentoHistoricalRequest:
        payload = _load_json_file(self.path)
        try:
            return MGCDatabentoHistoricalRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Databento MGC historical request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCLEiaTimingRequestSource:
    path: Path

    def load_cl_request(self) -> CLEiaTimingRequest:
        payload = _load_json_file(self.path)
        try:
            return CLEiaTimingRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"CL EIA timing request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonDatabentoHistoricalRequestSource:
    path: Path

    def load_es_request(self) -> ESDatabentoHistoricalRequest:
        payload = _load_json_file(self.path)
        try:
            return ESDatabentoHistoricalRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Databento ES historical request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonDatabentoCumulativeDeltaRequestSource:
    path: Path

    def load_es_request(self) -> ESDatabentoCumulativeDeltaRequest:
        payload = _load_json_file(self.path)
        try:
            return ESDatabentoCumulativeDeltaRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Databento ES cumulative-delta request payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonManualOverlaySource:
    path: Path

    def load_es_overlay(self) -> ESManualOverlayInput:
        payload = _load_json_file(self.path)
        try:
            return ESManualOverlayInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Manual ES overlay payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCLManualOverlaySource:
    path: Path

    def load_cl_overlay(self) -> CLManualOverlayInput:
        payload = _load_json_file(self.path)
        try:
            return CLManualOverlayInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Manual CL overlay payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonZNManualOverlaySource:
    path: Path

    def load_zn_overlay(self) -> ZNManualOverlayInput:
        payload = _load_json_file(self.path)
        try:
            return ZNManualOverlayInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Manual ZN overlay payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonNQManualOverlaySource:
    path: Path

    def load_nq_overlay(self) -> NQManualOverlayInput:
        payload = _load_json_file(self.path)
        try:
            return NQManualOverlayInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Manual NQ overlay payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonSixEManualOverlaySource:
    path: Path

    def load_six_e_overlay(self) -> SixEManualOverlayInput:
        payload = _load_json_file(self.path)
        try:
            return SixEManualOverlayInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Manual 6E overlay payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonMGCManualOverlaySource:
    path: Path

    def load_mgc_overlay(self) -> MGCManualOverlayInput:
        payload = _load_json_file(self.path)
        try:
            return MGCManualOverlayInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"Manual MGC overlay payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonNQRelativeStrengthComparisonSource:
    path: Path

    def load_nq_relative_strength_input(self) -> NQRelativeStrengthComparisonInput:
        payload = _load_json_file(self.path)
        try:
            return NQRelativeStrengthComparisonInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"NQ relative_strength_vs_es comparison source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCalendarSource:
    path: Path

    def load_es_calendar(self) -> ESCalendarSourceInput:
        payload = _load_json_file(self.path)
        try:
            return ESCalendarSourceInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"ES calendar source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonBreadthSource:
    path: Path

    def load_es_breadth(self) -> ESBreadthSourceInput:
        payload = _load_json_file(self.path)
        try:
            return ESBreadthSourceInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"ES breadth source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonIndexCashToneSource:
    path: Path

    def load_es_index_cash_tone(self) -> ESIndexCashToneSourceInput:
        payload = _load_json_file(self.path)
        try:
            return ESIndexCashToneSourceInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"ES index cash tone source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCumulativeDeltaSource:
    path: Path

    def load_es_cumulative_delta(self) -> ESCumulativeDeltaSourceInput:
        payload = _load_json_file(self.path)
        try:
            return ESCumulativeDeltaSourceInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"ES cumulative delta source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonCLContractExtensionSource:
    path: Path

    def load_cl_extension(self) -> CLContractExtensionInput:
        payload = _load_json_file(self.path)
        try:
            return CLContractExtensionInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"CL extension source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonZNContractExtensionSource:
    path: Path

    def load_zn_extension(self) -> ZNContractExtensionInput:
        payload = _load_json_file(self.path)
        try:
            return ZNContractExtensionInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"ZN extension source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonNQContractExtensionSource:
    path: Path

    def load_nq_extension(self) -> NQContractExtensionInput:
        payload = _load_json_file(self.path)
        try:
            return NQContractExtensionInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"NQ extension source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonSixEContractExtensionSource:
    path: Path

    def load_six_e_extension(self) -> SixEContractExtensionInput:
        payload = _load_json_file(self.path)
        try:
            return SixEContractExtensionInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"6E extension source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonMGCContractExtensionSource:
    path: Path

    def load_mgc_extension(self) -> MGCContractExtensionInput:
        payload = _load_json_file(self.path)
        try:
            return MGCContractExtensionInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"MGC extension source payload was invalid: {self.path}"
            ) from exc


@dataclass(frozen=True)
class JsonZNFredCash10YYieldRequestSource:
    path: Path

    def load_zn_request(self) -> ZNFredCash10YYieldRequest:
        payload = _load_json_file(self.path)
        try:
            return ZNFredCash10YYieldRequest.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                f"ZN FRED cash_10y_yield request payload was invalid: {self.path}"
            ) from exc


def _build_databento_client(*, api_key_env_var: str, client_factory: Any | None) -> Any:
    api_key = os.getenv(api_key_env_var)
    if not api_key:
        raise PacketCompilerSourceError(
            f"{api_key_env_var} is required for Databento historical sourcing."
        )
    if client_factory is not None:
        return client_factory(api_key)
    try:
        databento = importlib.import_module("databento")
    except ImportError as exc:
        raise PacketCompilerSourceError(
            "Databento historical sourcing requires the optional databento dependency."
        ) from exc
    return databento.Historical(api_key)


def _fetch_json_url(url: str) -> object:
    with urllib.request.urlopen(url) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class FREDCash10YYieldSource:
    request: ZNFredCash10YYieldRequest
    api_key_env_var: str = DEFAULT_FRED_API_KEY_ENV_VAR
    fetch_json: Any | None = None

    def _build_url(self) -> str:
        api_key = os.getenv(self.api_key_env_var)
        if not api_key:
            raise PacketCompilerSourceError(
                f"{self.api_key_env_var} is required for FRED cash_10y_yield sourcing."
            )
        params = urllib.parse.urlencode(
            {
                "series_id": self.request.series_id,
                "observation_start": self.request.observation_date.isoformat(),
                "observation_end": self.request.observation_date.isoformat(),
                "api_key": api_key,
                "file_type": "json",
            }
        )
        return f"https://api.stlouisfed.org/fred/series/observations?{params}"

    def load_zn_cash_10y_yield(self) -> ZNCash10YYieldSourceInput:
        url = self._build_url()
        payload = (self.fetch_json or _fetch_json_url)(url)
        if not isinstance(payload, Mapping):
            raise PacketCompilerSourceError("FRED response must decode to a JSON object.")
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise PacketCompilerSourceError("FRED response was missing observations list.")
        if len(observations) != 1:
            raise PacketCompilerSourceError(
                "FRED response must contain exactly one observation for the requested date."
            )
        observation = observations[0]
        if not isinstance(observation, Mapping):
            raise PacketCompilerSourceError("FRED observation rows must be JSON objects.")
        observation_date = observation.get("date")
        if observation_date != self.request.observation_date.isoformat():
            raise PacketCompilerSourceError(
                "FRED observation date did not match the requested observation_date."
            )
        raw_value = observation.get("value")
        if raw_value in (None, "."):
            raise PacketCompilerSourceError(
                "FRED response did not contain a usable cash_10y_yield value for the requested date."
            )
        try:
            cash_10y_yield = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise PacketCompilerSourceError(
                "FRED cash_10y_yield value must be numeric."
            ) from exc
        try:
            return ZNCash10YYieldSourceInput.model_validate(
                {"contract": "ZN", "cash_10y_yield": cash_10y_yield}
            )
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "FRED response could not be mapped into a valid ZN cash_10y_yield input."
            ) from exc


def _normalize_records(response: Any) -> list[dict[str, Any]]:
    candidate = response
    if hasattr(candidate, "to_df"):
        candidate = candidate.to_df()
    if hasattr(candidate, "reset_index"):
        candidate = candidate.reset_index()
    if hasattr(candidate, "to_dict"):
        try:
            records = candidate.to_dict(orient="records")
        except TypeError:
            records = candidate.to_dict()
        if isinstance(records, list):
            return [dict(record) for record in records]
    if isinstance(candidate, list):
        return [dict(record) for record in candidate]
    raise PacketCompilerSourceError(
        "Databento response could not be normalized into record dictionaries."
    )


def _coerce_timestamp(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise PacketCompilerSourceError(f"Databento response field {field_name} must be a timestamp.")
    if dt.tzinfo is None:
        raise PacketCompilerSourceError(f"Databento response field {field_name} must be timezone-aware.")
    return dt.astimezone(UTC)


def _record_timestamp(record: Mapping[str, Any]) -> datetime:
    for key in ("ts_event", "timestamp", "ts_recv"):
        if key in record:
            return _coerce_timestamp(record[key], field_name=key)
    raise PacketCompilerSourceError("Databento response record was missing ts_event/timestamp.")


def _record_float(record: Mapping[str, Any], field_name: str) -> float:
    if field_name not in record:
        raise PacketCompilerSourceError(f"Databento response record was missing {field_name}.")
    try:
        return float(record[field_name])
    except (TypeError, ValueError) as exc:
        raise PacketCompilerSourceError(
            f"Databento response field {field_name} must be numeric."
        ) from exc


def _record_symbol(record: Mapping[str, Any]) -> str | None:
    for key in ("symbol", "raw_symbol"):
        value = record.get(key)
        if value is not None:
            return str(value)
    return None


def _bars_from_records(records: Iterable[Mapping[str, Any]], *, symbol: str) -> list[HistoricalBar]:
    normalized: list[HistoricalBar] = []
    seen_symbols: set[str] = set()
    for record in records:
        record_symbol = _record_symbol(record)
        if record_symbol is not None:
            seen_symbols.add(record_symbol)
            if record_symbol != symbol:
                continue
        normalized.append(
            HistoricalBar.model_validate(
                {
                    "timestamp": _record_timestamp(record),
                    "open": _record_float(record, "open"),
                    "high": _record_float(record, "high"),
                    "low": _record_float(record, "low"),
                    "close": _record_float(record, "close"),
                    "volume": _record_float(record, "volume"),
                }
            )
        )
    if seen_symbols and symbol not in seen_symbols:
        raise PacketCompilerSourceError(
            f"Databento bar response did not contain the requested symbol: {symbol}"
        )
    if not normalized:
        raise PacketCompilerSourceError("Databento bar response produced no usable records.")
    return normalized


def _trade_levels_from_records(
    records: Iterable[Mapping[str, Any]],
    *,
    symbol: str,
) -> list[tuple[datetime, float, float]]:
    normalized: list[tuple[datetime, float, float]] = []
    seen_symbols: set[str] = set()
    for record in records:
        record_symbol = _record_symbol(record)
        if record_symbol is not None:
            seen_symbols.add(record_symbol)
            if record_symbol != symbol:
                continue
        timestamp = _record_timestamp(record)
        price = _record_float(record, "price")
        size_field = "size" if "size" in record else "volume"
        volume = _record_float(record, size_field)
        normalized.append((timestamp, price, volume))
    if seen_symbols and symbol not in seen_symbols:
        raise PacketCompilerSourceError(
            f"Databento trade response did not contain the requested symbol: {symbol}"
        )
    if not normalized:
        raise PacketCompilerSourceError("Databento trade response produced no usable records.")
    return normalized


def _session_bounds(
    session_date: date,
    *,
    session_start: time,
    session_end: time,
) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, session_start, tzinfo=ET).astimezone(UTC)
    end = datetime.combine(session_date, session_end, tzinfo=ET).astimezone(UTC)
    return start, end


def _rth_bounds(session_date: date) -> tuple[datetime, datetime]:
    return _session_bounds(session_date, session_start=ES_RTH_START, session_end=ES_RTH_END)


def _cl_rth_bounds(session_date: date) -> tuple[datetime, datetime]:
    return _session_bounds(session_date, session_start=CL_RTH_START, session_end=CL_RTH_END)


def _mgc_rth_bounds(session_date: date) -> tuple[datetime, datetime]:
    return _session_bounds(session_date, session_start=MGC_RTH_START, session_end=MGC_RTH_END)


def _session_date_for_bar(bar: HistoricalBar) -> date:
    return bar.timestamp.astimezone(ET).date()


def _is_session_bar(
    bar: HistoricalBar,
    *,
    session_date: date,
    session_start: time,
    session_end: time,
) -> bool:
    ts_et = bar.timestamp.astimezone(ET)
    return (
        ts_et.date() == session_date
        and session_start <= ts_et.timetz().replace(tzinfo=None) <= session_end
    )


def _is_rth_bar(bar: HistoricalBar, *, session_date: date) -> bool:
    return _is_session_bar(
        bar,
        session_date=session_date,
        session_start=ES_RTH_START,
        session_end=ES_RTH_END,
    )


def _is_cl_rth_bar(bar: HistoricalBar, *, session_date: date) -> bool:
    return _is_session_bar(
        bar,
        session_date=session_date,
        session_start=CL_RTH_START,
        session_end=CL_RTH_END,
    )


def _is_mgc_rth_bar(bar: HistoricalBar, *, session_date: date) -> bool:
    return _is_session_bar(
        bar,
        session_date=session_date,
        session_start=MGC_RTH_START,
        session_end=MGC_RTH_END,
    )


def _aggregate_profile_for_bounds(
    trades: list[tuple[datetime, float, float]],
    *,
    start: datetime,
    end: datetime,
    coverage_label: str,
) -> list[VolumeProfileLevel]:
    by_price: dict[float, float] = {}
    for timestamp, price, volume in trades:
        if start <= timestamp <= end:
            by_price[price] = by_price.get(price, 0.0) + volume
    if not by_price:
        raise PacketCompilerSourceError(
            f"Databento trade response did not contain usable {coverage_label} trades."
        )
    return [
        VolumeProfileLevel.model_validate({"price": price, "volume": volume})
        for price, volume in sorted(by_price.items())
    ]


def _aggregate_profile(
    trades: list[tuple[datetime, float, float]],
    *,
    session_date: date,
) -> list[VolumeProfileLevel]:
    start, end = _rth_bounds(session_date)
    return _aggregate_profile_for_bounds(
        trades,
        start=start,
        end=end,
        coverage_label=f"RTH trades for {session_date.isoformat()}",
    )


def _aggregate_cl_profile(
    trades: list[tuple[datetime, float, float]],
    *,
    session_date: date,
) -> list[VolumeProfileLevel]:
    start, end = _cl_rth_bounds(session_date)
    return _aggregate_profile_for_bounds(
        trades,
        start=start,
        end=end,
        coverage_label=f"CL RTH trades for {session_date.isoformat()}",
    )


def _aggregate_mgc_profile(
    trades: list[tuple[datetime, float, float]],
    *,
    session_date: date,
) -> list[VolumeProfileLevel]:
    start, end = _mgc_rth_bounds(session_date)
    return _aggregate_profile_for_bounds(
        trades,
        start=start,
        end=end,
        coverage_label=f"MGC RTH trades for {session_date.isoformat()}",
    )


def _group_session_bars_by_date(
    bars: list[HistoricalBar],
    *,
    session_start: time,
    session_end: time,
) -> dict[date, list[HistoricalBar]]:
    grouped: dict[date, list[HistoricalBar]] = {}
    for bar in bars:
        session_date = _session_date_for_bar(bar)
        if _is_session_bar(
            bar,
            session_date=session_date,
            session_start=session_start,
            session_end=session_end,
        ):
            grouped.setdefault(session_date, []).append(bar)
    return grouped


def _group_rth_bars_by_date(bars: list[HistoricalBar]) -> dict[date, list[HistoricalBar]]:
    return _group_session_bars_by_date(
        bars,
        session_start=ES_RTH_START,
        session_end=ES_RTH_END,
    )


def _group_cl_rth_bars_by_date(bars: list[HistoricalBar]) -> dict[date, list[HistoricalBar]]:
    return _group_session_bars_by_date(
        bars,
        session_start=CL_RTH_START,
        session_end=CL_RTH_END,
    )


def _group_mgc_rth_bars_by_date(bars: list[HistoricalBar]) -> dict[date, list[HistoricalBar]]:
    return _group_session_bars_by_date(
        bars,
        session_start=MGC_RTH_START,
        session_end=MGC_RTH_END,
    )


def _utc_window_bounds(
    session_date: date,
    *,
    session_start: time,
    session_end: time,
) -> tuple[datetime, datetime]:
    start = datetime.combine(session_date, session_start, tzinfo=UTC)
    end = datetime.combine(session_date, session_end, tzinfo=UTC)
    return start, end


def _is_utc_window_bar(
    bar: HistoricalBar,
    *,
    session_date: date,
    session_start: time,
    session_end: time,
) -> bool:
    ts_utc = bar.timestamp.astimezone(UTC)
    return (
        ts_utc.date() == session_date
        and session_start <= ts_utc.timetz().replace(tzinfo=None) <= session_end
    )


def _group_utc_window_bars_by_date(
    bars: list[HistoricalBar],
    *,
    session_start: time,
    session_end: time,
) -> dict[date, list[HistoricalBar]]:
    grouped: dict[date, list[HistoricalBar]] = {}
    for bar in bars:
        session_date = bar.timestamp.astimezone(UTC).date()
        if _is_utc_window_bar(
            bar,
            session_date=session_date,
            session_start=session_start,
            session_end=session_end,
        ):
            grouped.setdefault(session_date, []).append(bar)
    return grouped


def _profile_session_midpoint(levels: list[VolumeProfileLevel]) -> float:
    return (levels[0].price + levels[-1].price) / 2.0


def _profile_poc_index(levels: list[VolumeProfileLevel]) -> int:
    max_volume = max(level.volume for level in levels)
    candidates = [index for index, level in enumerate(levels) if level.volume == max_volume]
    midpoint = _profile_session_midpoint(levels)
    return min(candidates, key=lambda index: (abs(levels[index].price - midpoint), levels[index].price))


def _choose_profile_expansion_side(
    levels: list[VolumeProfileLevel],
    *,
    lower_index: int | None,
    upper_index: int | None,
) -> str:
    if lower_index is None:
        return "upper"
    if upper_index is None:
        return "lower"

    lower_volume = levels[lower_index].volume
    upper_volume = levels[upper_index].volume
    if upper_volume > lower_volume:
        return "upper"
    if lower_volume > upper_volume:
        return "lower"

    midpoint = _profile_session_midpoint(levels)
    lower_distance = abs(levels[lower_index].price - midpoint)
    upper_distance = abs(levels[upper_index].price - midpoint)
    if lower_distance < upper_distance:
        return "lower"
    if upper_distance < lower_distance:
        return "upper"
    return "lower"


def _derive_profile_levels(levels: list[VolumeProfileLevel]) -> dict[str, float]:
    total_volume = sum(level.volume for level in levels)
    target_volume = total_volume * 0.70
    poc_index = _profile_poc_index(levels)
    included_indices = {poc_index}
    cumulative_volume = levels[poc_index].volume
    low_index = poc_index
    high_index = poc_index

    while cumulative_volume < target_volume:
        candidate_lower = low_index - 1 if low_index > 0 else None
        candidate_upper = high_index + 1 if high_index < len(levels) - 1 else None
        if candidate_lower is None and candidate_upper is None:
            break
        chosen_side = _choose_profile_expansion_side(
            levels,
            lower_index=candidate_lower,
            upper_index=candidate_upper,
        )
        if chosen_side == "lower":
            assert candidate_lower is not None
            included_indices.add(candidate_lower)
            cumulative_volume += levels[candidate_lower].volume
            low_index = candidate_lower
        else:
            assert candidate_upper is not None
            included_indices.add(candidate_upper)
            cumulative_volume += levels[candidate_upper].volume
            high_index = candidate_upper

    selected_levels = [levels[index] for index in sorted(included_indices)]
    return {
        "poc": levels[poc_index].price,
        "vah": selected_levels[-1].price,
        "val": selected_levels[0].price,
    }


@dataclass(frozen=True)
class DatabentoHistoricalMarketDataSource:
    request: ESDatabentoHistoricalRequest
    api_key_env_var: str = DEFAULT_DATABENTO_API_KEY_ENV_VAR
    client_factory: Any | None = None

    def _build_client(self) -> Any:
        return _build_databento_client(
            api_key_env_var=self.api_key_env_var,
            client_factory=self.client_factory,
        )

    def _query_time_range(self) -> tuple[str, str]:
        lookback_start = datetime.combine(
            self.request.current_session_date - timedelta(days=DEFAULT_DATABENTO_LOOKBACK_CALENDAR_DAYS),
            time(0, 0),
            tzinfo=ET,
        ).astimezone(UTC)
        _, current_rth_end = _rth_bounds(self.request.current_session_date)
        query_end = current_rth_end + timedelta(minutes=1)
        return (
            lookback_start.isoformat().replace("+00:00", "Z"),
            query_end.isoformat().replace("+00:00", "Z"),
        )

    def load_es_input(self) -> ESHistoricalDataInput:
        client = self._build_client()
        start, end = self._query_time_range()
        if self.request.bar_schema != "ohlcv-1m" or self.request.trades_schema != "trades":
            raise PacketCompilerSourceError("Databento ES historical sourcing only supports ohlcv-1m and trades.")

        bars_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.bar_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )
        trades_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.trades_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )

        bars = _bars_from_records(_normalize_records(bars_response), symbol=self.request.symbol)
        trades = _trade_levels_from_records(_normalize_records(trades_response), symbol=self.request.symbol)

        rth_by_date = _group_rth_bars_by_date(bars)
        current_rth_bars = rth_by_date.get(self.request.current_session_date)
        if not current_rth_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current RTH coverage for {self.request.current_session_date.isoformat()}."
            )

        prior_dates = sorted(session_date for session_date in rth_by_date if session_date < self.request.current_session_date)
        if len(prior_dates) < 20:
            raise PacketCompilerSourceError(
                "Databento response did not contain 20 completed prior RTH sessions."
            )
        prior_20_dates = prior_dates[-20:]
        prior_session_date = prior_20_dates[-1]
        prior_rth_bars = rth_by_date[prior_session_date]

        prior_rth_end = prior_rth_bars[-1].timestamp
        current_rth_start = current_rth_bars[0].timestamp
        overnight_bars = [
            bar
            for bar in bars
            if prior_rth_end < bar.timestamp < current_rth_start
        ]
        if not overnight_bars:
            raise PacketCompilerSourceError("Databento response did not contain overnight bar coverage.")

        week_start_date = self.request.current_session_date - timedelta(days=self.request.current_session_date.weekday())
        weekly_candidates = [
            bar
            for session_date in sorted(rth_by_date)
            if week_start_date <= session_date <= self.request.current_session_date
            for bar in rth_by_date[session_date]
        ]
        if not weekly_candidates:
            raise PacketCompilerSourceError("Databento response did not contain a weekly open bar.")
        weekly_open_bar = weekly_candidates[0]

        current_start = current_rth_bars[0].timestamp
        current_end = current_rth_bars[-1].timestamp
        observed_duration = current_end - current_start

        prior_20_rth_sessions = [
            HistoricalSessionRangeInput.model_validate(
                {
                    "session_date": session_date,
                    "high": max(bar.high for bar in rth_by_date[session_date]),
                    "low": min(bar.low for bar in rth_by_date[session_date]),
                }
            )
            for session_date in prior_20_dates
        ]

        prior_20_rth_observed_volumes = []
        for session_date in prior_20_dates:
            session_bars = rth_by_date[session_date]
            session_start = session_bars[0].timestamp
            session_cutoff = session_start + observed_duration
            observed_volume = sum(bar.volume for bar in session_bars if bar.timestamp <= session_cutoff)
            prior_20_rth_observed_volumes.append(
                HistoricalObservedVolumeInput.model_validate(
                    {"session_date": session_date, "observed_volume": observed_volume}
                )
            )

        payload = {
            "contract": "ES",
            "prior_rth_bars": [bar.model_dump(mode="json") for bar in prior_rth_bars],
            "overnight_bars": [bar.model_dump(mode="json") for bar in overnight_bars],
            "current_rth_bars": [bar.model_dump(mode="json") for bar in current_rth_bars],
            "weekly_open_bar": weekly_open_bar.model_dump(mode="json"),
            "prior_rth_volume_profile": [
                level.model_dump(mode="json")
                for level in _aggregate_profile(trades, session_date=prior_session_date)
            ],
            "current_rth_volume_profile": [
                level.model_dump(mode="json")
                for level in _aggregate_profile(trades, session_date=self.request.current_session_date)
            ],
            "prior_20_rth_sessions": [
                session.model_dump(mode="json") for session in prior_20_rth_sessions
            ],
            "prior_20_rth_observed_volumes": [
                session.model_dump(mode="json") for session in prior_20_rth_observed_volumes
            ],
        }
        try:
            return ESHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "Databento historical response could not be mapped into a valid ES historical input."
            ) from exc


@dataclass(frozen=True)
class DatabentoCLHistoricalMarketDataSource:
    request: CLDatabentoHistoricalRequest
    api_key_env_var: str = DEFAULT_DATABENTO_API_KEY_ENV_VAR
    client_factory: Any | None = None

    def _build_client(self) -> Any:
        return _build_databento_client(
            api_key_env_var=self.api_key_env_var,
            client_factory=self.client_factory,
        )

    def _query_time_range(self) -> tuple[str, str]:
        lookback_start = datetime.combine(
            self.request.current_session_date - timedelta(days=DEFAULT_DATABENTO_LOOKBACK_CALENDAR_DAYS),
            time(0, 0),
            tzinfo=ET,
        ).astimezone(UTC)
        _, current_rth_end = _cl_rth_bounds(self.request.current_session_date)
        query_end = current_rth_end + timedelta(minutes=1)
        return (
            lookback_start.isoformat().replace("+00:00", "Z"),
            query_end.isoformat().replace("+00:00", "Z"),
        )

    def load_cl_input(self) -> CLHistoricalDataInput:
        client = self._build_client()
        start, end = self._query_time_range()
        if self.request.bar_schema != "ohlcv-1m" or self.request.trades_schema != "trades":
            raise PacketCompilerSourceError(
                "Databento CL historical sourcing only supports ohlcv-1m and trades."
            )

        bars_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.bar_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )
        trades_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.trades_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )

        bars = _bars_from_records(_normalize_records(bars_response), symbol=self.request.symbol)
        trades = _trade_levels_from_records(_normalize_records(trades_response), symbol=self.request.symbol)

        rth_by_date = _group_cl_rth_bars_by_date(bars)
        current_rth_bars = rth_by_date.get(self.request.current_session_date)
        if not current_rth_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current CL RTH coverage for {self.request.current_session_date.isoformat()}."
            )

        prior_dates = sorted(
            session_date for session_date in rth_by_date if session_date < self.request.current_session_date
        )
        if len(prior_dates) < 20:
            raise PacketCompilerSourceError(
                "Databento response did not contain 20 completed prior CL RTH sessions."
            )
        prior_20_dates = prior_dates[-20:]
        prior_session_date = prior_20_dates[-1]
        prior_rth_bars = rth_by_date[prior_session_date]

        prior_rth_end = prior_rth_bars[-1].timestamp
        current_rth_start = current_rth_bars[0].timestamp
        overnight_bars = [bar for bar in bars if prior_rth_end < bar.timestamp < current_rth_start]
        if not overnight_bars:
            raise PacketCompilerSourceError("Databento response did not contain CL overnight bar coverage.")

        current_start = current_rth_bars[0].timestamp
        current_end = current_rth_bars[-1].timestamp
        observed_duration = current_end - current_start

        prior_20_ranges = [
            max(bar.high for bar in rth_by_date[session_date]) - min(bar.low for bar in rth_by_date[session_date])
            for session_date in prior_20_dates
        ]
        average_range = round(sum(prior_20_ranges) / len(prior_20_ranges), 4)

        prior_observed_volumes = []
        for session_date in prior_20_dates:
            session_bars = rth_by_date[session_date]
            session_start = session_bars[0].timestamp
            session_cutoff = session_start + observed_duration
            observed_volume = sum(bar.volume for bar in session_bars if bar.timestamp <= session_cutoff)
            if observed_volume <= 0:
                raise PacketCompilerSourceError(
                    "Databento response did not contain usable matched-window CL volume coverage."
                )
            prior_observed_volumes.append(observed_volume)

        current_profile = _derive_profile_levels(
            _aggregate_cl_profile(trades, session_date=self.request.current_session_date)
        )
        previous_profile = _derive_profile_levels(
            _aggregate_cl_profile(trades, session_date=prior_session_date)
        )

        current_vwap_numerator = sum(
            (((bar.high + bar.low + bar.close) / 3.0) * bar.volume) for bar in current_rth_bars
        )
        current_volume = sum(bar.volume for bar in current_rth_bars)
        if current_volume <= 0:
            raise PacketCompilerSourceError("Databento response did not contain usable CL current-session volume.")

        signed_delta = 0.0
        seen_symbols: set[str] = set()
        matched_trades = 0
        current_start_bound, current_end_bound = _cl_rth_bounds(self.request.current_session_date)
        for record in _normalize_records(trades_response):
            record_symbol = _record_symbol(record)
            if record_symbol is not None:
                seen_symbols.add(record_symbol)
                if record_symbol != self.request.symbol:
                    continue
            timestamp = _record_timestamp(record)
            if not (current_start_bound <= timestamp <= current_end_bound):
                continue
            if "side" not in record:
                raise PacketCompilerSourceError(
                    "Databento CL historical trade records must include side for cumulative delta."
                )
            side = str(record["side"]).strip().lower()
            size_field = "size" if "size" in record else "volume"
            volume = _record_float(record, size_field)
            if side in {"a", "ask", "sell"}:
                signed_delta -= volume
            elif side in {"b", "bid", "buy"}:
                signed_delta += volume
            else:
                raise PacketCompilerSourceError(
                    "Databento CL historical trade side values must be bid/ask aligned."
                )
            matched_trades += 1
        if seen_symbols and self.request.symbol not in seen_symbols:
            raise PacketCompilerSourceError(
                f"Databento CL historical response did not contain the requested symbol: {self.request.symbol}"
            )
        if matched_trades == 0:
            raise PacketCompilerSourceError(
                "Databento CL historical response did not contain usable current-session trade coverage."
            )

        payload = {
            "contract": "CL",
            "timestamp": current_end,
            "current_price": current_rth_bars[-1].close,
            "session_open": current_rth_bars[0].open,
            "prior_day_high": max(bar.high for bar in prior_rth_bars),
            "prior_day_low": min(bar.low for bar in prior_rth_bars),
            "prior_day_close": prior_rth_bars[-1].close,
            "overnight_high": max(bar.high for bar in overnight_bars),
            "overnight_low": min(bar.low for bar in overnight_bars),
            "current_session_vah": current_profile["vah"],
            "current_session_val": current_profile["val"],
            "current_session_poc": current_profile["poc"],
            "previous_session_vah": previous_profile["vah"],
            "previous_session_val": previous_profile["val"],
            "previous_session_poc": previous_profile["poc"],
            "vwap": round(current_vwap_numerator / current_volume, 4),
            "session_range": round(
                max(bar.high for bar in current_rth_bars) - min(bar.low for bar in current_rth_bars),
                4,
            ),
            "avg_20d_session_range": average_range,
            "cumulative_delta": round(signed_delta, 4),
            "current_volume_vs_average": round(
                current_volume / (sum(prior_observed_volumes) / len(prior_observed_volumes)),
                4,
            ),
            "event_calendar_remainder": [],
        }
        try:
            return CLHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "Databento historical response could not be mapped into a valid CL historical input."
            ) from exc


@dataclass(frozen=True)
class DatabentoNQHistoricalMarketDataSource:
    request: NQDatabentoHistoricalRequest
    api_key_env_var: str = DEFAULT_DATABENTO_API_KEY_ENV_VAR
    client_factory: Any | None = None

    def _build_client(self) -> Any:
        return _build_databento_client(
            api_key_env_var=self.api_key_env_var,
            client_factory=self.client_factory,
        )

    def _query_time_range(self) -> tuple[str, str]:
        lookback_start = datetime.combine(
            self.request.current_session_date - timedelta(days=DEFAULT_DATABENTO_LOOKBACK_CALENDAR_DAYS),
            time(0, 0),
            tzinfo=ET,
        ).astimezone(UTC)
        _, current_rth_end = _rth_bounds(self.request.current_session_date)
        query_end = current_rth_end + timedelta(minutes=1)
        return (
            lookback_start.isoformat().replace("+00:00", "Z"),
            query_end.isoformat().replace("+00:00", "Z"),
        )

    def load_nq_input(self) -> NQHistoricalDataInput:
        client = self._build_client()
        start, end = self._query_time_range()
        if self.request.bar_schema != "ohlcv-1m" or self.request.trades_schema != "trades":
            raise PacketCompilerSourceError(
                "Databento NQ historical sourcing only supports ohlcv-1m and trades."
            )

        bars_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.bar_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )
        trades_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.trades_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )

        bars = _bars_from_records(_normalize_records(bars_response), symbol=self.request.symbol)
        trades = _trade_levels_from_records(_normalize_records(trades_response), symbol=self.request.symbol)

        rth_by_date = _group_rth_bars_by_date(bars)
        current_rth_bars = rth_by_date.get(self.request.current_session_date)
        if not current_rth_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current NQ RTH coverage for {self.request.current_session_date.isoformat()}."
            )

        prior_dates = sorted(
            session_date for session_date in rth_by_date if session_date < self.request.current_session_date
        )
        if len(prior_dates) < 20:
            raise PacketCompilerSourceError(
                "Databento response did not contain 20 completed prior NQ RTH sessions."
            )
        prior_20_dates = prior_dates[-20:]
        prior_session_date = prior_20_dates[-1]
        prior_rth_bars = rth_by_date[prior_session_date]

        prior_rth_end = prior_rth_bars[-1].timestamp
        current_rth_start = current_rth_bars[0].timestamp
        overnight_bars = [bar for bar in bars if prior_rth_end < bar.timestamp < current_rth_start]
        if not overnight_bars:
            raise PacketCompilerSourceError("Databento response did not contain NQ overnight bar coverage.")

        current_start = current_rth_bars[0].timestamp
        current_end = current_rth_bars[-1].timestamp
        observed_duration = current_end - current_start

        prior_20_ranges = [
            max(bar.high for bar in rth_by_date[session_date]) - min(bar.low for bar in rth_by_date[session_date])
            for session_date in prior_20_dates
        ]
        average_range = round(sum(prior_20_ranges) / len(prior_20_ranges), 4)

        prior_observed_volumes = []
        for session_date in prior_20_dates:
            session_bars = rth_by_date[session_date]
            session_start = session_bars[0].timestamp
            session_cutoff = session_start + observed_duration
            observed_volume = sum(bar.volume for bar in session_bars if bar.timestamp <= session_cutoff)
            if observed_volume <= 0:
                raise PacketCompilerSourceError(
                    "Databento response did not contain usable matched-window NQ volume coverage."
                )
            prior_observed_volumes.append(observed_volume)

        current_profile = _derive_profile_levels(
            _aggregate_profile(trades, session_date=self.request.current_session_date)
        )
        previous_profile = _derive_profile_levels(
            _aggregate_profile(trades, session_date=prior_session_date)
        )

        current_vwap_numerator = sum(
            (((bar.high + bar.low + bar.close) / 3.0) * bar.volume) for bar in current_rth_bars
        )
        current_volume = sum(bar.volume for bar in current_rth_bars)
        if current_volume <= 0:
            raise PacketCompilerSourceError("Databento response did not contain usable NQ current-session volume.")

        signed_delta = 0.0
        seen_symbols: set[str] = set()
        matched_trades = 0
        current_start_bound, current_end_bound = _rth_bounds(self.request.current_session_date)
        for record in _normalize_records(trades_response):
            record_symbol = _record_symbol(record)
            if record_symbol is not None:
                seen_symbols.add(record_symbol)
                if record_symbol != self.request.symbol:
                    continue
            timestamp = _record_timestamp(record)
            if not (current_start_bound <= timestamp <= current_end_bound):
                continue
            if "side" not in record:
                raise PacketCompilerSourceError(
                    "Databento NQ historical trade records must include side for cumulative delta."
                )
            side = str(record["side"]).strip().lower()
            size_field = "size" if "size" in record else "volume"
            volume = _record_float(record, size_field)
            if side in {"a", "ask", "sell"}:
                signed_delta -= volume
            elif side in {"b", "bid", "buy"}:
                signed_delta += volume
            else:
                raise PacketCompilerSourceError(
                    "Databento NQ historical trade side values must be bid/ask aligned."
                )
            matched_trades += 1
        if seen_symbols and self.request.symbol not in seen_symbols:
            raise PacketCompilerSourceError(
                f"Databento NQ historical response did not contain the requested symbol: {self.request.symbol}"
            )
        if matched_trades == 0:
            raise PacketCompilerSourceError(
                "Databento NQ historical response did not contain usable current-session trade coverage."
            )

        payload = {
            "contract": "NQ",
            "timestamp": current_end,
            "current_price": current_rth_bars[-1].close,
            "session_open": current_rth_bars[0].open,
            "prior_day_high": max(bar.high for bar in prior_rth_bars),
            "prior_day_low": min(bar.low for bar in prior_rth_bars),
            "prior_day_close": prior_rth_bars[-1].close,
            "overnight_high": max(bar.high for bar in overnight_bars),
            "overnight_low": min(bar.low for bar in overnight_bars),
            "current_session_vah": current_profile["vah"],
            "current_session_val": current_profile["val"],
            "current_session_poc": current_profile["poc"],
            "previous_session_vah": previous_profile["vah"],
            "previous_session_val": previous_profile["val"],
            "previous_session_poc": previous_profile["poc"],
            "vwap": round(current_vwap_numerator / current_volume, 4),
            "session_range": round(
                max(bar.high for bar in current_rth_bars) - min(bar.low for bar in current_rth_bars),
                4,
            ),
            "avg_20d_session_range": average_range,
            "cumulative_delta": round(signed_delta, 4),
            "current_volume_vs_average": round(
                current_volume / (sum(prior_observed_volumes) / len(prior_observed_volumes)),
                4,
            ),
            "event_calendar_remainder": [],
        }
        try:
            return NQHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "Databento historical response could not be mapped into a valid NQ historical input."
            ) from exc


@dataclass(frozen=True)
class DatabentoSixEHistoricalMarketDataSource:
    request: SixEDatabentoHistoricalRequest
    api_key_env_var: str = DEFAULT_DATABENTO_API_KEY_ENV_VAR
    client_factory: Any | None = None

    def _build_client(self) -> Any:
        return _build_databento_client(
            api_key_env_var=self.api_key_env_var,
            client_factory=self.client_factory,
        )

    def _query_time_range(self) -> tuple[str, str]:
        lookback_start = datetime.combine(
            self.request.current_session_date - timedelta(days=DEFAULT_DATABENTO_LOOKBACK_CALENDAR_DAYS),
            time(0, 0),
            tzinfo=UTC,
        )
        _, ny_session_end = _utc_window_bounds(
            self.request.current_session_date,
            session_start=SIX_E_NY_START_UTC,
            session_end=SIX_E_NY_END_UTC,
        )
        query_end = ny_session_end + timedelta(minutes=1)
        return (
            lookback_start.isoformat().replace("+00:00", "Z"),
            query_end.isoformat().replace("+00:00", "Z"),
        )

    def load_six_e_input(self) -> SixEHistoricalDataInput:
        client = self._build_client()
        start, end = self._query_time_range()
        if self.request.bar_schema != "ohlcv-1m" or self.request.trades_schema != "trades":
            raise PacketCompilerSourceError(
                "Databento 6E historical sourcing only supports ohlcv-1m and trades."
            )

        bars_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.bar_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )
        trades_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.trades_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )

        bars = _bars_from_records(_normalize_records(bars_response), symbol=self.request.symbol)
        trades = _trade_levels_from_records(_normalize_records(trades_response), symbol=self.request.symbol)

        ny_by_date = _group_utc_window_bars_by_date(
            bars,
            session_start=SIX_E_NY_START_UTC,
            session_end=SIX_E_NY_END_UTC,
        )
        asia_by_date = _group_utc_window_bars_by_date(
            bars,
            session_start=SIX_E_ASIA_START_UTC,
            session_end=SIX_E_ASIA_END_UTC,
        )
        london_by_date = _group_utc_window_bars_by_date(
            bars,
            session_start=SIX_E_LONDON_START_UTC,
            session_end=SIX_E_LONDON_END_UTC,
        )

        current_ny_bars = ny_by_date.get(self.request.current_session_date)
        current_asia_bars = asia_by_date.get(self.request.current_session_date)
        current_london_bars = london_by_date.get(self.request.current_session_date)
        if not current_asia_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current 6E Asia coverage for {self.request.current_session_date.isoformat()}."
            )
        if not current_london_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current 6E London coverage for {self.request.current_session_date.isoformat()}."
            )
        if not current_ny_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current 6E NY coverage for {self.request.current_session_date.isoformat()}."
            )

        prior_dates = sorted(
            session_date for session_date in ny_by_date if session_date < self.request.current_session_date
        )
        if len(prior_dates) < 20:
            raise PacketCompilerSourceError(
                "Databento response did not contain 20 completed prior 6E NY sessions."
            )
        prior_20_dates = prior_dates[-20:]
        prior_session_date = prior_20_dates[-1]
        prior_ny_bars = ny_by_date[prior_session_date]

        prior_ny_end = prior_ny_bars[-1].timestamp
        current_ny_start = current_ny_bars[0].timestamp
        overnight_bars = [bar for bar in bars if prior_ny_end < bar.timestamp < current_ny_start]
        if not overnight_bars:
            raise PacketCompilerSourceError("Databento response did not contain 6E overnight bar coverage.")

        current_start = current_ny_bars[0].timestamp
        current_end = current_ny_bars[-1].timestamp
        observed_duration = current_end - current_start

        prior_20_ranges = [
            max(bar.high for bar in ny_by_date[session_date]) - min(bar.low for bar in ny_by_date[session_date])
            for session_date in prior_20_dates
        ]
        average_range = round(sum(prior_20_ranges) / len(prior_20_ranges), 4)

        prior_observed_volumes = []
        for session_date in prior_20_dates:
            session_bars = ny_by_date[session_date]
            session_start = session_bars[0].timestamp
            session_cutoff = session_start + observed_duration
            observed_volume = sum(bar.volume for bar in session_bars if bar.timestamp <= session_cutoff)
            if observed_volume <= 0:
                raise PacketCompilerSourceError(
                    "Databento response did not contain usable matched-window 6E volume coverage."
                )
            prior_observed_volumes.append(observed_volume)

        current_profile = _derive_profile_levels(
            _aggregate_profile_for_bounds(
                trades,
                start=current_start,
                end=current_end,
                coverage_label=f"6E NY trades for {self.request.current_session_date.isoformat()}",
            )
        )
        previous_start, previous_end = _utc_window_bounds(
            prior_session_date,
            session_start=SIX_E_NY_START_UTC,
            session_end=SIX_E_NY_END_UTC,
        )
        previous_profile = _derive_profile_levels(
            _aggregate_profile_for_bounds(
                trades,
                start=previous_start,
                end=previous_end,
                coverage_label=f"6E NY trades for {prior_session_date.isoformat()}",
            )
        )

        current_vwap_numerator = sum(
            (((bar.high + bar.low + bar.close) / 3.0) * bar.volume) for bar in current_ny_bars
        )
        current_volume = sum(bar.volume for bar in current_ny_bars)
        if current_volume <= 0:
            raise PacketCompilerSourceError("Databento response did not contain usable 6E current-session volume.")

        signed_delta = 0.0
        seen_symbols: set[str] = set()
        matched_trades = 0
        for record in _normalize_records(trades_response):
            record_symbol = _record_symbol(record)
            if record_symbol is not None:
                seen_symbols.add(record_symbol)
                if record_symbol != self.request.symbol:
                    continue
            timestamp = _record_timestamp(record)
            if not (current_start <= timestamp <= current_end):
                continue
            if "side" not in record:
                raise PacketCompilerSourceError(
                    "Databento 6E historical trade records must include side for cumulative delta."
                )
            side = str(record["side"]).strip().lower()
            size_field = "size" if "size" in record else "volume"
            volume = _record_float(record, size_field)
            if side in {"a", "ask", "sell"}:
                signed_delta -= volume
            elif side in {"b", "bid", "buy"}:
                signed_delta += volume
            else:
                raise PacketCompilerSourceError(
                    "Databento 6E historical trade side values must be bid/ask aligned."
                )
            matched_trades += 1
        if seen_symbols and self.request.symbol not in seen_symbols:
            raise PacketCompilerSourceError(
                f"Databento 6E historical response did not contain the requested symbol: {self.request.symbol}"
            )
        if matched_trades == 0:
            raise PacketCompilerSourceError(
                "Databento 6E historical response did not contain usable current-session trade coverage."
            )

        payload = {
            "contract": "6E",
            "timestamp": current_end,
            "current_price": current_ny_bars[-1].close,
            "session_open": current_ny_bars[0].open,
            "prior_day_high": max(bar.high for bar in prior_ny_bars),
            "prior_day_low": min(bar.low for bar in prior_ny_bars),
            "prior_day_close": prior_ny_bars[-1].close,
            "overnight_high": max(bar.high for bar in overnight_bars),
            "overnight_low": min(bar.low for bar in overnight_bars),
            "current_session_vah": current_profile["vah"],
            "current_session_val": current_profile["val"],
            "current_session_poc": current_profile["poc"],
            "previous_session_vah": previous_profile["vah"],
            "previous_session_val": previous_profile["val"],
            "previous_session_poc": previous_profile["poc"],
            "vwap": round(current_vwap_numerator / current_volume, 5),
            "session_range": round(
                max(bar.high for bar in current_ny_bars) - min(bar.low for bar in current_ny_bars),
                5,
            ),
            "avg_20d_session_range": average_range,
            "cumulative_delta": round(signed_delta, 4),
            "current_volume_vs_average": round(
                current_volume / (sum(prior_observed_volumes) / len(prior_observed_volumes)),
                4,
            ),
            "event_calendar_remainder": [],
            "asia_bars": [bar.model_dump(mode="json") for bar in current_asia_bars],
            "london_bars": [bar.model_dump(mode="json") for bar in current_london_bars],
            "ny_bars": [bar.model_dump(mode="json") for bar in current_ny_bars],
        }
        try:
            return SixEHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "Databento historical response could not be mapped into a valid 6E historical input."
            ) from exc


@dataclass(frozen=True)
class DatabentoMGCHistoricalMarketDataSource:
    request: MGCDatabentoHistoricalRequest
    api_key_env_var: str = DEFAULT_DATABENTO_API_KEY_ENV_VAR
    client_factory: Any | None = None

    def _build_client(self) -> Any:
        return _build_databento_client(
            api_key_env_var=self.api_key_env_var,
            client_factory=self.client_factory,
        )

    def _query_time_range(self) -> tuple[str, str]:
        lookback_start = datetime.combine(
            self.request.current_session_date - timedelta(days=DEFAULT_DATABENTO_LOOKBACK_CALENDAR_DAYS),
            time(0, 0),
            tzinfo=ET,
        ).astimezone(UTC)
        _, current_rth_end = _mgc_rth_bounds(self.request.current_session_date)
        query_end = current_rth_end + timedelta(minutes=1)
        return (
            lookback_start.isoformat().replace("+00:00", "Z"),
            query_end.isoformat().replace("+00:00", "Z"),
        )

    def load_mgc_input(self) -> MGCHistoricalDataInput:
        client = self._build_client()
        start, end = self._query_time_range()
        if self.request.bar_schema != "ohlcv-1m" or self.request.trades_schema != "trades":
            raise PacketCompilerSourceError(
                "Databento MGC historical sourcing only supports ohlcv-1m and trades."
            )

        bars_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.bar_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )
        trades_response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.trades_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start,
            end=end,
        )

        bars = _bars_from_records(_normalize_records(bars_response), symbol=self.request.symbol)
        trades = _trade_levels_from_records(_normalize_records(trades_response), symbol=self.request.symbol)

        rth_by_date = _group_mgc_rth_bars_by_date(bars)
        current_rth_bars = rth_by_date.get(self.request.current_session_date)
        if not current_rth_bars:
            raise PacketCompilerSourceError(
                f"Databento response did not contain current MGC RTH coverage for {self.request.current_session_date.isoformat()}."
            )

        prior_dates = sorted(
            session_date for session_date in rth_by_date if session_date < self.request.current_session_date
        )
        if len(prior_dates) < 20:
            raise PacketCompilerSourceError(
                "Databento response did not contain 20 completed prior MGC RTH sessions."
            )
        prior_20_dates = prior_dates[-20:]
        prior_session_date = prior_20_dates[-1]
        prior_rth_bars = rth_by_date[prior_session_date]

        prior_rth_end = prior_rth_bars[-1].timestamp
        current_rth_start = current_rth_bars[0].timestamp
        overnight_bars = [bar for bar in bars if prior_rth_end < bar.timestamp < current_rth_start]
        if not overnight_bars:
            raise PacketCompilerSourceError("Databento response did not contain MGC overnight bar coverage.")

        current_start = current_rth_bars[0].timestamp
        current_end = current_rth_bars[-1].timestamp
        observed_duration = current_end - current_start

        prior_20_ranges = [
            max(bar.high for bar in rth_by_date[session_date]) - min(bar.low for bar in rth_by_date[session_date])
            for session_date in prior_20_dates
        ]
        average_range = round(sum(prior_20_ranges) / len(prior_20_ranges), 4)

        prior_observed_volumes = []
        for session_date in prior_20_dates:
            session_bars = rth_by_date[session_date]
            session_start = session_bars[0].timestamp
            session_cutoff = session_start + observed_duration
            observed_volume = sum(bar.volume for bar in session_bars if bar.timestamp <= session_cutoff)
            if observed_volume <= 0:
                raise PacketCompilerSourceError(
                    "Databento response did not contain usable matched-window MGC volume coverage."
                )
            prior_observed_volumes.append(observed_volume)

        current_profile = _derive_profile_levels(
            _aggregate_mgc_profile(trades, session_date=self.request.current_session_date)
        )
        previous_profile = _derive_profile_levels(
            _aggregate_mgc_profile(trades, session_date=prior_session_date)
        )

        current_vwap_numerator = sum(
            (((bar.high + bar.low + bar.close) / 3.0) * bar.volume) for bar in current_rth_bars
        )
        current_volume = sum(bar.volume for bar in current_rth_bars)
        if current_volume <= 0:
            raise PacketCompilerSourceError("Databento response did not contain usable MGC current-session volume.")

        signed_delta = 0.0
        seen_symbols: set[str] = set()
        matched_trades = 0
        current_start_bound, current_end_bound = _mgc_rth_bounds(self.request.current_session_date)
        for record in _normalize_records(trades_response):
            record_symbol = _record_symbol(record)
            if record_symbol is not None:
                seen_symbols.add(record_symbol)
                if record_symbol != self.request.symbol:
                    continue
            timestamp = _record_timestamp(record)
            if not (current_start_bound <= timestamp <= current_end_bound):
                continue
            if "side" not in record:
                raise PacketCompilerSourceError(
                    "Databento MGC historical trade records must include side for cumulative delta."
                )
            side = str(record["side"]).strip().lower()
            size_field = "size" if "size" in record else "volume"
            volume = _record_float(record, size_field)
            if side in {"a", "ask", "sell"}:
                signed_delta -= volume
            elif side in {"b", "bid", "buy"}:
                signed_delta += volume
            else:
                raise PacketCompilerSourceError(
                    "Databento MGC historical trade side values must be bid/ask aligned."
                )
            matched_trades += 1
        if seen_symbols and self.request.symbol not in seen_symbols:
            raise PacketCompilerSourceError(
                f"Databento MGC historical response did not contain the requested symbol: {self.request.symbol}"
            )
        if matched_trades == 0:
            raise PacketCompilerSourceError(
                "Databento MGC historical response did not contain usable current-session trade coverage."
            )

        payload = {
            "contract": "MGC",
            "timestamp": current_end,
            "current_price": current_rth_bars[-1].close,
            "session_open": current_rth_bars[0].open,
            "prior_day_high": max(bar.high for bar in prior_rth_bars),
            "prior_day_low": min(bar.low for bar in prior_rth_bars),
            "prior_day_close": prior_rth_bars[-1].close,
            "overnight_high": max(bar.high for bar in overnight_bars),
            "overnight_low": min(bar.low for bar in overnight_bars),
            "current_session_vah": current_profile["vah"],
            "current_session_val": current_profile["val"],
            "current_session_poc": current_profile["poc"],
            "previous_session_vah": previous_profile["vah"],
            "previous_session_val": previous_profile["val"],
            "previous_session_poc": previous_profile["poc"],
            "vwap": round(current_vwap_numerator / current_volume, 4),
            "session_range": round(
                max(bar.high for bar in current_rth_bars) - min(bar.low for bar in current_rth_bars),
                4,
            ),
            "avg_20d_session_range": average_range,
            "cumulative_delta": round(signed_delta, 4),
            "current_volume_vs_average": round(
                current_volume / (sum(prior_observed_volumes) / len(prior_observed_volumes)),
                4,
            ),
            "event_calendar_remainder": [],
        }
        try:
            return MGCHistoricalDataInput.model_validate(payload)
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "Databento historical response could not be mapped into a valid MGC historical input."
            ) from exc


@dataclass(frozen=True)
class EIAEiaTimingSource:
    request: CLEiaTimingRequest
    api_key_env_var: str = DEFAULT_EIA_API_KEY_ENV_VAR
    fetch_json: Any | None = None

    def _build_url(self) -> str:
        api_key = os.getenv(self.api_key_env_var)
        if not api_key:
            raise PacketCompilerSourceError(
                f"{self.api_key_env_var} is required for EIA timing sourcing."
            )
        params: list[tuple[str, str]] = [
            ("api_key", api_key),
            ("frequency", "weekly"),
            ("data[0]", "value"),
            ("start", self.request.release_week_ending.isoformat()),
            ("end", self.request.release_week_ending.isoformat()),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "desc"),
            ("length", "2"),
            ("offset", "0"),
        ]
        for facet_name, facet_values in sorted(self.request.facets.items()):
            for facet_value in facet_values:
                params.append((f"facets[{facet_name}][]", facet_value))
        query = urllib.parse.urlencode(params, doseq=True)
        route = self.request.route.strip("/")
        return f"https://api.eia.gov/v2/{route}/data/?{query}"

    def load_cl_eia_timing(self) -> Any:
        url = self._build_url()
        payload = (self.fetch_json or _fetch_json_url)(url)
        if not isinstance(payload, Mapping):
            raise PacketCompilerSourceError("EIA response must decode to a JSON object.")
        response = payload.get("response")
        if not isinstance(response, Mapping):
            raise PacketCompilerSourceError("EIA response was missing response.")
        data = response.get("data")
        if not isinstance(data, list):
            raise PacketCompilerSourceError("EIA response was missing response.data list.")
        if len(data) > 1:
            raise PacketCompilerSourceError(
                "EIA response returned multiple rows for the requested release window."
            )

        released_available = False
        if len(data) == 1:
            row = data[0]
            if not isinstance(row, Mapping):
                raise PacketCompilerSourceError("EIA response rows must be JSON objects.")
            period = row.get("period")
            if period != self.request.release_week_ending.isoformat():
                raise PacketCompilerSourceError(
                    "EIA response period did not match the requested release_week_ending."
                )
            released_available = True

        current_ts = self.request.current_session_timestamp
        scheduled_ts = self.request.scheduled_release_time
        if current_ts < scheduled_ts:
            if released_available:
                raise PacketCompilerSourceError(
                    "EIA response implied a release before the scheduled_release_time."
                )
            minutes_until = int((scheduled_ts - current_ts).total_seconds() // 60)
            return {
                "status": "scheduled",
                "scheduled_time": scheduled_ts,
                "minutes_until": minutes_until,
            }

        if not released_available:
            raise PacketCompilerSourceError(
                "EIA response did not confirm release after the scheduled_release_time."
            )
        minutes_since = int((current_ts - scheduled_ts).total_seconds() // 60)
        return {
            "status": "released",
            "scheduled_time": scheduled_ts,
            "minutes_since": minutes_since,
        }


@dataclass(frozen=True)
class DatabentoCumulativeDeltaSource:
    request: ESDatabentoCumulativeDeltaRequest
    api_key_env_var: str = DEFAULT_DATABENTO_API_KEY_ENV_VAR
    client_factory: Any | None = None

    def load_es_cumulative_delta(self) -> ESCumulativeDeltaSourceInput:
        if self.request.trades_schema != "trades":
            raise PacketCompilerSourceError(
                "Databento ES cumulative-delta sourcing only supports trades_schema=trades."
            )
        client = _build_databento_client(
            api_key_env_var=self.api_key_env_var,
            client_factory=self.client_factory,
        )
        start, end = _rth_bounds(self.request.current_session_date)
        response = client.timeseries.get_range(
            dataset=self.request.dataset,
            schema=self.request.trades_schema,
            symbols=self.request.symbol,
            stype_in=self.request.stype_in,
            start=start.isoformat().replace("+00:00", "Z"),
            end=(end + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        )
        trades = _normalize_records(response)
        signed_delta = 0.0
        seen_symbols: set[str] = set()
        matched_trades = 0
        for record in trades:
            record_symbol = _record_symbol(record)
            if record_symbol is not None:
                seen_symbols.add(record_symbol)
                if record_symbol != self.request.symbol:
                    continue
            timestamp = _record_timestamp(record)
            if not (start <= timestamp <= end):
                continue
            if "side" not in record:
                raise PacketCompilerSourceError(
                    "Databento cumulative-delta response records must include side."
                )
            side = str(record["side"]).strip().lower()
            size_field = "size" if "size" in record else "volume"
            volume = _record_float(record, size_field)
            if side in {"a", "ask", "sell"}:
                signed_delta -= volume
            elif side in {"b", "bid", "buy"}:
                signed_delta += volume
            else:
                raise PacketCompilerSourceError(
                    "Databento cumulative-delta response side values must be bid/ask aligned."
                )
            matched_trades += 1
        if seen_symbols and self.request.symbol not in seen_symbols:
            raise PacketCompilerSourceError(
                f"Databento cumulative-delta response did not contain the requested symbol: {self.request.symbol}"
            )
        if matched_trades == 0:
            raise PacketCompilerSourceError(
                "Databento cumulative-delta response did not contain usable current-session trade coverage."
            )
        try:
            return ESCumulativeDeltaSourceInput.model_validate(
                {"contract": "ES", "cumulative_delta": round(signed_delta, 4)}
            )
        except ValidationError as exc:
            raise PacketCompilerSourceError(
                "Databento cumulative-delta response could not be mapped into a valid ES cumulative-delta input."
            ) from exc
