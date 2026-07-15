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
import logging
import time
from typing import Any, Callable, Dict, Optional

import plotly.graph_objects as go
from nova.mvvm.interface import BindingInterface
from pydantic import BaseModel, Field

from ..models.root import SingleCrystalMainModel
from .steering_angle_plan import AnglePlanActions
from .steering_eic import EicActions
from .tracing import _trace

logger = logging.getLogger(__name__)


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
            logger.warning("%s %s", "Warning: failed to set parent for temporalanalysis:", e)
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

        # Domain collaborators (facade pattern): the public method names stay on
        # this class — manifests, the agent verb allowlist, and views reference
        # them by name — and forward to these delegates.
        self._eic = EicActions(self)
        self._angle_plan = AnglePlanActions(self)

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
            logger.warning(f"error in fields {results['errored']}, model not changed")
        else:
            _trace("model fields updated:", results["updated"])
        # time.sleep(7)

    def change_callback(self, results: Dict[str, Any]) -> None:
        if results["error"]:
            logger.warning(f"error in fields {results['errored']}, model not changed")
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
            logger.warning(f"clear_plot_buffers failed: {e}")
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
            logger.warning(f"temporalanalysis error in {results.get('errored')}")
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
        self._angle_plan.upload_strategy()

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
        self._eic.submit_angle_plan()

    def call_load_token(self) -> None:
        self._eic.call_load_token()

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
            logger.debug("Live update already running — ignoring duplicate start request.")
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
            logger.warning(f"Failed to start live data: {e}")
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
            logger.warning(f"on_deactivate: stop_live_update failed: {e}")
        # 2. Drop the buffered temporal time-series so stale data from the old
        #    beamline doesn't bleed into the next one's plots.
        try:
            self.model.temporalanalysis.clear_plot_buffers()
        except Exception as e:
            logger.warning(f"on_deactivate: clear_plot_buffers failed: {e}")
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
            logger.debug("============================================================================================")
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
                logger.debug(
                    "============================================================================================"
                )
                # Pull the latest UB out of the workflow so the side-table in the view refreshes.
                try:
                    self.model.temporalanalysis.sync_latest_ub_from_workflow()
                except Exception as e:
                    logger.warning(f"sync_latest_ub_from_workflow failed: {e}")
                await self._update_figures_async(loop)
                _trace("=== update temporal done ===")
                # Persist the latest figures + their data alongside the UB
                # .mat file. Cheap (HTML write + small CSV); offload anyway
                # so the event loop stays responsive on slow filesystems.
                try:
                    await loop.run_in_executor(None, self.model.temporalanalysis.save_latest_figure_snapshot)
                except Exception as e:
                    logger.warning(f"save_latest_figure_snapshot failed: {e}")
                if (
                    self.model.eiccontrol.eic_auto_stop_strategy == "By Uncertainty"
                    and len(wf.temporal_poisson_uncertainty) > 0
                ):
                    if wf.temporal_poisson_uncertainty[-1] < self.model.eiccontrol.eic_auto_stop_uncertainty_threshold:
                        logger.debug("stop_run")
                        self.stoprun()
                        wf.temporal_poisson_uncertainty = []
                        wf.timeseries_data_plt = []

                        continue
            except asyncio.CancelledError:
                logger.debug("Live update loop cancelled.")
                break
            except Exception as e:
                logger.debug(e)
            # self.update_temporalanalysis_figure()
            await asyncio.sleep(40)
        self.view_state.is_live_update_running = False
        self.view_state_bind.update_in_view(self.view_state)

    def update_newtabtemplate_figure(self, _: Any = None) -> None:
        self.newtabtemplate_bind.update_in_view(self.model.newtabtemplate)
        self.newtabtemplate_updatefig_bind.update_in_view(self.model.newtabtemplate.get_figure())

    def stoprun(self) -> None:
        self._eic.stoprun()

    def poll_job_statuses(self) -> None:
        self._eic.poll_job_statuses()

    def abort_job(self, scan_id: int) -> None:
        self._eic.abort_job(scan_id)

    ##########################################################################################################################
    #  edit angle plans
    ##########################################################################################################################
    # import trame
    # trame_server=trame.app.get_server()

    # (trigger wiring lives in the view; bodies live in AnglePlanActions)
    def add_run(self) -> None:
        self._angle_plan.add_run()

    def edit_run(self, run_id: int) -> None:
        self._angle_plan.edit_run(run_id)

    def close_runedit_dialog(self) -> None:
        self._angle_plan.close_runedit_dialog()

    def save_run(self) -> None:
        self._angle_plan.save_run()

    def remove_run(self, run_id: int) -> None:
        self._angle_plan.remove_run(run_id)

    ############################### coverage figure update ###########################################################
    def update_coverage_figure(self, _: Any = None) -> None:
        self._angle_plan.update_coverage_figure(_)

    def update_coverage_figure_with_symmetry(self, _: Any = None) -> None:
        self._angle_plan.update_coverage_figure_with_symmetry(_)

    def get_figure_coverage(self) -> go.Figure:
        return self._angle_plan.get_figure_coverage()

    def show_coverage(self) -> None:
        self._angle_plan.show_coverage()

    def close_coverage(self) -> None:
        self._angle_plan.close_coverage()

    def reset_run(self) -> None:
        self._angle_plan.reset_run()

    def optimize_angleplan(self) -> None:
        self._angle_plan.optimize_angleplan()
