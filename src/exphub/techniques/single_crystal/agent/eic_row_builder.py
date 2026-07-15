"""Single-crystal EIC row builder.

Translates a single-crystal angle plan into the per-row EIC table-scan
submission payloads (``headers`` + ``row``) plus the display metadata the
EIC Control panel shows for each submitted job.

This is the single-crystal half of the EIC seam introduced in P3a: the
framework-agnostic submit/poll/abort plumbing lives in
``exphub.core.eic.control``; the single-crystal CSV column layout
(goniometer angle columns, ramp PV columns, run-title PV) lives here.

P3a.2 formalizes the seam as an :class:`~exphub.core.eic.row_builder.EICRowBuilder`
declared on the :class:`~exphub.core.beamline.technique.TechniqueManifest`
(:data:`SINGLE_CRYSTAL_EIC_ROW_BUILDER`). The submit path resolves
``active_technique().eic_row_builder`` and calls :meth:`build_jobs`; the CSV/row
shape is identical to the pre-refactor ``EICControlModel`` so single-crystal
submission behavior is unchanged for every single-crystal beamline. The legacy
module-level functions remain as thin delegators for existing callers.
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ....core.beamline import active as _active_beamline
from ....core.paths import resolver_for as _resolver_for
from ..models import gonio_pvs

logger = logging.getLogger(__name__)


class SingleCrystalEICRowBuilder:
    """``EICRowBuilder`` for single-crystal goniometer angle plans.

    Stateless: every method reads the active beamline's goniometer/ramp PVs at
    call time (via the ``gonio_pvs`` shim), so one shared instance serves every
    single-crystal beamline. Wired onto the manifest as
    :data:`SINGLE_CRYSTAL_EIC_ROW_BUILDER`.
    """

    def write_strategy_csv(
        self,
        angleplan: List[Dict],
        ipts_number: str,
        goniometer_type: str = gonio_pvs.AMBIENT,
    ) -> str:
        """Write the experiment-strategy CSV to the EIC dropbox location.

        Column layout depends on ``goniometer_type``; ramp rows fill the ramp
        PV columns and leave Wait For/Value blank. Returns the destination path.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"CrystalPilot-experiment-plan-{timestamp}.csv"
        destination_dir = _resolver_for(ipts_number).eic_dropbox
        destination_path = os.path.join(destination_dir, filename)

        try:
            os.makedirs(destination_dir, exist_ok=True)
            logger.debug(f"Ensured directory exists: {destination_dir}")
        except OSError as e:
            logger.warning(f"Failed to create directory {destination_dir}: {e}")
            raise

        run_title_pv = _active_beamline().single_crystal.run_title_pv
        angle_cols = gonio_pvs.angle_columns(goniometer_type)
        ramp_cols = list(gonio_pvs.RAMP_PVS.values())
        fieldnames = [
            run_title_pv,
            *angle_cols,
            *ramp_cols,
            "Comment",
            "Wait For",
            "Value",
        ]
        pvs = gonio_pvs.ANGLE_PVS[goniometer_type]
        with open(destination_path, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for angle in angleplan:
                row: Dict = {
                    run_title_pv: angle.get("title", "CrystalPilot"),
                    "Comment": angle.get("comment", ""),
                    pvs["omega"]: angle.get("omega", 0),
                }
                if "phi" in pvs:
                    row[pvs["phi"]] = angle.get("phi", 0)

                if angle.get("step_type") == "ramp":
                    row[gonio_pvs.RAMP_PVS["start"]] = angle.get("ramp_start", "")
                    row[gonio_pvs.RAMP_PVS["end"]] = angle.get("ramp_end", "")
                    row[gonio_pvs.RAMP_PVS["rate"]] = angle.get("ramp_rate", "")
                    row[gonio_pvs.RAMP_PVS["soak"]] = angle.get("ramp_soak", "")
                    row[gonio_pvs.RAMP_PVS["run"]] = angle.get("ramp_run", "")
                    row["Wait For"] = ""
                    row["Value"] = ""
                else:
                    wait_for = angle.get("wait_for", "PCharge")
                    row["Wait For"] = gonio_pvs.WAIT_FOR_PCHARGE_PV if wait_for == "PCharge" else wait_for
                    row["Value"] = angle.get("value", 10)
                writer.writerow(row)
        logger.debug(f"Copied experiment strategy to {destination_path}")
        return destination_path

    def build_jobs(
        self,
        strategy_rows: List[Dict],
        goniometer_type: str = gonio_pvs.AMBIENT,
        **_kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Build the per-row EIC submission payloads for a single-crystal plan.

        Returns one job dict per angle-plan entry. Each dict carries the EIC
        table-scan ``headers`` + ``row`` to submit plus the display metadata the
        EIC Control panel renders (``title``/``phi``/``omega``). Angle and ramp
        rows can carry different column layouts, so headers travel per-row.
        """
        pvs = gonio_pvs.ANGLE_PVS[goniometer_type]

        angle_headers = ["Title", "Comment", pvs["omega"]]
        angle_keys: List[str] = ["title", "comment", "omega"]
        if "phi" in pvs:
            angle_headers.append(pvs["phi"])
            angle_keys.append("phi")
        angle_headers.extend(["Wait For", "Value"])
        angle_keys.extend(["wait_for", "value"])

        ramp_headers = ["Title", "Comment", *gonio_pvs.RAMP_PVS.values()]
        ramp_keys = ["title", "comment", "ramp_start", "ramp_end", "ramp_rate", "ramp_soak", "ramp_run"]

        jobs: List[Dict[str, Any]] = []
        for angle in strategy_rows:
            if angle.get("step_type") == "ramp":
                headers = ramp_headers
                keys = ramp_keys
            else:
                headers = angle_headers
                keys = angle_keys

            def _cell(k: str, entry: Dict = angle) -> object:
                v = entry.get(k)
                if k == "wait_for" and v == "PCharge":
                    return gonio_pvs.WAIT_FOR_PCHARGE_PV
                return "" if v is None else v

            row = [_cell(k) for k in keys]
            jobs.append(
                {
                    "headers": headers,
                    "row": row,
                    "title": angle.get("title", ""),
                    "phi": angle.get("phi", 0.0) or 0.0,
                    "omega": angle.get("omega", 0.0) or 0.0,
                }
            )
        return jobs

    def build_rows(
        self,
        strategy_rows: List[Dict],
        ipts: str = "",
        spec: Any = None,
        goniometer_type: str = gonio_pvs.AMBIENT,
        **_kwargs: Any,
    ) -> Tuple[List[str], List[List[Any]]]:
        """Flat ``(headers, rows)`` form for a homogeneous (single-shape) plan.

        Convenience wrapper named in the plan. Single-crystal plans may mix
        angle and ramp row shapes; this form is only well-defined when they do
        not, so it asserts a single shared header layout and is intended for
        tests / homogeneous callers. The live submit path uses
        :meth:`build_jobs` (per-row headers) directly.
        """
        jobs = self.build_jobs(strategy_rows, goniometer_type=goniometer_type)
        if not jobs:
            return [], []
        headers = jobs[0]["headers"]
        if any(job["headers"] != headers for job in jobs):
            raise ValueError(
                "build_rows requires a homogeneous plan (all rows share one "
                "header layout); this plan mixes angle and ramp rows. Use "
                "build_jobs for per-row headers."
            )
        return headers, [job["row"] for job in jobs]


# Shared stateless instance wired onto the single-crystal manifest's
# ``eic_row_builder`` field; the submit path resolves it via
# ``active_technique().eic_row_builder``.
SINGLE_CRYSTAL_EIC_ROW_BUILDER = SingleCrystalEICRowBuilder()


# --- legacy module-level delegators (existing callers / back-compat) --------
def write_strategy_csv(
    angleplan: List[Dict],
    ipts_number: str,
    goniometer_type: str = gonio_pvs.AMBIENT,
) -> str:
    """Module-level delegator to :meth:`SingleCrystalEICRowBuilder.write_strategy_csv`."""
    return SINGLE_CRYSTAL_EIC_ROW_BUILDER.write_strategy_csv(angleplan, ipts_number, goniometer_type)


def build_jobs(
    angleplan: List[Dict],
    goniometer_type: str = gonio_pvs.AMBIENT,
) -> List[Dict[str, Any]]:
    """Module-level delegator to :meth:`SingleCrystalEICRowBuilder.build_jobs`."""
    return SINGLE_CRYSTAL_EIC_ROW_BUILDER.build_jobs(angleplan, goniometer_type=goniometer_type)
