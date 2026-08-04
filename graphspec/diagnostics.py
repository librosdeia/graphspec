"""Diagnostics: every finding graphspec reports, uniformly formatted.

The CLI, CI and the serve editor all print the same string for the same
problem: ``file:line: [RULE-ID] message`` plus a one-line hint.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    rule_id: str
    severity: str  # "error" | "warning"
    message: str
    hint: str = ""

    def format(self) -> str:
        head = f"{self.file}:{self.line}: [{self.rule_id}] {self.message}"
        if self.hint:
            return f"{head}\n  hint: {self.hint}"
        return head


def sort_diagnostics(diags: list[Diagnostic]) -> list[Diagnostic]:
    """Stable order for output and tests: by line, then rule ID, then message."""
    return sorted(diags, key=lambda d: (d.file, d.line, d.rule_id, d.message))
