"""Shared EIC monitor/auth actions for technique steering view-models.

Every technique steering facade owns an EIC collaborator (single-crystal
``EicActions``, SANS ``SansEicActions``). The *submit* verb is technique-
specific — each technique has its own column contract — but authenticate /
stop / poll / abort are identical up to where the technique keeps its IPTS
number and how it pushes the EIC panel state. This helper owns that shared
subset, parameterized by those three seams, so the per-technique collaborators
shrink to their submit verb plus thin delegation.

Late-binding: the seams are callables (not captured instances) so the helper
always acts on the technique's *current* model, mirroring how the collaborators
reach through their facade on every call.
"""

import logging
from typing import Callable

from ..beamline import active
from .control import EICControlModel

logger = logging.getLogger(__name__)


class EicMonitorActions:
    """Authenticate / stop / poll / abort against the shared EIC control model."""

    def __init__(
        self,
        get_eiccontrol: Callable[[], EICControlModel],
        get_ipts_number: Callable[[], str],
        push: Callable[[], None],
    ) -> None:
        self._get_eiccontrol = get_eiccontrol
        self._get_ipts_number = get_ipts_number
        self._push = push

    def load_token(self) -> None:
        """Load the EIC token from the configured token file and report status."""
        ctrl = self._get_eiccontrol()
        try:
            ctrl.load_token(ctrl.token_file)
            ctrl.eic_status = "authenticated successfully"
        except Exception as e:
            ctrl.eic_status = f"authentication failed: {e}"
        self._push()

    def stop_run(self) -> None:
        """Abort the currently selected scan."""
        ctrl = self._get_eiccontrol()
        ctrl.stop_run(self._get_ipts_number(), active().mantid_instrument_name)
        self._push()

    def poll_job_statuses(self) -> None:
        """Refresh every submitted job's status from EIC (best-effort)."""
        ctrl = self._get_eiccontrol()
        try:
            ctrl.poll_job_statuses(self._get_ipts_number(), active().mantid_instrument_name)
        except Exception as e:
            logger.warning(f"Error polling job statuses: {e}")
        self._push()

    def abort_job(self, scan_id: int) -> None:
        """Abort a single submitted job by scan id."""
        ctrl = self._get_eiccontrol()
        ctrl.abort_job(scan_id, self._get_ipts_number(), active().mantid_instrument_name)
        self._push()
