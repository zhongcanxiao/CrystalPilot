"""Code-hygiene ratchet: no new ``print(`` / ``# noqa`` / ``type: ignore``.

Companion to :mod:`test_technique_coupling`. ``mypy .`` is a CI step and now
reports zero errors; ``ruff check`` is the lint gate. These caps keep those
green gates from being quietly bypassed:

  - a ``type:`` ``ignore`` comment suppresses a mypy error instead of fixing it,
  - a ``# noqa`` suppresses a ruff finding instead of fixing it,
  - a new ``print(`` in the package (``src/``) is almost always a stray debug
    line — package code should log, not print.

Each count may only ratchet DOWN. When you legitimately delete suppressions or
prints, lower the matching cap in the same commit so the gain is locked in.
Never raise a cap to land new debt.

The patterns are assembled from fragments so this file does not match its own
checks, and the scan skips this file regardless.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SELF = Path(__file__).resolve()

# Built from fragments so the literal tokens never appear verbatim here.
PRINT_RE = re.compile(r"\b" + "print" + r"\s*\(")
TYPE_IGNORE_RE = re.compile("type:" + r"\s*" + "ignore")
NOQA_RE = re.compile("#" + r"\s*" + "noqa")

# Caps recorded after the mypy-to-zero pass (2026-06-03). Lower, never raise.
# 151, not 0: the remainder is the vendored EIC client modules (eic_client.py,
# auth.py), the two intentional print-gated trace helpers (tracing.py /
# temporal_analysis/_debug.py), and commented-out prints the regex still counts.
PRINT_CAP = 151  # scanned dirs: src/
TYPE_IGNORE_CAP = 14  # scanned dirs: src/ tests/ scripts/
# 34, not 31: the golden-path tests each carry one `import exphub.beamlines
# # noqa: F401` — the codebase's blessed registration-side-effect idiom, not a
# silenced finding. Still a hard ceiling for everything else.
NOQA_CAP = 34  # scanned dirs: src/ tests/ scripts/


def _count(pattern: re.Pattern[str], dirs: tuple[str, ...]) -> int:
    total = 0
    for d in dirs:
        base = REPO_ROOT / d
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if py.resolve() == _SELF:
                continue
            total += len(pattern.findall(py.read_text(encoding="utf-8", errors="ignore")))
    return total


def test_no_new_print_in_package() -> None:
    """Package code (src/) must not accumulate stray debug prints."""
    n = _count(PRINT_RE, ("src",))
    assert n <= PRINT_CAP, (
        f"print-call count in src/ = {n} exceeds cap {PRINT_CAP}. Prefer the "
        "logging module in package code. If you removed prints, lower PRINT_CAP."
    )


def test_no_new_type_ignore() -> None:
    """No new mypy suppressions — mypy is a CI gate at zero errors."""
    n = _count(TYPE_IGNORE_RE, ("src", "tests", "scripts"))
    assert n <= TYPE_IGNORE_CAP, (
        f"type-ignore count = {n} exceeds cap {TYPE_IGNORE_CAP}. Fix the type "
        "rather than suppress it. If you removed suppressions, lower TYPE_IGNORE_CAP."
    )


def test_no_new_noqa() -> None:
    """No new ruff suppressions — fix the finding instead."""
    n = _count(NOQA_RE, ("src", "tests", "scripts"))
    assert n <= NOQA_CAP, (
        f"noqa count = {n} exceeds cap {NOQA_CAP}. Fix the lint finding rather "
        "than suppress it. If you removed suppressions, lower NOQA_CAP."
    )
