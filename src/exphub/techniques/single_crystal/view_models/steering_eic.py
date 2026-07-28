"""EIC actions for the single-crystal steering ViewModel (facade collaborator).

Extracted verbatim from ``SingleCrystalSteeringViewModel``: the facade keeps
the public method names — they are pinned by the technique manifest's
``vm_method`` strings, the agent's action-verb allowlist, and the views' click
handlers — and forwards here. This collaborator reaches back through the
facade for the shared root model and the targeted ``_push_eiccontrol`` push.
"""

import logging
from typing import TYPE_CHECKING

from ....core.beamline import active
from ....core.eic.vm_actions import EicMonitorActions

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .steering import SingleCrystalSteeringViewModel


class EicActions:
    """EIC job submission, authentication, and stop/poll/abort plumbing."""

    def __init__(self, vm: "SingleCrystalSteeringViewModel") -> None:
        self._vm = vm
        # Shared authenticate/stop/poll/abort plumbing (identical across
        # techniques up to where the IPTS number lives) lives in core.
        self._monitor = EicMonitorActions(
            get_eiccontrol=lambda: vm.model.eiccontrol,
            get_ipts_number=lambda: vm.model.experimentinfo.ipts_number,
            push=vm._push_eiccontrol,
        )

    def submit_angle_plan(self) -> str:
        from ....core.beamline import active_technique

        # Resolve the active technique's EIC row builder (P3a.2 seam) so the
        # single-crystal CSV/row layout lives in the technique manifest and
        # core/eic stays technique-agnostic, only submitting pre-built jobs.
        row_builder = active_technique().eic_row_builder
        # The single-crystal manifest always provides a row builder (asserted by
        # test_manifest_exposes_row_builder_seam); narrow the Optional seam so
        # the submit path can call its methods without a None-guard.
        assert row_builder is not None

        ipts_number = self._vm.model.experimentinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        goniometer_type = self._vm.model.angleplan.goniometer_type
        angle_list = self._vm.model.angleplan.angle_list
        try:
            try:
                row_builder.write_strategy_csv(angle_list, ipts_number, goniometer_type)
            except Exception as e:
                logger.warning(f"Warning: failed to copy strategy to EIC location: {e}")
            jobs = row_builder.build_jobs(angle_list, goniometer_type=goniometer_type)
            self._vm.model.eiccontrol.submit_jobs(
                jobs,
                ipts_number,
                instrument_name,
            )
            if self._vm.model.eiccontrol.is_simulation:
                self._vm.model.eiccontrol.eic_status = "job submission simulated"
            else:
                self._vm.model.eiccontrol.eic_status = "jobs submitted"
        except Exception as e:
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
