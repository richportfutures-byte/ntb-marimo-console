from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cl import compile_cl_packet
from .es import compile_es_packet, write_compiled_packet
from .mgc import compile_mgc_packet
from .nq import compile_nq_packet
from .sixe import compile_six_e_packet
from .zn import compile_zn_packet
from .sources import (
    DatabentoCumulativeDeltaSource,
    DatabentoCLHistoricalMarketDataSource,
    DatabentoHistoricalMarketDataSource,
    DatabentoMGCHistoricalMarketDataSource,
    DatabentoNQHistoricalMarketDataSource,
    DatabentoSixEHistoricalMarketDataSource,
    EIAEiaTimingSource,
    FREDCash10YYieldSource,
    JsonCLContractExtensionSource,
    JsonCLDatabentoHistoricalRequestSource,
    JsonCLEiaTimingRequestSource,
    JsonCLHistoricalMarketDataSource,
    JsonCLManualOverlaySource,
    JsonMGCContractExtensionSource,
    JsonMGCDatabentoHistoricalRequestSource,
    JsonMGCHistoricalMarketDataSource,
    JsonMGCManualOverlaySource,
    JsonNQContractExtensionSource,
    JsonNQDatabentoHistoricalRequestSource,
    JsonNQHistoricalMarketDataSource,
    JsonNQManualOverlaySource,
    JsonNQRelativeStrengthComparisonSource,
    JsonSixEContractExtensionSource,
    JsonSixEDatabentoHistoricalRequestSource,
    JsonSixEHistoricalMarketDataSource,
    JsonSixEManualOverlaySource,
    JsonZNContractExtensionSource,
    JsonZNFredCash10YYieldRequestSource,
    JsonZNHistoricalMarketDataSource,
    JsonZNManualOverlaySource,
    JsonBreadthSource,
    JsonCalendarSource,
    JsonCumulativeDeltaSource,
    JsonDatabentoCumulativeDeltaRequestSource,
    JsonDatabentoHistoricalRequestSource,
    JsonHistoricalMarketDataSource,
    JsonIndexCashToneSource,
    JsonManualOverlaySource,
    PacketCompilerSourceError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ninjatradebuilder.packet_compiler.cli",
        description="Compile one validated historical_packet_v1 JSON file for ES, CL, NQ, 6E, ZN, or MGC.",
    )
    parser.add_argument("--contract", choices=("ES", "CL", "NQ", "6E", "ZN", "MGC"), default="ES")
    parser.add_argument("--historical-source", choices=("json", "databento"), default="json")
    parser.add_argument("--historical-input", help="Path to contract historical source JSON.")
    parser.add_argument(
        "--databento-request",
        help="Path to contract Databento historical request JSON.",
    )
    parser.add_argument("--overlay", required=True, help="Path to contract manual overlay JSON.")
    parser.add_argument(
        "--relative-strength-input",
        help="Path to NQ relative_strength_vs_es comparison JSON.",
    )
    parser.add_argument(
        "--extension-input",
        help="Path to CL contract-specific extension JSON.",
    )
    parser.add_argument(
        "--eia-source",
        choices=("extension", "eia"),
        default="extension",
        help="Source for CL eia_timing.",
    )
    parser.add_argument(
        "--eia-request",
        help="Path to CL EIA timing request JSON.",
    )
    parser.add_argument(
        "--cash-10y-yield-source",
        choices=("extension", "fred"),
        default="extension",
        help="Source for ZN cash_10y_yield.",
    )
    parser.add_argument(
        "--fred-request",
        help="Path to ZN FRED cash_10y_yield request JSON.",
    )
    parser.add_argument(
        "--calendar-input",
        help="Path to ES event_calendar_remainder JSON.",
    )
    parser.add_argument(
        "--breadth-input",
        help="Path to ES breadth JSON.",
    )
    parser.add_argument(
        "--index-cash-tone-input",
        help="Path to ES index_cash_tone JSON.",
    )
    parser.add_argument(
        "--cumulative-delta-input",
        help="Path to ES cumulative_delta JSON.",
    )
    parser.add_argument(
        "--cumulative-delta-source",
        choices=("json", "databento"),
        default="json",
        help="Source for ES cumulative_delta input.",
    )
    parser.add_argument(
        "--databento-cumulative-delta-request",
        help="Path to ES Databento cumulative-delta request JSON.",
    )
    parser.add_argument("--output", required=True, help="Path to write packet.json.")
    parser.add_argument(
        "--provenance-output",
        help="Optional path to write packet provenance JSON. Defaults to packet.provenance.json.",
    )
    return parser


def run_cli(argv: list[str] | None = None, *, stdout: Any = None, stderr: Any = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.contract == "ES":
            if args.historical_source == "json":
                if not args.historical_input:
                    raise PacketCompilerSourceError(
                        "--historical-input is required when --historical-source=json."
                    )
                historical_input = JsonHistoricalMarketDataSource(Path(args.historical_input)).load_es_input()
            else:
                if not args.databento_request:
                    raise PacketCompilerSourceError(
                        "--databento-request is required when --historical-source=databento."
                    )
                request = JsonDatabentoHistoricalRequestSource(Path(args.databento_request)).load_es_request()
                historical_input = DatabentoHistoricalMarketDataSource(request=request).load_es_input()
            overlay = JsonManualOverlaySource(Path(args.overlay)).load_es_overlay()
            if not args.calendar_input:
                raise PacketCompilerSourceError("--calendar-input is required for --contract=ES.")
            calendar_input = JsonCalendarSource(Path(args.calendar_input)).load_es_calendar()
            if not args.breadth_input:
                raise PacketCompilerSourceError("--breadth-input is required for --contract=ES.")
            breadth_input = JsonBreadthSource(Path(args.breadth_input)).load_es_breadth()
            if not args.index_cash_tone_input:
                raise PacketCompilerSourceError(
                    "--index-cash-tone-input is required for --contract=ES."
                )
            index_cash_tone_input = JsonIndexCashToneSource(
                Path(args.index_cash_tone_input)
            ).load_es_index_cash_tone()
            if args.cumulative_delta_source == "json":
                if not args.cumulative_delta_input:
                    raise PacketCompilerSourceError(
                        "--cumulative-delta-input is required when --cumulative-delta-source=json."
                    )
                cumulative_delta_input = JsonCumulativeDeltaSource(
                    Path(args.cumulative_delta_input)
                ).load_es_cumulative_delta()
            else:
                if not args.databento_cumulative_delta_request:
                    raise PacketCompilerSourceError(
                        "--databento-cumulative-delta-request is required when "
                        "--cumulative-delta-source=databento."
                    )
                cumulative_delta_request = JsonDatabentoCumulativeDeltaRequestSource(
                    Path(args.databento_cumulative_delta_request)
                ).load_es_request()
                cumulative_delta_input = DatabentoCumulativeDeltaSource(
                    request=cumulative_delta_request
                ).load_es_cumulative_delta()
            artifact = compile_es_packet(
                historical_input,
                overlay,
                calendar_input,
                breadth_input,
                index_cash_tone_input,
                cumulative_delta_input,
            )
        elif args.contract == "CL":
            if args.historical_source == "json":
                if not args.historical_input:
                    raise PacketCompilerSourceError(
                        "--historical-input is required when --contract=CL and --historical-source=json."
                    )
                historical_input = JsonCLHistoricalMarketDataSource(Path(args.historical_input)).load_cl_input()
            else:
                if not args.databento_request:
                    raise PacketCompilerSourceError(
                        "--databento-request is required when --contract=CL and --historical-source=databento."
                    )
                request = JsonCLDatabentoHistoricalRequestSource(Path(args.databento_request)).load_cl_request()
                historical_input = DatabentoCLHistoricalMarketDataSource(request=request).load_cl_input()
            if not args.extension_input:
                raise PacketCompilerSourceError("--extension-input is required for --contract=CL.")
            overlay = JsonCLManualOverlaySource(Path(args.overlay)).load_cl_overlay()
            extension_input = JsonCLContractExtensionSource(Path(args.extension_input)).load_cl_extension()
            if args.eia_source == "eia":
                if not args.eia_request:
                    raise PacketCompilerSourceError(
                        "--eia-request is required when --contract=CL and --eia-source=eia."
                    )
                eia_request = JsonCLEiaTimingRequestSource(Path(args.eia_request)).load_cl_request()
                eia_timing = EIAEiaTimingSource(request=eia_request).load_cl_eia_timing()
                extension_payload = extension_input.model_dump(mode="json")
                extension_payload["eia_timing"] = eia_timing
                extension_input = extension_payload
            artifact = compile_cl_packet(
                historical_input,
                overlay,
                extension_input,
            )
        elif args.contract == "NQ":
            if args.historical_source == "json":
                if not args.historical_input:
                    raise PacketCompilerSourceError(
                        "--historical-input is required when --contract=NQ and --historical-source=json."
                    )
                historical_input = JsonNQHistoricalMarketDataSource(Path(args.historical_input)).load_nq_input()
            else:
                if not args.databento_request:
                    raise PacketCompilerSourceError(
                        "--databento-request is required when --contract=NQ and --historical-source=databento."
                    )
                request = JsonNQDatabentoHistoricalRequestSource(Path(args.databento_request)).load_nq_request()
                historical_input = DatabentoNQHistoricalMarketDataSource(request=request).load_nq_input()
            if not args.relative_strength_input:
                raise PacketCompilerSourceError(
                    "--relative-strength-input is required for --contract=NQ."
                )
            if not args.extension_input:
                raise PacketCompilerSourceError("--extension-input is required for --contract=NQ.")
            overlay = JsonNQManualOverlaySource(Path(args.overlay)).load_nq_overlay()
            relative_strength_input = JsonNQRelativeStrengthComparisonSource(
                Path(args.relative_strength_input)
            ).load_nq_relative_strength_input()
            extension_input = JsonNQContractExtensionSource(Path(args.extension_input)).load_nq_extension()
            artifact = compile_nq_packet(
                historical_input,
                overlay,
                relative_strength_input,
                extension_input,
            )
        elif args.contract == "6E":
            if args.historical_source == "json":
                if not args.historical_input:
                    raise PacketCompilerSourceError(
                        "--historical-input is required when --contract=6E and --historical-source=json."
                    )
                historical_input = JsonSixEHistoricalMarketDataSource(Path(args.historical_input)).load_six_e_input()
            else:
                if not args.databento_request:
                    raise PacketCompilerSourceError(
                        "--databento-request is required when --contract=6E and --historical-source=databento."
                    )
                request = JsonSixEDatabentoHistoricalRequestSource(
                    Path(args.databento_request)
                ).load_six_e_request()
                historical_input = DatabentoSixEHistoricalMarketDataSource(
                    request=request
                ).load_six_e_input()
            if not args.extension_input:
                raise PacketCompilerSourceError("--extension-input is required for --contract=6E.")
            overlay = JsonSixEManualOverlaySource(Path(args.overlay)).load_six_e_overlay()
            extension_input = JsonSixEContractExtensionSource(Path(args.extension_input)).load_six_e_extension()
            artifact = compile_six_e_packet(
                historical_input,
                overlay,
                extension_input,
            )
        elif args.contract == "ZN":
            if args.historical_source != "json":
                raise PacketCompilerSourceError(
                    "ZN compiler only supports --historical-source=json in this slice."
                )
            if not args.historical_input:
                raise PacketCompilerSourceError("--historical-input is required for --contract=ZN.")
            if not args.extension_input:
                raise PacketCompilerSourceError("--extension-input is required for --contract=ZN.")
            historical_input = JsonZNHistoricalMarketDataSource(Path(args.historical_input)).load_zn_input()
            overlay = JsonZNManualOverlaySource(Path(args.overlay)).load_zn_overlay()
            extension_input = JsonZNContractExtensionSource(Path(args.extension_input)).load_zn_extension()
            if args.cash_10y_yield_source == "fred":
                if not args.fred_request:
                    raise PacketCompilerSourceError(
                        "--fred-request is required when --contract=ZN and --cash-10y-yield-source=fred."
                    )
                fred_request = JsonZNFredCash10YYieldRequestSource(Path(args.fred_request)).load_zn_request()
                cash_10y_yield_input = FREDCash10YYieldSource(request=fred_request).load_zn_cash_10y_yield()
                extension_payload = extension_input.model_dump(mode="json")
                extension_payload["cash_10y_yield"] = cash_10y_yield_input.cash_10y_yield
                extension_input = extension_payload
            artifact = compile_zn_packet(
                historical_input,
                overlay,
                extension_input,
            )
        else:
            if args.historical_source == "json":
                if not args.historical_input:
                    raise PacketCompilerSourceError(
                        "--historical-input is required when --contract=MGC and --historical-source=json."
                    )
                historical_input = JsonMGCHistoricalMarketDataSource(Path(args.historical_input)).load_mgc_input()
            else:
                if not args.databento_request:
                    raise PacketCompilerSourceError(
                        "--databento-request is required when --contract=MGC and --historical-source=databento."
                    )
                request = JsonMGCDatabentoHistoricalRequestSource(
                    Path(args.databento_request)
                ).load_mgc_request()
                historical_input = DatabentoMGCHistoricalMarketDataSource(
                    request=request
                ).load_mgc_input()
            if not args.extension_input:
                raise PacketCompilerSourceError("--extension-input is required for --contract=MGC.")
            overlay = JsonMGCManualOverlaySource(Path(args.overlay)).load_mgc_overlay()
            extension_input = JsonMGCContractExtensionSource(Path(args.extension_input)).load_mgc_extension()
            artifact = compile_mgc_packet(
                historical_input,
                overlay,
                extension_input,
            )
        output_path, provenance_path = write_compiled_packet(
            artifact,
            output_path=Path(args.output),
            provenance_output_path=Path(args.provenance_output) if args.provenance_output else None,
        )
    except (PacketCompilerSourceError, ValueError) as exc:
        stderr.write(f"ERROR: {exc}\n")
        return 2

    stdout.write(
        json.dumps(
            {
                "contract": args.contract,
                "packet_path": str(output_path),
                "provenance_path": str(provenance_path),
                "packet_schema": artifact.packet.schema_name,
                "market_timestamp": artifact.packet.market_packet.timestamp.isoformat().replace(
                    "+00:00", "Z"
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    stdout.write("\n")
    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
