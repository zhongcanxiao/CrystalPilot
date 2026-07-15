"""Single-crystal steering ViewModel.

Owns every single-crystal experiment-steering concern: experiment info,
angle plan + coverage, temporal/live-data analysis, instrument-status
figures, EIC submit/auth, the run table, and the angle-plan optimizer. The
technique-agnostic window chrome (tab navigation, beamline selector,
under-development dialog) lives in ``app/view_models/app_shell.py``.

Moved out of ``app/view_models/main.py`` and renamed ``MainViewModel`` →
``SingleCrystalSteeringViewModel`` during the multi-technique refactor (P2.16).
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import plotly.graph_objects as go
from nova.mvvm.interface import BindingInterface
from pydantic import BaseModel, Field

from ....core.beamline import active
from ..models.root import SingleCrystalMainModel

# Verbose tracing for ViewModel actions; off by default. Used to gate the
# (~100) print statements scattered across this module which previously
# spammed stdout on every UI interaction and per-second on the live-update
# loop. Set CRYSTALPILOT_DEBUG=1 to re-enable.
_DEBUG = bool(os.environ.get("CRYSTALPILOT_DEBUG"))


def _trace(*args: Any) -> None:
    if _DEBUG:
        print(*args)


@lru_cache(maxsize=1)
def _load_optimizer_fallback_angles() -> dict[str, list[list[float]]]:
    fixture = Path(__file__).parent.parent / "fixtures" / "optimizer_fallback_angles.json"
    return json.loads(fixture.read_text())


class SingleCrystalSteeringViewState(BaseModel):
    """View state for the single-crystal steering tabs."""

    is_live_update_running: bool = Field(default=False)
    # Chip+popover visibility flags for the temporal-analysis tab's HKL editors.
    hkl_individual_menu: bool = Field(default=False)
    hkl_peak_ratio_menu: bool = Field(default=False)


class SingleCrystalSteeringViewModel:
    """Viewmodel class, used to create data<->view binding and react on changes from GUI."""

    def __init__(
        self,
        model: SingleCrystalMainModel,
        binding: BindingInterface,
        notify_fn: Optional[Callable[[str], None]] = None,
    ):
        self.model = model
        self.view_state = SingleCrystalSteeringViewState()
        # Optional callback (app-shell ``notify``) for surfacing snackbar
        # messages in the technique-agnostic chrome — e.g. when a peak-selection
        # change pauses the live-update loop.
        self._notify = notify_fn
        # Guard to prevent recursive / re-entrant updates for temporalanalysis
        self._temporalanalysis_updating: bool = False
        # Debounce: avoid repeated updates in a short interval (seconds)
        self._temporalanalysis_last_update_time: float = 0.0
        self._temporalanalysis_min_interval: float = 1.0
        # Task reference for the live-update loop; None means not running
        self._live_update_task: asyncio.Task | None = None
        # Back-reference to the TemporalAnalysisView (set by the view on init)
        self._temporal_view: Any = None
        # Track the last-known peak-selection mode so we can detect user-driven
        # changes (the callback fires on any field on temporalanalysis).
        self._last_data_selection: str = self.model.temporalanalysis.data_selection
        # Set parent link for temporalanalysis model so it can access sibling models
        try:
            if hasattr(self.model, "temporalanalysis") and hasattr(self.model.temporalanalysis, "set_parent"):
                self.model.temporalanalysis.set_parent(self.model)
        except Exception as e:
            print("Warning: failed to set parent for temporalanalysis:", e)
        # self.angleplan = AnglePlanModel()

        # here we create a bind that connects ViewModel with View. It returns a communicator object,
        # that allows to update View from ViewModel (by calling update_view).
        # self.model will be updated automatically on changes of connected fields in View,
        # but one also can provide a callback function if they want to react to those events
        # and/or process errors.
        self.model_bind = binding.new_bind(self.model, callback_after_update=self.change_callback)
        # The steering view-state carries only single-crystal UI flags
        # (live-update running, HKL popover visibility); the TemporalAnalysis
        # view connects this bind to its own ``steering`` namespace. No
        # reactive logic is needed beyond the explicit apply_* / live-update
        # methods, so a plain logging callback suffices.
        self.view_state_bind = binding.new_bind(self.view_state, callback_after_update=self.change_callback)

        # self.experimentinfo_bind = binding.new_bind(self.model.experimentinfo, callback_after_update=self.change_callback)#noqa
        self.experimentinfo_bind = binding.new_bind(
            self.model.experimentinfo, callback_after_update=self.update_experimentinfo_options
        )
        self.angleplan_bind = binding.new_bind(
            self.model.angleplan, callback_after_update=self.update_angleplan_after_change
        )
        self.eiccontrol_bind = binding.new_bind(self.model.eiccontrol, callback_after_update=self.change_callback)
        # temporalanalysis_bind needs a *user-driven-change* callback to react
        # to dropdown / HKL edits (auto-stop on mode switch, buffer clear).
        # The callback only fires on view→model writes — model→view pushes
        # via ``update_in_view`` do not loop back through it.
        self.temporalanalysis_bind = binding.new_bind(
            self.model.temporalanalysis,
            callback_after_update=self.on_temporalanalysis_change,
        )

        self.dataanalysis_bind = binding.new_bind(self.model.dataanalysis, callback_after_update=self.change_callback)

        # self.cssstatus_bind = binding.new_bind(self.model.cssstatus, callback_after_update=self.change_callback)
        self.cssstatus_bind = binding.new_bind(self.model.cssstatus, callback_after_update=self.update_cssstatus_figure)
        self.temporalanalysis_updatefigure_uncertainty_bind = binding.new_bind()
        self.temporalanalysis_updatefigure_intensity_bind = binding.new_bind()
        ######################################################################################################################################################
        # wrong
        #        self.newtabtemplate_bind = binding.new_bind(self.model.newtabtemplate, callback_after_update=self.change_callback)#noqa
        #        self.newtabtemplate_updatefig_bind = binding.new_bind(self.model.newtabtemplate, callback_after_update=self.update_newtabtemplate_figure)#noqa
        ######################################################################################################################################################
        self.newtabtemplate_bind = binding.new_bind(
            self.model.newtabtemplate, callback_after_update=self.update_newtabtemplate_figure
        )
        self.newtabtemplate_updatefig_bind = binding.new_bind()
        ######################################################################################################################################################

        # self.pyvista_config = PyVistaConfig()

        # self.plotly_config_bind = binding.new_bind(
        #    linked_object=self.plotly_config, callback_after_update=self.update_plotly_figure
        # )
        # self.plotly_figure_bind = binding.new_bind(linked_object=self.plotly_config)
        # self.pyvista_config_bind = binding.new_bind(linked_object=self.pyvista_config)

        self.angleplan_updatefigure_coverage_bind = binding.new_bind()

        # Initialize temporalanalysis figures once at startup (no continuous callback)
        try:
            self.update_temporalanalysis_figure()
        except Exception:
            pass

    # def update_experimentinfo_options(self, _: Any = None) -> None:
    def update_experimentinfo_options(self, results: Dict[str, Any]) -> None:
        self.model.experimentinfo.update_option_lists()
        self.experimentinfo_bind.update_in_view(self.model.experimentinfo)
        _trace("update_experimentinfo_options")

        if results["error"]:
            print(f"error in fields {results['errored']}, model not changed")
        else:
            _trace("model fields updated:", results["updated"])
        # time.sleep(7)

    def change_callback(self, results: Dict[str, Any]) -> None:
        if results["error"]:
            print(f"error in fields {results['errored']}, model not changed")
        else:
            _trace("model fields updated:", results["updated"])

    def _handle_plot_definition_change(self, reason: str) -> None:
        """User changed something that invalidates the plotted time series.

        Clears the workflow's plot buffers, pauses the live loop if running,
        surfaces a snackbar prompt, and re-pushes the (now empty) figures
        so the view shows "Waiting for data" until the user restarts.
        """
        try:
            self.model.temporalanalysis.clear_plot_buffers()
        except Exception as e:
            print(f"clear_plot_buffers failed: {e}")
        if self.view_state.is_live_update_running:
            self.stop_live_update()
            if self._notify is not None:
                self._notify(f"{reason}. Live update paused — press Start to resume.")
        try:
            self.update_temporalanalysis_figure()
        except Exception:
            pass

    def on_temporalanalysis_change(self, results: Dict[str, Any]) -> None:
        """User-driven update on the temporal-analysis form (dropdown change).

        HKL edits inside the chip+popover do not flow through this path —
        the popover's Apply button calls :meth:`apply_individual_hkl` /
        :meth:`apply_peak_ratio_hkls` directly so we only invalidate
        buffers on user commit, not on every keystroke.
        """
        if results.get("error"):
            print(f"temporalanalysis error in {results.get('errored')}")
            return
        new_sel = self.model.temporalanalysis.data_selection
        if new_sel != self._last_data_selection:
            self._last_data_selection = new_sel
            self._handle_plot_definition_change(f"Peak selection changed to '{new_sel}'")

    def apply_individual_hkl(self) -> None:
        """User clicked Apply in the Individual-peak HKL popover."""
        ta = self.model.temporalanalysis
        self._handle_plot_definition_change(
            f"Individual peak HKL set to ({ta.individual_peak_h}, {ta.individual_peak_k}, {ta.individual_peak_l})"
        )
        self.view_state.hkl_individual_menu = False
        self.view_state_bind.update_in_view(self.view_state)

    def apply_peak_ratio_hkls(self) -> None:
        """User clicked Apply in the Peak-Ratio HKL popover."""
        ta = self.model.temporalanalysis
        self._handle_plot_definition_change(
            f"Peak ratio set to "
            f"({ta.peak_ratio_a_h}, {ta.peak_ratio_a_k}, {ta.peak_ratio_a_l}) / "
            f"({ta.peak_ratio_b_h}, {ta.peak_ratio_b_k}, {ta.peak_ratio_b_l})"
        )
        self.view_state.hkl_peak_ratio_menu = False
        self.view_state_bind.update_in_view(self.view_state)

    def update_angleplan_after_change(self, results: Dict[str, Any]) -> None:
        """Angleplan post-validators (goniometer_type → angle_list_headers) mutate fields.

        These are fields the user did not edit directly. Re-push the model so the
        view re-renders.
        """
        self.change_callback(results)
        self.angleplan_bind.update_in_view(self.model.angleplan)

    def upload_strategy(self) -> None:
        self.model.angleplan.load_ap(self.model.angleplan.plan_file)
        self._push_angleplan()

    # ------- targeted view-state pushes (cheap, one bind each) ------------
    def _push_angleplan(self) -> None:
        self.angleplan_bind.update_in_view(self.model.angleplan)

    def _push_eiccontrol(self) -> None:
        self.eiccontrol_bind.update_in_view(self.model.eiccontrol)

    def _push_temporal(self) -> None:
        self.temporalanalysis_bind.update_in_view(self.model.temporalanalysis)

    ######################################################################################################################################################
    # self.newtabtemplate_bind.update_in_view(self.model.newtabtemplate)
    ######################################################################################################################################################
    # print(self.model.angleplan.test_list)

    def submit_angle_plan(self) -> None:
        # print("submit_angle_plan")
        from ....core.beamline import active_technique

        # Resolve the active technique's EIC row builder (P3a.2 seam) so the
        # single-crystal CSV/row layout lives in the technique manifest and
        # core/eic stays technique-agnostic, only submitting pre-built jobs.
        row_builder = active_technique().eic_row_builder
        # The single-crystal manifest always provides a row builder (asserted by
        # test_manifest_exposes_row_builder_seam); narrow the Optional seam so
        # the submit path can call its methods without a None-guard.
        assert row_builder is not None

        ipts_number = self.model.experimentinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        goniometer_type = self.model.angleplan.goniometer_type
        angle_list = self.model.angleplan.angle_list
        try:
            try:
                row_builder.write_strategy_csv(angle_list, ipts_number, goniometer_type)
            except Exception as e:
                print(f"Warning: failed to copy strategy to EIC location: {e}")
            jobs = row_builder.build_jobs(angle_list, goniometer_type=goniometer_type)
            self.model.eiccontrol.submit_jobs(
                jobs,
                ipts_number,
                instrument_name,
            )
            if self.model.eiccontrol.is_simulation:
                self.model.eiccontrol.eic_status = "job submission simulated"
            else:
                self.model.eiccontrol.eic_status = "jobs submitted"
        except Exception as e:
            self.model.eiccontrol.eic_status = f"submission failed: {e}"
        self._push_eiccontrol()

    def call_load_token(self) -> None:
        try:
            self.model.eiccontrol.load_token(self.model.eiccontrol.token_file)
            self.model.eiccontrol.eic_status = "authenticated successfully"
        except Exception as e:
            self.model.eiccontrol.eic_status = f"authentication failed: {e}"
        self._push_eiccontrol()

    #
    #
    #    def update_pyvista_volume(self, plotter: Plotter) -> None:
    #        self.pyvista_config.render(plotter)
    #
    #    def update_plotly_figure(self, _: Any = None) -> None:
    #        self.plotly_config_bind.update_in_view(self.plotly_config)
    #        self.plotly_figure_bind.update_in_view(self.plotly_config.get_figure())
    #

    def update_cssstatus_figure(self, _: Any = None) -> None:
        # self.model.cssstatus.update_figure()
        self.cssstatus_bind.update_in_view(self.model.cssstatus)
        # time.sleep(7)

    def update_temporalanalysis_figure(self, _: Any = None) -> None:
        # Prevent re-entrant calls (can happen if view updates cause model callbacks)
        if self._temporalanalysis_updating:
            return
        # Debounce: skip if last update was very recent
        try:
            now = time.time()
            if now - self._temporalanalysis_last_update_time < self._temporalanalysis_min_interval:
                return
            self._temporalanalysis_last_update_time = now
        except Exception:
            # If time isn't available for some reason, continue without debounce
            pass
        self._temporalanalysis_updating = True
        try:
            # Push the new figures to the view
            self.temporalanalysis_updatefigure_intensity_bind.update_in_view(
                self.model.temporalanalysis.get_figure_intensity()
            )
            self.temporalanalysis_updatefigure_uncertainty_bind.update_in_view(
                self.model.temporalanalysis.get_figure_uncertainty()
            )
            # Update the model representation in view (avoid triggering view->model callbacks here)
            try:
                self.temporalanalysis_bind.update_in_view(self.model.temporalanalysis)
            except Exception:
                # Some binding implementations may attempt to invoke callbacks; swallow
                # exceptions here to avoid causing an update loop.
                pass
        finally:
            self._temporalanalysis_updating = False

    def _build_temporal_figures(self) -> tuple:
        """Build both figures in the caller's thread (intended for thread-pool use)."""
        return (
            self.model.temporalanalysis.get_figure_intensity(),
            self.model.temporalanalysis.get_figure_uncertainty(),
        )

    async def _update_figures_async(self, loop: asyncio.AbstractEventLoop) -> None:
        """Offload figure construction to thread pool, then push results to view on event loop."""
        if self._temporalanalysis_updating:
            return
        now = time.time()
        if now - self._temporalanalysis_last_update_time < self._temporalanalysis_min_interval:
            return
        self._temporalanalysis_last_update_time = now
        self._temporalanalysis_updating = True
        try:
            fig_i, fig_u = await loop.run_in_executor(None, self._build_temporal_figures)
            self.temporalanalysis_updatefigure_intensity_bind.update_in_view(fig_i)
            self.temporalanalysis_updatefigure_uncertainty_bind.update_in_view(fig_u)
            try:
                self.temporalanalysis_bind.update_in_view(self.model.temporalanalysis)
            except Exception:
                pass
        finally:
            self._temporalanalysis_updating = False

    def create_auto_update_temporalanalysis_figure(self) -> None:
        if self._live_update_task is not None and not self._live_update_task.done():
            print("Live update already running — ignoring duplicate start request.")
            return
        self._live_update_task = asyncio.create_task(self._start_and_run_live_update())

    async def _start_and_run_live_update(self) -> None:
        """Start live data collection in a thread, then run the reduction loop."""
        loop = asyncio.get_event_loop()
        # Show placeholder figures immediately while Mantid starts up
        if self._temporal_view is not None:
            self._temporal_view.show_placeholders()
        try:
            await loop.run_in_executor(None, self.model.temporalanalysis.start_reading_live_mtd_data)
        except RuntimeError as e:
            print(f"Failed to start live data: {e}")
            self._live_update_task = None
            return
        self.view_state.is_live_update_running = True
        self.view_state_bind.update_in_view(self.view_state)
        await self.get_live_mtd_data()

    def on_deactivate(self) -> None:
        """Quiesce the steering VM before an inside-technique beamline switch.

        Invoked by the app shell (via ``set_deactivate_hook``) just before the
        registry swaps to another single-crystal beamline. Best-effort: each
        step is guarded so a failure in one does not skip the rest, and the VM
        is left in a clean stopped state (no live-update task, empty plot
        buffers) for the next beamline.

        This is also the seam P3a-future will reuse for true cross-technique
        hot-rebuild (cancel async tasks + clear buffers + disconnect binds).
        """
        # 1. Cancel the live-update asyncio task + stop the Mantid live thread.
        try:
            self.stop_live_update()
        except Exception as e:
            print(f"on_deactivate: stop_live_update failed: {e}")
        # 2. Drop the buffered temporal time-series so stale data from the old
        #    beamline doesn't bleed into the next one's plots.
        try:
            self.model.temporalanalysis.clear_plot_buffers()
        except Exception as e:
            print(f"on_deactivate: clear_plot_buffers failed: {e}")
        # 3. Best-effort: reset the cached selection mode so the next
        #    user-driven change is detected correctly.
        try:
            self._last_data_selection = self.model.temporalanalysis.data_selection
        except Exception:
            pass

    def stop_live_update(self) -> None:
        """Cancel the asyncio task and stop the Mantid MonitorLiveData thread."""
        if self._live_update_task is not None and not self._live_update_task.done():
            self._live_update_task.cancel()
        self._live_update_task = None
        self.model.temporalanalysis.stop_live_data()
        self.view_state.is_live_update_running = False
        self.view_state_bind.update_in_view(self.view_state)

    async def get_live_mtd_data(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            print("============================================================================================")
            _trace("get_live_mtd_data")
            try:
                # The loop only runs after the workflow has been initialized.
                wf = self.model.temporalanalysis.mtd_workflow
                assert wf is not None
                # update_experiment_info only sets Python attrs — safe on event loop thread
                models = self.model.temporalanalysis.get_models()
                wf.update_experiment_info(models)
                # live_data_reduction runs the full Mantid pipeline; offload to thread pool
                # so the event loop (and GUI) stays responsive during the reduction.
                await loop.run_in_executor(None, wf.live_data_reduction)
                _trace("get_live_mtd_data done")
                print("============================================================================================")
                # Pull the latest UB out of the workflow so the side-table in the view refreshes.
                try:
                    self.model.temporalanalysis.sync_latest_ub_from_workflow()
                except Exception as e:
                    print(f"sync_latest_ub_from_workflow failed: {e}")
                await self._update_figures_async(loop)
                _trace("=== update temporal done ===")
                # Persist the latest figures + their data alongside the UB
                # .mat file. Cheap (HTML write + small CSV); offload anyway
                # so the event loop stays responsive on slow filesystems.
                try:
                    await loop.run_in_executor(None, self.model.temporalanalysis.save_latest_figure_snapshot)
                except Exception as e:
                    print(f"save_latest_figure_snapshot failed: {e}")
                if (
                    self.model.eiccontrol.eic_auto_stop_strategy == "By Uncertainty"
                    and len(wf.temporal_poisson_uncertainty) > 0
                ):
                    if wf.temporal_poisson_uncertainty[-1] < self.model.eiccontrol.eic_auto_stop_uncertainty_threshold:
                        print("stop_run")
                        self.stoprun()
                        wf.temporal_poisson_uncertainty = []
                        wf.timeseries_data_plt = []

                        continue
            except asyncio.CancelledError:
                print("Live update loop cancelled.")
                break
            except Exception as e:
                print(e)
            # self.update_temporalanalysis_figure()
            await asyncio.sleep(40)
        self.view_state.is_live_update_running = False
        self.view_state_bind.update_in_view(self.view_state)

    def update_newtabtemplate_figure(self, _: Any = None) -> None:
        self.newtabtemplate_bind.update_in_view(self.model.newtabtemplate)
        self.newtabtemplate_updatefig_bind.update_in_view(self.model.newtabtemplate.get_figure())

    def stoprun(self) -> None:
        ipts_number = self.model.experimentinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        self.model.eiccontrol.stop_run(ipts_number, instrument_name)
        self._push_eiccontrol()

    def poll_job_statuses(self) -> None:
        ipts_number = self.model.experimentinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        try:
            self.model.eiccontrol.poll_job_statuses(ipts_number, instrument_name)
        except Exception as e:
            print(f"Error polling job statuses: {e}")
        self._push_eiccontrol()

    def abort_job(self, scan_id: int) -> None:
        ipts_number = self.model.experimentinfo.ipts_number
        instrument_name = active().mantid_instrument_name
        self.model.eiccontrol.abort_job(scan_id, ipts_number, instrument_name)
        self._push_eiccontrol()

    ##########################################################################################################################
    #  edit angle plans
    ##########################################################################################################################
    # import trame
    # trame_server=trame.app.get_server()

    # @trame_server.controller.trigger('add_run')
    def add_run(self) -> None:
        _trace("add_run")
        self.model.angleplan.is_editing_run = False
        self.model.angleplan.run_record = self.model.angleplan.get_default_run_record()
        self.model.angleplan.runedit_dialog = True
        #### should be called after change object in python and want to sync with js object
        self._push_angleplan()

    # trigger needed for passing js variable to fucntion call in view
    # @trame_server.controller.trigger('edit_run')
    def edit_run(self, run_id: int) -> None:
        _trace("edit_run", run_id)
        self.model.angleplan.is_editing_run = True
        run = next((r for r in self.model.angleplan.angle_list if r["id"] == run_id), None)
        if run:
            self.model.angleplan.run_record = run.copy()
            self.model.angleplan.runedit_dialog = True
        self._push_angleplan()

    def close_runedit_dialog(self) -> None:
        _trace("close_runedit_dialog")
        self.model.angleplan.runedit_dialog = False
        self._push_angleplan()

    # @trame_server.controller.trigger('save_run')
    def save_run(self) -> None:
        _trace("save_run")
        print(self.model.angleplan.run_record["id"])
        if self.model.angleplan.is_editing_run:
            for i, run in enumerate(self.model.angleplan.angle_list):
                if run["id"] == self.model.angleplan.run_record["id"]:
                    self.model.angleplan.angle_list[i] = self.model.angleplan.run_record.copy()
                    break
        else:
            max_id = max((r["id"] for r in self.model.angleplan.angle_list), default=0)
            self.model.angleplan.run_record["id"] = max_id + 1
            self.model.angleplan.angle_list.append(self.model.angleplan.run_record.copy())
        self.model.angleplan.runedit_dialog = False
        self._push_angleplan()

    # @trame_server.controller.trigger('remove_run')
    def remove_run(self, run_id: int) -> None:
        _trace("remove_run", run_id)
        self.model.angleplan.angle_list = [r for r in self.model.angleplan.angle_list if r["id"] != run_id]
        self._push_angleplan()

    ############################### coverage figure update ###########################################################
    def update_coverage_figure(self, _: Any = None) -> None:
        # self.temporalanalysis_updatefig_bind.update_in_view(self.model.temporalanalysis.get_figure_intensity(),self.model.temporalanalysis.get_figure_uncertainty())#noqa
        self.angleplan_updatefigure_coverage_bind.update_in_view(self.model.angleplan.get_figure_coverage())
        self._push_angleplan()

    def update_coverage_figure_with_symmetry(self, _: Any = None) -> None:
        self.angleplan_updatefigure_coverage_bind.update_in_view(
            self.model.angleplan.get_coverage_figure_with_symmetry()
        )
        self._push_angleplan()

    def get_figure_coverage(self) -> go.Figure:
        _trace("get_figure_coverage")
        fig = self.model.angleplan.get_figure_coverage()
        self._push_angleplan()
        return fig

    def show_coverage(self) -> None:
        """Launch NeuXtalViz with the current angle plan.

        1. Export current angle_list to a temp CSV.
        2. Launch NXV via subprocess with --initialize-planner <UB> --open-plan <csv>.
        3. Spawn an async task that waits for NXV to exit, then reimports the CSV.
        """
        print("show_cov: exporting plan and launching NeuXtalViz")

        # Determine exchange CSV path (in the IPTS shared dir so NXV can also find it)
        plan_csv = os.path.join(tempfile.gettempdir(), "crystalpilot_nxv_plan.csv")

        # Export current strategy (may be empty — NXV will let user build from scratch)
        self.model.angleplan.export_to_nxv_csv(plan_csv)

        # UB matrix file from experiment info
        ub_file = getattr(self.model.experimentinfo, "UBFileName", "")

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
        print(f"show_cov: NXV launched (pid={self._nxv_proc.pid}), plan at {plan_csv}")

        # Schedule async reimport when NXV exits
        loop = asyncio.get_event_loop()
        loop.create_task(self._wait_for_nxv_and_reimport())

    async def _wait_for_nxv_and_reimport(self) -> None:
        """Wait for the NXV subprocess to exit, then reimport the edited CSV."""
        loop = asyncio.get_event_loop()
        # Wait in a thread so we don't block the event loop
        await loop.run_in_executor(None, self._nxv_proc.wait)
        print(f"show_cov: NXV exited (rc={self._nxv_proc.returncode})")

        plan_csv = self._nxv_plan_csv
        if os.path.isfile(plan_csv):
            self.model.angleplan.import_from_nxv_csv(plan_csv)
            self._push_angleplan()
            print(f"show_cov: reimported {len(self.model.angleplan.angle_list)} rows from {plan_csv}")
        else:
            print(f"show_cov: CSV not found at {plan_csv}, skipping reimport")

    def close_coverage(self) -> None:
        _trace("hide_cov")
        self.model.angleplan.is_showing_coverage = False
        self._push_angleplan()

    ############################### coverage figure update ###########################################################
    def reset_run(self) -> None:
        # if self.model.experimentinfo.c
        self.optimize_angleplan()
        _trace("reset_run")

        self._push_angleplan()
        _trace("reset_run after update view")

        pass

    def optimize_angleplan(self) -> None:
        from .angle_plan import angleplan_optimize

        _trace("optimize_angleplan")
        ##self.is_uninterruptable = True
        ##self.update_view()
        final_angle_list = angleplan_optimize(self)
        ##self.is_uninterruptable = False
        ##self.update_view()
        # print('optimize done. final_angle_list',final_angle_list)

        # Per-point-group fallback angle lists.
        # Source data lives in techniques/single_crystal/fixtures/optimizer_fallback_angles.json
        # so this hot path stays maintainable.
        pg = self.model.experimentinfo.point_group
        fallback = _load_optimizer_fallback_angles().get(pg)
        if fallback is not None:
            final_angle_list = [tuple(row) for row in fallback]

        print(
            "update angle_list",
        )
        self.model.angleplan.angle_list = []
        for i in range(len(final_angle_list)):
            r = {
                "id": i + 1,
                "title": "pg:" + self.model.experimentinfo.point_group + "_" + str(i + 1),
                "comment": "resetted",
                "phi": float(final_angle_list[i][0]),
                "chi": float(final_angle_list[i][1]),
                "omega": float(final_angle_list[i][2]),
                "wait_for": "PCharge",
                "value": 1,
            }
            self.model.angleplan.angle_list.append(r)

        print("vm optimize done for angle_list", self.model.angleplan.angle_list)
