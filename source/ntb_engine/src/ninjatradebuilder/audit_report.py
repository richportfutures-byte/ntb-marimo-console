from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NONE_LABEL = "(none)"


class AuditReportError(ValueError):
    pass


@dataclass(frozen=True)
class AuditSummary:
    total_runs: int
    success_count: int
    failure_count: int
    by_requested_contract: dict[str, int]
    by_termination_stage: dict[str, int]
    by_final_decision: dict[str, int]
    by_error_category: dict[str, int]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ninjatradebuilder.audit_report",
        description="Summarize NinjaTradeBuilder JSONL audit logs into concise aggregate counts.",
    )
    parser.add_argument(
        "--audit-log",
        required=True,
        help="Path to a JSONL audit log written by the operator CLI.",
    )
    return parser


def _normalize_counter(counter: Counter[str]) -> dict[str, int]:
    return {
        key: counter[key]
        for key in sorted(counter, key=lambda item: (-counter[item], item))
    }


def _label(value: Any) -> str:
    if value is None:
        return NONE_LABEL
    if isinstance(value, str) and value.strip():
        return value
    return NONE_LABEL


def load_audit_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise AuditReportError(f"Audit log does not exist: {path}")

    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AuditReportError(
                f"Audit log contains invalid JSON on line {line_number}: {path}"
            ) from exc
        if not isinstance(parsed, Mapping):
            raise AuditReportError(
                f"Audit log line {line_number} is not a JSON object: {path}"
            )
        records.append(dict(parsed))
    return records


def build_audit_summary(records: Iterable[Mapping[str, Any]]) -> AuditSummary:
    success_count = 0
    failure_count = 0
    by_requested_contract: Counter[str] = Counter()
    by_termination_stage: Counter[str] = Counter()
    by_final_decision: Counter[str] = Counter()
    by_error_category: Counter[str] = Counter()
    total_runs = 0

    for record in records:
        total_runs += 1
        if record.get("success") is True:
            success_count += 1
        else:
            failure_count += 1

        by_requested_contract[_label(record.get("requested_contract"))] += 1
        by_termination_stage[_label(record.get("termination_stage"))] += 1
        by_final_decision[_label(record.get("final_decision"))] += 1
        by_error_category[_label(record.get("error_category"))] += 1

    return AuditSummary(
        total_runs=total_runs,
        success_count=success_count,
        failure_count=failure_count,
        by_requested_contract=_normalize_counter(by_requested_contract),
        by_termination_stage=_normalize_counter(by_termination_stage),
        by_final_decision=_normalize_counter(by_final_decision),
        by_error_category=_normalize_counter(by_error_category),
    )


def _render_counter_section(title: str, values: Mapping[str, int]) -> list[str]:
    lines = [f"{title}:"]
    for key, count in values.items():
        lines.append(f"  {key}: {count}")
    return lines


def render_audit_summary(summary: AuditSummary) -> str:
    lines = [
        "NinjaTradeBuilder Audit Summary",
        f"Total runs: {summary.total_runs}",
        f"Success: {summary.success_count}",
        f"Failure: {summary.failure_count}",
        "",
    ]
    lines.extend(_render_counter_section("By requested_contract", summary.by_requested_contract))
    lines.append("")
    lines.extend(_render_counter_section("By termination_stage", summary.by_termination_stage))
    lines.append("")
    lines.extend(_render_counter_section("By final_decision", summary.by_final_decision))
    lines.append("")
    lines.extend(_render_counter_section("By error_category", summary.by_error_category))
    return "\n".join(lines)


def run_audit_report_cli(
    argv: list[str] | None = None,
    *,
    stdout: Any = None,
    stderr: Any = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        records = load_audit_records(Path(args.audit_log))
        summary = build_audit_summary(records)
        report = render_audit_summary(summary)
    except AuditReportError as exc:
        stderr.write(f"ERROR: {exc}\n")
        return 2

    stdout.write(report)
    stdout.write("\n")
    return 0


def main() -> int:
    return run_audit_report_cli()


if __name__ == "__main__":
    raise SystemExit(main())
