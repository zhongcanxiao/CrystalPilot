"""Angle-plan actions for the single-crystal steering ViewModel (facade collaborator).

Extracted verbatim from ``SingleCrystalSteeringViewModel``: the run-table
editing dialog, strategy upload, coverage figures, the NeuXtalViz round-trip,
and the angle-plan optimizer. The facade keeps the public method names — they
are pinned by the technique manifest's ``vm_method`` strings and the views'
click handlers — and forwards here. This collaborator reaches back through the
facade for the shared root model, the targeted ``_push_angleplan`` push, and
the coverage-figure bind.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import plotly.graph_objects as go

from ....core.tracing import _trace

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .steering import SingleCrystalSteeringViewModel


@lru_cache(maxsize=1)
def _load_optimizer_fallback_angles() -> dict[str, list[list[float]]]:
    fixture = Path(__file__).parent.parent / "fixtures" / "optimizer_fallback_angles.json"
    return json.loads(fixture.read_text())


class AnglePlanActions:
    """Run-table editing, coverage figures, NXV round-trip, and the optimizer."""

    def __init__(self, vm: "SingleCrystalSteeringViewModel") -> None:
        self._vm = vm

    def upload_strategy(self) -> None:
        self._vm.model.angleplan.load_ap(self._vm.model.angleplan.plan_file)
        self._vm._push_angleplan()

    # ------------------------------------------------------------------ run-table editing dialog

    def add_run(self) -> None:
        _trace("add_run")
        self._vm.model.angleplan.is_editing_run = False
        self._vm.model.angleplan.run_record = self._vm.model.angleplan.get_default_run_record()
        self._vm.model.angleplan.runedit_dialog = True
        #### should be called after change object in python and want to sync with js object
        self._vm._push_angleplan()

    def edit_run(self, run_id: int) -> None:
        _trace("edit_run", run_id)
        self._vm.model.angleplan.is_editing_run = True
        run = next((r for r in self._vm.model.angleplan.angle_list if r["id"] == run_id), None)
        if run:
            self._vm.model.angleplan.run_record = run.copy()
            self._vm.model.angleplan.runedit_dialog = True
        self._vm._push_angleplan()

    def close_runedit_dialog(self) -> None:
        _trace("close_runedit_dialog")
        self._vm.model.angleplan.runedit_dialog = False
        self._vm._push_angleplan()

    def save_run(self) -> None:
        _trace("save_run")
        angleplan = self._vm.model.angleplan
        if angleplan.is_editing_run:
            for i, run in enumerate(angleplan.angle_list):
                if run["id"] == angleplan.run_record["id"]:
                    angleplan.angle_list[i] = angleplan.run_record.copy()
                    break
        else:
            max_id = max((r["id"] for r in angleplan.angle_list), default=0)
            angleplan.run_record["id"] = max_id + 1
            angleplan.angle_list.append(angleplan.run_record.copy())
        angleplan.runedit_dialog = False
        self._vm._push_angleplan()

    def remove_run(self, run_id: int) -> None:
        _trace("remove_run", run_id)
        self._vm.model.angleplan.angle_list = [r for r in self._vm.model.angleplan.angle_list if r["id"] != run_id]
        self._vm._push_angleplan()

    # ------------------------------------------------------------------ coverage figures / NXV

    def update_coverage_figure(self, _: Any = None) -> None:
        self._vm.angleplan_updatefigure_coverage_bind.update_in_view(self._vm.model.angleplan.get_figure_coverage())
        self._vm._push_angleplan()

    def update_coverage_figure_with_symmetry(self, _: Any = None) -> None:
        self._vm.angleplan_updatefigure_coverage_bind.update_in_view(
            self._vm.model.angleplan.get_coverage_figure_with_symmetry()
        )
        self._vm._push_angleplan()

    def get_figure_coverage(self) -> go.Figure:
        _trace("get_figure_coverage")
        fig = self._vm.model.angleplan.get_figure_coverage()
        self._vm._push_angleplan()
        return fig

    def show_coverage(self) -> None:
        """Launch NeuXtalViz with the current angle plan.

        1. Export current angle_list to a temp CSV.
        2. Launch NXV via subprocess with --initialize-planner <UB> --open-plan <csv>.
        3. Spawn an async task that waits for NXV to exit, then reimports the CSV.
        """
        logger.debug("show_cov: exporting plan and launching NeuXtalViz")

        # Determine exchange CSV path (in the IPTS shared dir so NXV can also find it)
        plan_csv = os.path.join(tempfile.gettempdir(), "crystalpilot_nxv_plan.csv")

        # Export current strategy (may be empty — NXV will let user build from scratch)
        self._vm.model.angleplan.export_to_nxv_csv(plan_csv)

        # UB matrix file from experiment info
        ub_file = getattr(self._vm.model.experimentinfo, "UBFileName", "")

        # Build NXV launch command — NeuXtalViz-tools is a sibling repo
        _code_dir = os.path.dirname(os.path.abspath(__file__))
        # Walk up from view_models/ to CrystalPilot/, then go to sibling
        _project_root = os.path.normpath(os.path.join(_code_dir, "../../../.."))
        nxv_python = os.path.join(os.path.dirname(_project_root), "NeuXtalViz-tools", "src", "NeuXtalViz.py")
        nxv_conda_env = "nxv"
        nxv_activate = os.path.expanduser("~/.miniforge/bin/activate")

        cmd_parts = [
            f"source '{nxv_activate}'",
            f"conda activate {nxv_conda_env}",
            f"python '{nxv_python}'",
        ]
        if ub_file and os.path.isfile(ub_file):
            cmd_parts[-1] += f" --initialize-planner '{ub_file}'"
        cmd_parts[-1] += f" --open-plan '{plan_csv}'"

        shell_cmd = " && ".join(cmd_parts)

        # Launch NXV as a subprocess and wait for it asynchronously
        self._nxv_plan_csv = plan_csv
        self._nxv_proc = subprocess.Popen(shell_cmd, shell=True, executable="/bin/bash")
        logger.debug(f"show_cov: NXV launched (pid={self._nxv_proc.pid}), plan at {plan_csv}")

        # Schedule async reimport when NXV exits
        loop = asyncio.get_event_loop()
        loop.create_task(self._wait_for_nxv_and_reimport())

    async def _wait_for_nxv_and_reimport(self) -> None:
        """Wait for the NXV subprocess to exit, then reimport the edited CSV."""
        loop = asyncio.get_event_loop()
        # Wait in a thread so we don't block the event loop
        await loop.run_in_executor(None, self._nxv_proc.wait)
        logger.debug(f"show_cov: NXV exited (rc={self._nxv_proc.returncode})")

        plan_csv = self._nxv_plan_csv
        if os.path.isfile(plan_csv):
            self._vm.model.angleplan.import_from_nxv_csv(plan_csv)
            self._vm._push_angleplan()
            logger.debug(f"show_cov: reimported {len(self._vm.model.angleplan.angle_list)} rows from {plan_csv}")
        else:
            logger.warning(f"show_cov: CSV not found at {plan_csv}, skipping reimport")

    def close_coverage(self) -> None:
        _trace("hide_cov")
        self._vm.model.angleplan.is_showing_coverage = False
        self._vm._push_angleplan()

    # ------------------------------------------------------------------ optimizer

    def reset_run(self) -> None:
        self.optimize_angleplan()
        _trace("reset_run")
        self._vm._push_angleplan()
        _trace("reset_run after update view")

    def optimize_angleplan(self) -> None:
        from .angle_plan import angleplan_optimize

        _trace("optimize_angleplan")
        # angleplan_optimize takes the steering VM (it reads model.experimentinfo).
        final_angle_list = angleplan_optimize(self._vm)

        # Per-point-group fallback angle lists.
        # Source data lives in techniques/single_crystal/fixtures/optimizer_fallback_angles.json
        # so this hot path stays maintainable.
        pg = self._vm.model.experimentinfo.point_group
        fallback = _load_optimizer_fallback_angles().get(pg)
        if fallback is not None:
            final_angle_list = [tuple(row) for row in fallback]

        logger.debug(
            "update angle_list",
        )
        self._vm.model.angleplan.angle_list = []
        for i in range(len(final_angle_list)):
            r = {
                "id": i + 1,
                "title": "pg:" + self._vm.model.experimentinfo.point_group + "_" + str(i + 1),
                "comment": "resetted",
                "phi": float(final_angle_list[i][0]),
                "chi": float(final_angle_list[i][1]),
                "omega": float(final_angle_list[i][2]),
                "wait_for": "PCharge",
                "value": 1,
            }
            self._vm.model.angleplan.angle_list.append(r)

        logger.debug("%s %s", "vm optimize done for angle_list", self._vm.model.angleplan.angle_list)
