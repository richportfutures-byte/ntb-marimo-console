from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from .contracts import LIVE_OBSERVABLE_FIELD_PATHS, TriggerEvaluation, TriggerSpec


@dataclass(frozen=True)
class TriggerEvaluationBundle:
    evaluations: tuple[TriggerEvaluation, ...]

    @property
    def query_gate_true(self) -> bool:
        return any(item.is_valid and item.is_true for item in self.evaluations)


class TriggerEvaluator:
    """Deterministic evaluator for frozen TriggerSpec predicates.

    Dependency authority is explicit: evaluator reads only
    `TriggerSpec.required_live_field_paths` and never prose descriptions.
    """

    def evaluate(
        self,
        trigger_specs: list[TriggerSpec],
        live_snapshot: dict[str, Any],
    ) -> TriggerEvaluationBundle:
        evaluations = [self._evaluate_single(spec, live_snapshot) for spec in trigger_specs]
        return TriggerEvaluationBundle(evaluations=tuple(evaluations))

    def _evaluate_single(
        self,
        spec: TriggerSpec,
        live_snapshot: dict[str, Any],
    ) -> TriggerEvaluation:
        unknown_declared = tuple(
            path for path in spec.required_live_field_paths if path not in LIVE_OBSERVABLE_FIELD_PATHS
        )
        if unknown_declared:
            return TriggerEvaluation(
                trigger_id=spec.id,
                is_valid=False,
                is_true=False,
                missing_fields=(),
                invalid_reasons=("unknown_declared_live_field_path",),
            )

        if not spec.required_live_field_paths:
            return TriggerEvaluation(
                trigger_id=spec.id,
                is_valid=False,
                is_true=False,
                missing_fields=(),
                invalid_reasons=("empty_required_live_field_paths",),
            )

        missing_paths = tuple(
            path for path in spec.required_live_field_paths if self._resolve_path(live_snapshot, path) is _MISSING
        )
        if missing_paths:
            return TriggerEvaluation(
                trigger_id=spec.id,
                is_valid=False,
                is_true=False,
                missing_fields=missing_paths,
                invalid_reasons=("missing_required_live_field_paths",),
            )

        env: dict[str, Any] = {}
        token_map: dict[str, str] = {}
        for idx, path in enumerate(spec.required_live_field_paths):
            token = f"f_{idx}"
            token_map[path] = token
            env[token] = self._resolve_path(live_snapshot, path)

        try:
            expression = _normalize_predicate(spec.predicate)
            tokenized_expression = _tokenize_expression(expression, token_map)
            node = ast.parse(tokenized_expression, mode="eval")
            referenced = tuple(sorted(_collect_name_tokens(node)))
        except SyntaxError:
            return TriggerEvaluation(
                trigger_id=spec.id,
                is_valid=False,
                is_true=False,
                missing_fields=(),
                invalid_reasons=("invalid_predicate_syntax",),
            )

        undeclared = tuple(token for token in referenced if token not in set(token_map.values()))
        if undeclared:
            return TriggerEvaluation(
                trigger_id=spec.id,
                is_valid=False,
                is_true=False,
                missing_fields=(),
                invalid_reasons=("undeclared_field_path_in_predicate",),
            )

        try:
            result = bool(
                eval(
                    compile(node, "<trigger>", "eval"),
                    {"__builtins__": {}},
                    env,
                )
            )
        except Exception:
            return TriggerEvaluation(
                trigger_id=spec.id,
                is_valid=False,
                is_true=False,
                missing_fields=(),
                invalid_reasons=("predicate_evaluation_error",),
            )

        return TriggerEvaluation(
            trigger_id=spec.id,
            is_valid=True,
            is_true=result,
            missing_fields=(),
            invalid_reasons=(),
        )

    @staticmethod
    def _resolve_path(snapshot: dict[str, Any], path: str) -> Any:
        current: Any = snapshot
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
        return current


def _collect_name_tokens(node: ast.AST) -> set[str]:
    tokens: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Name(self, current: ast.Name) -> None:
            tokens.add(current.id)

    Visitor().visit(node)
    return tokens


def _normalize_predicate(predicate: str) -> str:
    normalized = predicate.replace(" AND ", " and ")
    normalized = normalized.replace(" OR ", " or ")
    normalized = normalized.replace(" NOT ", " not ")
    return normalized


def _tokenize_expression(expression: str, token_map: dict[str, str]) -> str:
    tokenized = expression
    for path in sorted(token_map.keys(), key=len, reverse=True):
        tokenized = tokenized.replace(path, token_map[path])
    return tokenized


_MISSING = object()
