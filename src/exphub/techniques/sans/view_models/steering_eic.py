"""EIC actions for the SANS steering ViewModel (facade collaborator).

Same facade split as the single-crystal steering VM (``EicActions`` /
``AnglePlanActions``): the facade keeps the public method names — pinned by the
SANS manifest's ``vm_method`` strings, the agent's action-verb allowlist, and
the strategy view's click handlers — and forwards here. The shared
authenticate / stop / poll / abort plumbing delegates to
:class:`~exphub.core.eic.vm_actions.EicMonitorActions`; only the SANS submit
verb (guidance gate + group-column-grouped table scans — sample-X position on
USANS, holder index on legacy CSVs) lives in this module.
"""

import logging
from typing import TYPE_CHECKING

from ....core.beamline import active, active_technique
from ....core.eic.vm_actions import EicMonitorActions

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .steering import SansSteeringViewModel


class SansEicActions:
    """SANS strategy submission plus shared EIC monitor/auth plumbing."""

    def __init__(self, vm: "SansSteeringViewModel") -> None:
        self._vm = vm
        self._monitor = EicMonitorActions(
            get_eiccontrol=lambda: vm.model.eiccontrol,
            get_ipts_number=lambda: vm.model.iptsinfo.ipts_number,
            push=vm._push_eiccontrol,
        )

    def submit_strategy(self) -> str:
        """Submit the SANS strategy table through EIC; returns the outcome status.

        The guidance gate runs first (errors block, warnings allow), then the
        SANS row builder groups the table by the configured group column and
        each Sample goes out as one multi-row table scan in the beamline's
        column contract. The returned status string is what the confirmation
        gate reports back to the user.
        """
        ipts_number = self._vm.model.iptsinfo.ipts_number
        instrument_name = active().mantid_instrument_name

        ok = self._vm.model.strategy.run_guidance()
        self._vm._push_strategy()
        if not ok:
            n = len(self._vm.model.strategy.guidance_errors)
            self._vm.model.eiccontrol.eic_status = f"submission blocked: {n} issue(s) — see guidance above"
            self._vm._push_eiccontrol()
            return self._vm.model.eiccontrol.eic_status
        if self._vm.model.strategy.guidance_warnings and self._vm._notify is not None:
            n_warn = len(self._vm.model.strategy.guidance_warnings)
            self._vm._notify(f"Strategy has {n_warn} warning(s); submitting anyway.")

        # Defensive: only honour the active technique's row builder when the
        # active technique is actually SANS (a mid-switch race would otherwise
        # submit through the single-crystal builder). The manifest always
        # supplies a builder, so a None here is a wiring bug, not a TBD.
        row_builder = None
        try:
            manifest = active_technique()
            if manifest.id == "sans":
                row_builder = manifest.eic_row_builder
        except Exception:  # noqa: BLE001 — registry unavailable mid-switch
            row_builder = None

        if row_builder is None:
            self._vm.model.eiccontrol.eic_status = "submission unavailable: no SANS row builder (technique wiring bug)"
            self._vm._push_eiccontrol()
            return self._vm.model.eiccontrol.eic_status

        try:
            jobs = row_builder.build_jobs(
                self._vm.model.strategy.strategy_list,
                group_key=self._vm.model.strategy.group_key,
                columns=self._vm.model.strategy.columns,
            )
            self._vm.model.eiccontrol.submit_jobs(jobs, ipts_number, instrument_name)
            if self._vm.model.eiccontrol.is_simulation:
                self._vm.model.eiccontrol.eic_status = "job submission simulated"
            else:
                self._vm.model.eiccontrol.eic_status = "jobs submitted"
        except Exception as e:  # noqa: BLE001
            self._vm.model.eiccontrol.eic_status = f"submission failed: {e}"
        self._vm._push_eiccontrol()
        return self._vm.model.eiccontrol.eic_status

    def call_load_token(self) -> None:
        self._monitor.load_token()

    def stoprun(self) -> None:
        self._monitor.stop_run()

    def poll_job_statuses(self) -> None:
        self._monitor.poll_job_statuses()

    def abort_job(self, scan_id: int) -> None:
        self._monitor.abort_job(scan_id)
