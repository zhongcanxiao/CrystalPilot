"""SANS EIC row builder — flexible columns, one table-scan per Sample.

The SANS half of the EIC seam (the single-crystal half is
:mod:`exphub.techniques.single_crystal.agent.eic_row_builder`). The
framework-agnostic submit/poll/abort plumbing lives in
:mod:`exphub.core.eic.control`; the per-technique CSV column layout lives here.

SANS strategy tables are **column-flexible**: the columns are whatever the
uploaded CSV carried (discovered by
:class:`~exphub.techniques.sans.models.strategy.SansStrategyModel`), so the row
builder never hard-codes a header list — it reads the column order off the rows.
The only structural assumption is the **group column** (beamline-configurable
via ``SansConfig.group_key``; legacy default
:data:`~exphub.techniques.sans.models.strategy.GROUP_KEY` =
``BL1A:sampleholder``, USANS uses ``Title``): rows sharing a group value form
one Sample, submitted as **one EIC table-scan carrying all of that Sample's
steps**. That is why :meth:`build_jobs` emits one job per Sample with a ``rows``
(plural) payload — the framework-agnostic
:meth:`~exphub.core.eic.control.EICControlModel.submit_jobs` submits ``rows`` as
a multi-row table scan whose parameters are exactly
``{"run_mode": 0, "headers": <CSV columns>, "rows": <cell values>}``.
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ....core.paths import resolver_for as _resolver_for
from ..models.strategy import GROUP_KEY

logger = logging.getLogger(__name__)


def _headers_of(strategy_rows: List[Dict]) -> List[str]:
    """The raw CSV column order, taken off the first row (excludes ``id``)."""
    if not strategy_rows:
        return []
    return [k for k in strategy_rows[0].keys() if k != "id"]


def _cell(entry: Dict, key: str) -> object:
    v = entry.get(key)
    return "" if v is None else v


def _holder_sort_key(holder: str) -> Tuple[int, Any]:
    try:
        return (0, int(float(str(holder))))
    except (TypeError, ValueError):
        return (1, str(holder))


def _group_by_holder(strategy_rows: List[Dict], group_key: str) -> List[Tuple[str, List[Dict]]]:
    """Group rows by holder value, holder-sorted, order-stable within a group."""
    groups: Dict[str, List[Dict]] = {}
    for row in strategy_rows:
        holder = str(row.get(group_key, "")).strip()
        groups.setdefault(holder, []).append(row)
    return [(h, groups[h]) for h in sorted(groups, key=_holder_sort_key)]


class SansEICRowBuilder:
    """``EICRowBuilder`` for flexible-column SANS strategy tables.

    Stateless: one shared instance serves every SANS beamline. The CSV columns
    are whatever the uploaded strategy carried; rows are grouped into Samples by
    ``BL1A:sampleholder`` and each Sample becomes one multi-row table scan.
    """

    def write_strategy_csv(
        self,
        strategy_rows: List[Dict],
        ipts_number: str,
        *_args: Any,
        **_kwargs: Any,
    ) -> str:
        """Write the flexible-column SANS strategy CSV to the EIC dropbox.

        Columns and their order are taken from the strategy rows verbatim (the
        injected ``id`` is dropped). Returns the destination path.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"CrystalPilot-sans-plan-{timestamp}.csv"
        destination_dir = _resolver_for(ipts_number).eic_dropbox
        destination_path = os.path.join(destination_dir, filename)

        try:
            os.makedirs(destination_dir, exist_ok=True)
            logger.debug(f"Ensured directory exists: {destination_dir}")
        except OSError as e:
            logger.warning(f"Failed to create directory {destination_dir}: {e}")
            raise

        fieldnames = _headers_of(strategy_rows)
        with open(destination_path, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in strategy_rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        logger.debug(f"Copied SANS strategy to {destination_path}")
        return destination_path

    def build_rows(
        self,
        strategy_rows: List[Dict],
        ipts: str = "",
        spec: Any = None,
        **_kwargs: Any,
    ) -> Tuple[List[str], List[List[Any]]]:
        """Return ``(headers, rows)`` — the flat, ungrouped form.

        SANS tables are homogeneous (one shared column layout), so this returns
        the loaded column order and one flat value row per strategy step. Used by
        tests / the homogeneous convenience path; live submission uses the
        per-Sample grouping in :meth:`build_jobs`.
        """
        headers = _headers_of(strategy_rows)
        rows: List[List[Any]] = [[_cell(entry, k) for k in headers] for entry in strategy_rows]
        return headers, rows

    def build_jobs(
        self,
        strategy_rows: List[Dict],
        group_key: str = GROUP_KEY,
        **_kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Build one EIC submission payload **per Sample** (grouped by ``group_key``).

        Each job carries the flexible ``headers`` and a ``rows`` (plural) list —
        every step for that Sample — plus display metadata: ``title`` is
        ``"Sample <holder>"`` for holder-index grouping and the raw group value
        for Title-style grouping. SANS has no goniometer, so no ``phi`` /
        ``omega`` travel. The framework's ``submit_jobs`` submits ``rows`` as a
        single multi-row table scan.
        """
        headers = _headers_of(strategy_rows)
        jobs: List[Dict[str, Any]] = []
        for holder, group_rows in _group_by_holder(strategy_rows, group_key):
            rows = [[_cell(entry, k) for k in headers] for entry in group_rows]
            if holder == "":
                title = "Sample (unassigned)" if group_key == GROUP_KEY else "(untitled)"
            else:
                title = f"Sample {holder}" if group_key == GROUP_KEY else str(holder)
            jobs.append(
                {
                    "headers": headers,
                    "rows": rows,
                    "title": title,
                    "sampleholder": holder,
                }
            )
        return jobs


# Shared stateless instance wired onto the SANS manifest's ``eic_row_builder``
# field; the SANS submit path resolves it via
# ``active_technique().eic_row_builder``.
SANS_EIC_ROW_BUILDER = SansEICRowBuilder()
