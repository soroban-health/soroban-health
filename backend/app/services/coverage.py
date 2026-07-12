"""Helpers for deriving test coverage from rust coverage tool output."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any


class CoverageTool(str, Enum):
    AUTO = "auto"
    TARP = "tarpaulin"
    LLVM = "llvm-cov"


_TARPAULIN_PERCENT_RE = re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)%\s+coverage\b")
_LLVM_TOTAL_RE = re.compile(r"(?im)^\s*TOTAL\s+\d+\s+\d+\s+([0-9]+(?:\.[0-9]+)?)%\s*$")


def _coerce_coverage(value: float) -> float | None:
    if 0 <= value <= 100:
        return round(float(value), 2)
    return None


def _parse_tarpaulin_output(output: str) -> float | None:
    matches = _TARPAULIN_PERCENT_RE.findall(output)
    if not matches:
        return None
    return _coerce_coverage(float(matches[-1]))


def _parse_llvm_cov_text_output(output: str) -> float | None:
    matches = _LLVM_TOTAL_RE.findall(output)
    if not matches:
        return None
    return _coerce_coverage(float(matches[-1]))


def _extract_lines_percent_from_json(node: Any) -> float | None:
    if isinstance(node, dict):
        lines = node.get("lines")
        if isinstance(lines, dict) and "percent" in lines:
            percent = lines["percent"]
            if isinstance(percent, (float, int)):
                coerced = _coerce_coverage(float(percent))
                if coerced is not None:
                    return coerced
        for child in node.values():
            hit = _extract_lines_percent_from_json(child)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for child in node:
            hit = _extract_lines_percent_from_json(child)
            if hit is not None:
                return hit
    return None


def _parse_llvm_cov_json_output(output: str) -> float | None:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    return _extract_lines_percent_from_json(payload)


def parse_coverage_pct(
    output: str, tool: CoverageTool = CoverageTool.AUTO
) -> float | None:
    """Parse test coverage percentage from tarpaulin/llvm-cov output text."""
    if tool == CoverageTool.TARP:
        return _parse_tarpaulin_output(output)

    if tool == CoverageTool.LLVM:
        return _parse_llvm_cov_json_output(output) or _parse_llvm_cov_text_output(
            output
        )

    # AUTO mode tries both tool formats in order of most structured to least.
    return (
        _parse_llvm_cov_json_output(output)
        or _parse_llvm_cov_text_output(output)
        or _parse_tarpaulin_output(output)
    )
