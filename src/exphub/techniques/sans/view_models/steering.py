"""SANS steering ViewModel (P4.2).

The SANS analogue of
:class:`~exphub.techniques.single_crystal.view_models.steering.SingleCrystalSteeringViewModel`.
It orchestrates the three SANS sub-models (sample/IPTS info, strategy table,
I(Q) reduction placeholder) plus the shared EIC control model, and exposes the
trame ``*_bind`` surface the SANS tab views connect to.

Structural mirror of the single-crystal steering VM, reduced to the SANS shape:

  - tab 1 (IPTS info):   ``iptsinfo_bind``     — sample/experiment identity
  - tab 2 (live / I(Q)): ``iqreduction_bind``  + figure-push bind (placeholder)
  - tab 3 (strategy):    ``strategy_bind``     + ``eiccontrol_bind`` (CSV table,
                          row-edit dialog, EIC submit/auth/stop)

Deliberately absent (no single-crystal machinery): no goniometer angle plan,
no UB / coverage figures, no Mantid live-reduction loop, no temporal HKL
editors. SANS has no reciprocal lattice to cover and no real reduction
pipeline yet — the I(Q) tab renders a placeholder figure.

The manifest (``techniques/sans/manifest.py``) registers this VM via
``steering_vm_factory`` and the app shell builds it through
``app/mvvm_factory``. EIC submission is fully wired: the strategy table is
grouped by the beamline's configured group column (``Title`` on USANS) and
submits one multi-row table scan per Sample through the shared
:class:`~exphub.core.eic.control.EICControlModel`, behind the pre-submission
guidance gate.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from nova.mvvm.interface import BindingInterface
from pydantic import BaseModel, Field

from ....core.beamline import active
from ....core.tracing import _trace
from ..models.root import SansMainModel

logger = logging.getLogger(__name__)


class SansSteeringViewState(BaseModel):
    """View state for the SANS steering tabs.

    SANS has no live-reduction loop yet, so the only UI flag carried here is the
    placeholder ``is_live_update_running`` (mirrors the single-crystal field name
    so the LIVE-tab view can reuse the same ``steering`` namespace idiom). More
    SANS-specific flags can land here as the science is specified.
    """

    is_live_update_running: bool = Field(default=False)


class SansSteeringViewModel:
    """ViewModel that wires the SANS sub-models to the SANS tab views.

    Mirrors the single-crystal steering VM's construction: one ``new_bind`` per
    sub-model (each connected to its own trame namespace by the view), a
    view-state bind, and an empty figure-push bind for the I(Q) placeholder.
    """

    def __init__(
        self,
        model: SansMainModel,
        binding: BindingInterface,
        notify_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.model = model
        self.view_state = SansSteeringViewState()
        # Optional app-shell ``notify`` callback for surfacing snackbar messages
        # in the technique-agnostic chrome (same seam the single-crystal VM uses).
        self._notify = notify_fn

        # One bind per sub-model. The IPTS-info bind re-pushes its option lists
        # after an edit (instrument/sample-environment dropdowns); the rest use
        # the plain logging callback. Names mirror the single-crystal VM's
        # ``*_bind`` convention so the contract surface is predictable.
        self.model_bind = binding.new_bind(self.model, callback_after_update=self.change_callback)
        self.view_state_bind = binding.new_bind(self.view_state, callback_after_update=self.change_callback)

        self.iptsinfo_bind = binding.new_bind(self.model.iptsinfo, callback_after_update=self.change_callback)
        self.strategy_bind = binding.new_bind(self.model.strategy, callback_after_update=self.change_callback)
        self.iqreduction_bind = binding.new_bind(
            self.model.iqreduction, callback_after_update=self.update_iqreduction_figure
        )
        self.eiccontrol_bind = binding.new_bind(self.model.eiccontrol, callback_after_update=self.change_callback)

        # Empty figure-push bind for the I(Q) placeholder figure (the SANS
        # analogue of the single-crystal temporal/coverage figure binds).
        self.iqreduction_updatefig_bind = binding.new_bind()

        # Seed the strategy table from the active beamline's SansConfig: the
        # default upload path, the grouping column (USANS groups by "Title";
        # the model default is the legacy sample-holder PV), and the required
        # CSV column set the guidance check enforces. All blank-safe.
        config = getattr(active(), "technique_config", None)
        default_plan_file = getattr(config, "default_plan_file", "") or ""
        if default_plan_file and not self.model.strategy.plan_file:
            self.model.strategy.plan_file = default_plan_file
        group_key = getattr(config, "group_key", "") or ""
        if group_key:
            self.model.strategy.group_key = group_key
        required_columns = tuple(getattr(config, "required_columns", ()) or ())
        if required_columns:
            self.model.strategy.required_columns = list(required_columns)

    # ------------------------------------------------------------------ #
    # generic callbacks
    # ------------------------------------------------------------------ #
    def change_callback(self, results: Dict[str, Any]) -> None:
        if results["error"]:
            logger.warning(f"error in fields {results['errored']}, model not changed")
        else:
            _trace("model fields updated:", results["updated"])

    def update_iqreduction_figure(self, _: Any = None) -> None:
        """Re-push the I(Q) model + its (placeholder) figure to the view."""
        self.iqreduction_bind.update_in_view(self.model.iqreduction)
        self.iqreduction_updatefig_bind.update_in_view(self.model.iqreduction.get_figure())

    # ------------------------------------------------------------------ #
    # targeted view-state pushes (cheap, one bind each)
    # ------------------------------------------------------------------ #
    def _push_strategy(self) -> None:
        self.strategy_bind.update_in_view(self.model.strategy)

    def _push_eiccontrol(self) -> None:
        self.eiccontrol_bind.update_in_view(self.model.eiccontrol)

    def get_iq_figure(self) -> Any:
        """Initial I(Q) figure for the LIVE tab (the view seeds through the VM)."""
        return self.model.iqreduction.get_figure()

    # ------------------------------------------------------------------ #
    # strategy CSV load
    # ------------------------------------------------------------------ #
    def upload_strategy(self) -> None:
        """Load the SANS strategy CSV named in ``model.strategy.plan_file``.

        Runs the guidance check immediately after a successful load so a CSV in
        the wrong format (missing required columns, blank group values, bad
        cell types) is flagged at upload time, not first at submit time.
        """
        try:
            self.model.strategy.load_strategy(self.model.strategy.plan_file)
        except Exception as e:  # noqa: BLE001 — surface load errors to the user
            logger.warning(f"Failed to load SANS strategy CSV: {e}")
            if self._notify is not None:
                self._notify(f"Failed to load strategy CSV: {e}")
            self._push_strategy()
            return
        self.model.strategy.run_guidance()
        if self._notify is not None:
            n_err = len(self.model.strategy.guidance_errors)
            n_warn = len(self.model.strategy.guidance_warnings)
            if n_err:
                self._notify(f"Strategy CSV format problem: {n_err} error(s), {n_warn} warning(s) — see guidance.")
            elif n_warn:
                self._notify(f"Strategy CSV loaded with {n_warn} warning(s) — see guidance.")
        self._push_strategy()

    # ------------------------------------------------------------------ #
    # strategy row editing (inline; grouped by sample holder)
    # ------------------------------------------------------------------ #
    def add_sample(self) -> None:
        """Append a new Sample (next integer holder) with one empty step."""
        _trace("add_sample")
        self.model.strategy.add_sample()
        self._push_strategy()

    def add_step(self, holder: Any) -> None:
        """Append a new empty step to the Sample identified by ``holder``."""
        _trace("add_step", holder)
        self.model.strategy.add_step(holder)
        self._push_strategy()

    def remove_step(self, row_id: int) -> None:
        """Delete the strategy step with the given row id."""
        _trace("remove_step", row_id)
        self.model.strategy.remove_step(row_id)
        self._push_strategy()

    # ------------------------------------------------------------------ #
    # strategy export
    # ------------------------------------------------------------------ #
    def export_strategy(self) -> None:
        """Write the edited strategy table to ``model.strategy.export_file``."""
        path = self.model.strategy.export_file
        if not path:
            if self._notify is not None:
                self._notify("Set an export file path before exporting the strategy.")
            return
        try:
            self.model.strategy.export_to_csv(path)
            if self._notify is not None:
                self._notify(f"Strategy exported to {path}")
        except OSError as e:
            if self._notify is not None:
                self._notify(f"Failed to export strategy CSV: {e}")
        self._push_strategy()

    # ------------------------------------------------------------------ #
    # EIC submit / auth / stop (shared pipeline; SANS row-builder TBD)
    # ------------------------------------------------------------------ #
    def submit_strategy(self) -> None:
        """Submit the SANS strategy table through EIC.

        SANS submits through the same EIC pipeline as every other beamline
        (``MULTI_TECHNIQUE_PLAN.md`` decision #1): the guidance gate runs first
        (errors block, warnings allow), then the SANS row builder groups the
        table by the configured group column and each Sample goes out as one
        multi-row table scan in the beamline's column contract.
        """
        from ....core.beamline import active_technique

        ipts_number = self.model.iptsinfo.ipts_number
        instrument_name = active().mantid_instrument_name

        # Pre-submission guidance gate: errors block submission, warnings are
        # surfaced but allow it. Rules live on the strategy model (real
        # scientific rules TBD with the SANS scientist).
        ok = self.model.strategy.run_guidance()
        self._push_strategy()
        if not ok:
            n = len(self.model.strategy.guidance_errors)
            self.model.eiccontrol.eic_status = f"submission blocked: {n} issue(s) — see guidance above"
            self._push_eiccontrol()
            return
        if self.model.strategy.guidance_warnings and self._notify is not None:
            self._notify(f"Strategy has {len(self.model.strategy.guidance_warnings)} warning(s); submitting anyway.")

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
            self.model.eiccontrol.eic_status = "submission unavailable: no SANS row builder (technique wiring bug)"
            self._push_eiccontrol()
            return

        try:
            jobs = row_builder.build_jobs(
                self.model.strategy.strategy_list,
                group_key=self.model.strategy.group_key,
                columns=self.model.strategy.columns,
            )
            self.model.eiccontrol.submit_jobs(jobs, ipts_number, instrument_name)
            if self.model.eiccontrol.is_simulation:
                self.model.eiccontrol.eic_status = "job submission simulated"
            else:
                self.model.eiccontrol.eic_status = "jobs submitted"
        except Exception as e:  # noqa: BLE001
            self.model.eiccontrol.eic_status = f"submission failed: {e}"
        self._push_eiccontrol()

    def call_load_token(self) -> None:
        try:
            self.model.eiccontrol.load_token(self.model.eiccontrol.token_file)
            self.model.eiccontrol.eic_status = "authenticated successfully"
        except Exception as e:  # noqa: BLE001
            self.model.eiccontrol.eic_status = f"authentication failed: {e}"
        self._push_eiccontrol()

    def stoprun(self) -> None:
        ipts_number = self.model.iptsinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        self.model.eiccontrol.stop_run(ipts_number, instrument_name)
        self._push_eiccontrol()

    def poll_job_statuses(self) -> None:
        ipts_number = self.model.iptsinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        try:
            self.model.eiccontrol.poll_job_statuses(ipts_number, instrument_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error polling job statuses: {e}")
        self._push_eiccontrol()

    def abort_job(self, scan_id: int) -> None:
        ipts_number = self.model.iptsinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        self.model.eiccontrol.abort_job(scan_id, ipts_number, instrument_name)
        self._push_eiccontrol()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def on_deactivate(self) -> None:
        """Quiesce the SANS steering VM before an inside-technique switch.

        Mirrors the single-crystal ``on_deactivate`` seam (P3a-future reuse).
        SANS has no async live-reduction loop yet, so there is nothing to
        cancel; the hook exists so the app shell can call it uniformly across
        techniques. Kept best-effort for forward-compatibility.
        """
        self.view_state.is_live_update_running = False
