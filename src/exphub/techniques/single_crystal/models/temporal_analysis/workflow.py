"""Mantid live-data orchestration.

:class:`MantidWorkflow` owns the ``StartLiveData`` session, all per-cycle
running buffers, and bookkeeping for the latest refined UB / lattice. The
per-cycle pipeline itself lives in :mod:`.pipeline`; this class wires the
phases together and exposes ``live_data_reduction()`` as the single entry
point the view-model invokes on every tick.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import mantid.simpleapi as mtdapi
import numpy as np

from .....core.beamline import active as _active_beamline
from .....core.paths import resolver_for
from . import pipeline
from ._debug import trace

logger = logging.getLogger(__name__)


class MantidWorkflow:
    """Live-data session: state buckets + per-cycle pipeline orchestration."""

    def __init__(self) -> None:
        logger.debug("initializing mtd workflow")
        # Pulled from MainModel by update_experiment_info().
        self.ipts: int = 0
        self.ub_failsafe: str = ""
        self.output_path: str = ""
        self.calib_fname: str = ""

        # Sample-environment defaults.
        self.min_d: float = 7
        self.max_d: float = 40
        self.cell_type = "Monoclinic"
        self.centering = "P"
        self.tolerance = 0.12

        # Satellite-peak parameters (kept for downstream code that reads them).
        self.satellite_peak_size = "0.07"
        self.satellite_background_inner_size = "0.09"
        self.satellite_background_outer_size = "0.12"
        self.satellite_region_radius = "0.13"
        self.mod_vector1 = "0,0,0"
        self.mod_vector2 = "0,0,0"
        self.mod_vector3 = "0,0,0"
        self.max_order = "1"
        self.cross_terms = False
        self.tolerance_satellite = 0.10
        self.save_mod_info = False
        self.min_monitor_tof = 500
        self.max_monitor_tof = 13000
        self.use_monitor_counts = False

        # Latest UB + lattice captured from the live workspace.
        self.latest_ub: Optional[List[List[float]]] = None
        self.latest_lattice: Optional[Dict[str, float]] = None
        self.latest_ub_timestamp: str = ""
        self.latest_ub_saved_path: str = ""

        # Per-cycle history buffers; figures plot these.
        self.proton_charges: list[float] = []
        self.intensity_ratios: list[float] = []
        self.rsigs: list[float] = []
        self.measure_times: list[float] = []
        self.measure_times_sim: list[float] = []
        self.intensity_ratios_sim: list[float] = []
        self.rsigs_sim: list[float] = []
        self.sum = self.sig2 = self.sig3 = self.sig5 = self.sig10 = 0
        self.sig2s: list = []
        self.sig3s: list = []
        self.sig5s: list = []
        self.sig10s: list = []
        self.missing_ub_number = 0

        self.current_run_end_time = 0
        self.measure_time = 0
        self.proton_charge = 0
        self.maxpeak_idx = -1
        self.timeseries: Any = np.array([])
        self.timeseries_data: List[np.ndarray] = []
        self.maxpeak_int_i = 0

        self.time_interval = 40
        self.total_time_of_run = 0
        self.total_numberof_time_intervals = 1
        self.time_of_poissonprocess = 0
        self.hkl: List[Any] = []
        self.timeseries_plt: Any = []
        self.timeseries_data_plt: Any = []
        self.temporal_poisson_intensity: Any = [0]
        self.temporal_poisson_uncertainty: Any = [0]

        # Optional kwargs passed to selector factories (e.g. {"hkl": (1,0,0)}).
        self.selector_params: dict[str, Any] = {}
        self.selection_aux: dict[str, Any] = {}
        # Set per cycle by ``pipeline.check_peaks`` after a successful
        # selector.select() — None entries mean "use figure defaults".
        self.current_labels: dict[str, Optional[str]] = {
            "intensity_title": None,
            "intensity_yaxis": None,
            "uncertainty_title": None,
            "uncertainty_yaxis": None,
        }
        # Set to True by ``pipeline.check_peaks`` when the active selector
        # returned None (no peak match, placeholder mode, ...). The
        # view-model can react by showing a "Waiting for data" figure.
        self.skip_this_cycle: bool = False
        # Human-readable reason from the most recent skipped cycle. Read by
        # the figure builders so the on-screen placeholder names the actual
        # problem (e.g. "Peak (1,0,0) not indexed in workspace") instead of
        # a generic "Waiting for data".
        self.skip_reason: str = ""
        # Reset by ``pipeline.check_peaks`` per cycle (live ratio for
        # the figures); seeded here so legacy fall-through doesn't trip
        # an AttributeError on first read.
        self.intensity_ratio: float = 0.0
        self.Rsig: float = 0.0

    def stop(self) -> None:
        """Cancel any in-flight MonitorLiveData thread."""
        try:
            from mantid.api import AlgorithmManager

            for alg in AlgorithmManager.runningInstancesOf("MonitorLiveData"):
                alg.cancel()
        except Exception as e:
            logger.warning(f"StopLiveData warning: {e}")

    # ---------- UB + lattice readback ----------

    def get_latest_ub(self, workspace_name: str = "live_predict_peaks_ws") -> Optional[List[List[float]]]:
        """Return the latest UB matrix from the named peaks workspace, or None."""
        try:
            ws = mtdapi.mtd[workspace_name]
            lattice = ws.sample().getOrientedLattice()
            ub = lattice.getUB()
            return [[float(ub[i][j]) for j in range(3)] for i in range(3)]
        except Exception as e:
            logger.debug(f"get_latest_ub: could not read UB from {workspace_name}: {e}")
            return None

    def get_latest_lattice(self, workspace_name: str = "live_predict_peaks_ws") -> Optional[Dict[str, float]]:
        """Return lattice constants (a,b,c Å — α,β,γ deg — V Å³)."""
        try:
            ws = mtdapi.mtd[workspace_name]
            lat = ws.sample().getOrientedLattice()
            return {
                "a": float(lat.a()),
                "b": float(lat.b()),
                "c": float(lat.c()),
                "alpha": float(lat.alpha()),
                "beta": float(lat.beta()),
                "gamma": float(lat.gamma()),
                "volume": float(lat.volume()),
            }
        except Exception as e:
            logger.debug(f"get_latest_lattice: could not read lattice from {workspace_name}: {e}")
            return None

    def save_latest_ub(self, workspace_name: str = "live_predict_peaks_ws") -> Optional[str]:
        """Save the UB matrix to the per-IPTS live-monitoring directory."""
        try:
            ws = mtdapi.mtd[workspace_name]
            ws.sample().getOrientedLattice()
        except Exception as e:
            logger.debug(f"save_latest_ub: workspace '{workspace_name}' has no UB yet: {e}")
            return None

        resolver = resolver_for(self.ipts)
        save_dir = resolver.live_monitor_dir + "/"
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            logger.debug(f"save_latest_ub: could not create {save_dir}: {e}")
            return None

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        bl_id = resolver.ctx.id
        filename = f"live_{bl_id}-ipts-{self.ipts}_run-{getattr(self, 'current_run', 'na')}_{timestamp}.mat"
        path = os.path.join(save_dir, filename)
        try:
            mtdapi.SaveIsawUB(InputWorkspace=workspace_name, Filename=path)
            logger.debug(f"save_latest_ub: wrote {path}")
            return path
        except Exception as e:
            logger.warning(f"save_latest_ub: SaveIsawUB failed for {path}: {e}")
            return None

    # ---------- experiment info & filenames ----------

    def update_experiment_info(self, _models: Any) -> None:
        from exphub.techniques.single_crystal.models.root import SingleCrystalMainModel

        models: SingleCrystalMainModel = _models

        self.ipts = int(models.experimentinfo.ipts_number)
        self.cell_type = models.experimentinfo.crystalsystem
        self.point_group = models.experimentinfo.point_group
        self.centering = models.experimentinfo.centering
        self.min_d = models.experimentinfo.min_dspacing
        self.max_d = models.experimentinfo.max_dspacing
        self.calib_fname = models.experimentinfo.cal_filename
        logger.debug("update experiment info")
        if models.experimentinfo.UBFileName:
            self.ub_failsafe = models.experimentinfo.UBFileName
        self.output_path = resolver_for(self.ipts).autoreduce_dir + "/live_data/"

        self.selection = models.temporalanalysis.data_selection
        # Selector kwargs for the registry factory; unused keys are
        # ignored by selectors that don't take them. HKLs are stored as
        # scalar pydantic fields and assembled into tuples here.
        ta = models.temporalanalysis
        self.selector_params = {
            "hkl": (ta.individual_peak_h, ta.individual_peak_k, ta.individual_peak_l),
            "hkl_a": (ta.peak_ratio_a_h, ta.peak_ratio_a_k, ta.peak_ratio_a_l),
            "hkl_b": (ta.peak_ratio_b_h, ta.peak_ratio_b_k, ta.peak_ratio_b_l),
        }

    def update_peak_output_filenames(self) -> None:
        bl_id = _active_beamline().id
        if self.cell_type is not None:
            self.live_peaks_fname = "live_%s-ipts-%s_%s_%s_%s.integrate" % (
                bl_id,
                str(self.ipts),
                str(self.current_run),
                self.cell_type,
                self.centering,
            )
            self.live_peaks_ub_fname = "live_%s-ipts-%s_%s__%s_%s.mat" % (
                bl_id,
                str(self.ipts),
                str(self.current_run),
                self.cell_type,
                self.centering,
            )
        else:
            self.live_peaks_fname = "live_%s-ipts-%s_%s_Niggli.integrate" % (
                bl_id,
                str(self.ipts),
                str(self.current_run),
            )
            self.live_peaks_ub_fname = "live_%s-ipts-%s_%s_Niggli.mat" % (
                bl_id,
                str(self.ipts),
                str(self.current_run),
            )

    # ---------- live-data lifecycle ----------

    def start_live_data_collection_instances(self) -> None:
        """Kick off StartLiveData; the per-cycle reduction is driven separately."""
        instrument_name = _active_beamline().single_crystal.mantid.instrument_name
        try:
            mtdapi.StartLiveData(
                Instrument=instrument_name,
                Listener="SNSLiveEventDataListener",
                UpdateEvery=self.time_interval,
                AccumulationMethod="Add",
                PreserveEvents=True,
                OutputWorkspace="live_event_ws",
            )
            self.monitor_start_time = mtdapi.mtd["live_event_ws"].getRun().startTime().totalNanoseconds() * 1e-9
            time.sleep(1)
        except RuntimeError as e:
            if "Another MonitorLiveData thread is running" in str(e):
                conflict_current_run = mtdapi.mtd["live_event_ws"].getRunNumber()
                msg = (
                    "Another MonitorLiveData thread is already running for %s run %s. "
                    "Stop the existing live-update session before starting a new one."
                ) % (instrument_name, str(conflict_current_run))
                logger.warning("%s %s", "Warning:", msg)
                raise RuntimeError(msg) from e
            else:
                logger.warning(f"Unexpected error occurred: {str(e)}")
                raise

        if not mtdapi.mtd.doesExist("live_event_ws"):
            raise RuntimeError("Live data workspace 'live_event_ws' does not exist after StartLiveData.")
        self.initial_run = mtdapi.mtd["live_event_ws"].getRunNumber()
        self.initial_run_start_time = mtdapi.mtd["live_event_ws"].getRun().startTime().totalNanoseconds() * 1e-9
        logger.debug(f"initial run: {self.initial_run}")

        self.current_run = self.initial_run
        self.current_run_start_time = self.initial_run_start_time
        self.update_peak_output_filenames()

    def live_data_reduction(self) -> None:
        """One cycle: checkpoint → load → refine → integrate → check."""
        logger.debug("============================================================================================")
        trace("live data reduction started")
        logger.debug("============================================================================================")
        pipeline.run_change_checkpoint(self)
        pipeline.load_config(self)
        pipeline.refine_ub(self)
        pipeline.integrate_and_predict(self)
        pipeline.check_peaks(self)
