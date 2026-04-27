from __future__ import annotations

from dataclasses import dataclass

from lr2rt.models import ConversionResult


STRICT_FAILURE_EXIT_CODE = 3


@dataclass(slots=True, frozen=True)
class StrictEvaluation:
    strict_enabled: bool
    warning_count: int
    failed: bool
    message: str | None = None


def evaluate_strict_mode(result: ConversionResult, strict: bool) -> StrictEvaluation:
    warning_count = len(result.warnings)
    if not strict:
        return StrictEvaluation(strict_enabled=False, warning_count=warning_count, failed=False, message=None)

    if warning_count == 0:
        return StrictEvaluation(strict_enabled=True, warning_count=0, failed=False, message=None)

    return StrictEvaluation(
        strict_enabled=True,
        warning_count=warning_count,
        failed=True,
        message=f"{warning_count} warning(s) detected. Strict mode requires zero warnings.",
    )
