"""Pydantic binding surface for the live-data tab.

Holds the per-cycle UI state (selection mode, prediction model, latest UB)
and exposes ``get_figure_intensity`` / ``get_figure_uncertainty`` for the
view. Figure construction itself lives in :mod:`.figures`; this class only
selects which series to feed each builder and memoises the result.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pydantic import BaseModel, Field

from .figures import (
    build_intensity_figure,
    build_uncertainty_figure,
    save_figure_snapshot,
    waiting_figure,
)
from .workflow import MantidWorkflow

logger = logging.getLogger(__name__)


class TemporalAnalysisModel(BaseModel):
    """Pydantic class for holding temporal analysis information."""

    table_test: List[Dict] = Field(default=[{"title": "1", "header": "h"}])
    prediction_model_type: str = Field(default="Poisson Model", title="Prediction Model")
    prediction_model_type_options: List[str] = ["Poisson Model", "Bayesian Model", "Linear Interpolation"]
    data_selection: str = Field(default="All Peaks", title="Peak Selection")
    data_selection_options: List[str] = [
        "All Peaks",
        "Bragg Peaks",
        "Satellite Peaks",
        "Max Peak",
        "Diffuse Scattering",
        "Individual Peak",
        "Peak Ratio",
    ]
    # User-entered HKLs for the modes that need them. Stored as 9 scalar
    # fields rather than 3 List[int] fields because trame's state diffing
    # doesn't reliably round-trip ``v-model="array[i]"`` writes from the
    # browser; binding each input to a top-level scalar avoids the issue.
    # Tuples are assembled at consumption time in
    # :meth:`MantidWorkflow.update_experiment_info`.
    individual_peak_h: int = Field(default=1, title="Individual peak h")
    individual_peak_k: int = Field(default=0, title="Individual peak k")
    individual_peak_l: int = Field(default=0, title="Individual peak l")
    peak_ratio_a_h: int = Field(default=1, title="Peak ratio A h (numerator)")
    peak_ratio_a_k: int = Field(default=0, title="Peak ratio A k (numerator)")
    peak_ratio_a_l: int = Field(default=0, title="Peak ratio A l (numerator)")
    peak_ratio_b_h: int = Field(default=0, title="Peak ratio B h (denominator)")
    peak_ratio_b_k: int = Field(default=1, title="Peak ratio B k (denominator)")
    peak_ratio_b_l: int = Field(default=0, title="Peak ratio B l (denominator)")

    @property
    def individual_peak_hkl(self) -> tuple[int, int, int]:
        return (self.individual_peak_h, self.individual_peak_k, self.individual_peak_l)

    @property
    def peak_ratio_hkl_a(self) -> tuple[int, int, int]:
        return (self.peak_ratio_a_h, self.peak_ratio_a_k, self.peak_ratio_a_l)

    @property
    def peak_ratio_hkl_b(self) -> tuple[int, int, int]:
        return (self.peak_ratio_b_h, self.peak_ratio_b_k, self.peak_ratio_b_l)

    time_steps: List[float] = Field(default=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0], title="Time Steps")
    intensity_data: List[float] = Field(
        default=[0.0, 1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0, 64.0, 81.0], title="Intensity Data"
    )
    variance_data: List[float] = Field(
        default=[0.0, 0.1, 0.4, 0.9, 1.6, 2.5, 3.6, 4.9, 6.4, 8.1], title="Variance Data"
    )
    uncertainty_data: List[float] = Field(
        default=[0.0, 0.2, 0.6, 1.2, 2.0, 3.0, 4.2, 5.6, 7.2, 9.0], title="Uncertainty Data"
    )
    timestamp: float = Field(default=0.0, title="timestamp")
    all_time: List[float] = Field(default=[0.0, 10000], title="All Time")
    time_interval: float = Field(default=40, title="Time Interval")

    latest_ub: List[List[float]] = Field(
        default_factory=lambda: [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        title="Latest UB",
        description="Most recent UB matrix inferred from live data (rows are UB rows).",
    )
    latest_ub_timestamp: str = Field(default="", title="Latest UB timestamp")
    latest_ub_saved_path: str = Field(default="", title="Latest UB saved path")
    latest_lattice: Dict[str, float] = Field(
        default_factory=lambda: {
            "a": 0.0,
            "b": 0.0,
            "c": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
            "volume": 0.0,
        },
        title="Latest lattice constants (Å / deg / Å³)",
    )
    latest_lattice_summary: str = Field(
        default="",
        title="Latest lattice summary",
        description="Pretty one-line a,b,c,α,β,γ,V derived from latest_lattice.",
    )
    latest_ub_rows: List[Dict[str, Any]] = Field(
        default_factory=lambda: [
            {"row": "row 1", "c1": 0.0, "c2": 0.0, "c3": 0.0},
            {"row": "row 2", "c1": 0.0, "c2": 0.0, "c3": 0.0},
            {"row": "row 3", "c1": 0.0, "c2": 0.0, "c3": 0.0},
        ],
        title="Latest UB (table rows)",
    )
    latest_ub_headers: List[Dict[str, Any]] = Field(
        default_factory=lambda: [
            {"title": "", "value": "row", "sortable": False, "align": "center"},
            {"title": "col 1", "value": "c1", "sortable": False, "align": "center"},
            {"title": "col 2", "value": "c2", "sortable": False, "align": "center"},
            {"title": "col 3", "value": "c3", "sortable": False, "align": "center"},
        ],
    )

    # Created lazily by start_reading_live_mtd_data() once Mantid is ready.
    _mtd_workflow: Optional[MantidWorkflow] = None
    # Optional back-reference to MainModel; set by MainViewModel during wiring.
    _parent: Any = None
    # Figure builders are pure-but-expensive (each refits LinearRegression).
    # Cache by (model_type, len(series), tail values) so unchanged ticks reuse the figure.
    _intensity_fig_cache: Optional[tuple[Any, go.Figure]] = None
    _uncertainty_fig_cache: Optional[tuple[Any, go.Figure]] = None

    @property
    def mtd_workflow(self) -> Optional[MantidWorkflow]:
        """Return the MantidWorkflow instance, or None if not yet initialized."""
        return self._mtd_workflow

    def set_parent(self, parent: Any) -> None:
        """Set a back-reference to the owning MainModel."""
        from exphub.techniques.single_crystal.models.root import SingleCrystalMainModel

        self._parent: SingleCrystalMainModel = parent

    def get_models(self) -> Any:
        """Return the parent MainModel (or None) without importing it here."""
        try:
            logger.debug("try get models from parent")
            if getattr(self, "_parent", None) is not None:
                logger.debug("get models from parent")
                if self._parent:
                    logger.debug(self._parent.experimentinfo)
                return self._parent
        except Exception:
            return None
        return None

    def sync_latest_ub_from_workflow(self) -> None:
        """Copy latest UB / lattice from MantidWorkflow into pydantic fields.

        The workflow holds plain Python attributes; the side-table binds to
        these pydantic fields. Called after each live-data reduction tick.
        """
        if self._mtd_workflow is None:
            return
        ub = getattr(self._mtd_workflow, "latest_ub", None)
        if ub is None:
            return
        try:
            self.latest_ub = [[float(v) for v in row] for row in ub]
            self.latest_ub_timestamp = getattr(self._mtd_workflow, "latest_ub_timestamp", "") or ""
            self.latest_ub_saved_path = getattr(self._mtd_workflow, "latest_ub_saved_path", "") or ""
            self.latest_ub_rows = [
                {
                    "row": f"row {i + 1}",
                    "c1": round(self.latest_ub[i][0], 6),
                    "c2": round(self.latest_ub[i][1], 6),
                    "c3": round(self.latest_ub[i][2], 6),
                }
                for i in range(3)
            ]
            lat = getattr(self._mtd_workflow, "latest_lattice", None)
            if lat:
                self.latest_lattice = {k: float(v) for k, v in lat.items()}
                self.latest_lattice_summary = (
                    f"a = {lat['a']:.4f} Å    b = {lat['b']:.4f} Å    c = {lat['c']:.4f} Å    "
                    f"α = {lat['alpha']:.3f}°    β = {lat['beta']:.3f}°    γ = {lat['gamma']:.3f}°    "
                    f"V = {lat['volume']:.2f} Å³"
                )
        except Exception as e:
            logger.debug(f"sync_latest_ub_from_workflow: {e}")

    # ---------- series resolution + figure dispatch ----------

    def _series_for_intensity(self) -> tuple[Any, Any]:
        wf = self._mtd_workflow
        assert wf is not None  # callers guard on _mtd_workflow is None first
        if self.prediction_model_type == "Poisson Model":
            return wf.measure_times, wf.intensity_ratios
        return wf.timeseries_plt, np.array(wf.timeseries_data_plt)

    def _series_for_uncertainty(self) -> tuple[Any, Any]:
        wf = self._mtd_workflow
        assert wf is not None  # callers guard on _mtd_workflow is None first
        if self.prediction_model_type == "Poisson Model":
            return wf.measure_times, wf.rsigs
        return wf.timeseries_plt, wf.temporal_poisson_uncertainty

    def _intensity_cache_key(self) -> Any:
        if self._mtd_workflow is None:
            return ("none",)
        ts, vals = self._series_for_intensity()
        n = len(ts)
        return (
            self.prediction_model_type,
            n,
            ts[-1] if n else None,
            vals[-1] if n and len(vals) else None,
            getattr(self._mtd_workflow, "skip_reason", "") if n == 0 else "",
        )

    def get_figure_intensity(self) -> go.Figure:
        cache_key = self._intensity_cache_key()
        cached = self._intensity_fig_cache
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        fig = self._build_figure_intensity()
        self._intensity_fig_cache = (cache_key, fig)
        return fig

    def _label_overrides(self) -> Dict[str, Optional[str]]:
        """Return per-mode title/y-axis overrides parked by the latest selector."""
        if self._mtd_workflow is None:
            return {}
        return getattr(self._mtd_workflow, "current_labels", {}) or {}

    def _build_figure_intensity(self) -> go.Figure:
        # Diffuse Scattering is an explicit placeholder mode — show
        # "Waiting for data" regardless of whether the live loop is running.
        if self.data_selection == "Diffuse Scattering":
            return waiting_figure(
                "Diffuse Scattering (not yet implemented)",
                "Intensity",
            )
        if self._mtd_workflow is None:
            return go.Figure()
        ts, vals = self._series_for_intensity()
        labels = self._label_overrides()
        return build_intensity_figure(
            ts,
            vals,
            self.prediction_model_type,
            title=labels.get("intensity_title"),
            yaxis=labels.get("intensity_yaxis"),
            skip_reason=getattr(self._mtd_workflow, "skip_reason", "") or None,
        )

    def _uncertainty_cache_key(self) -> Any:
        if self._mtd_workflow is None:
            return ("none",)
        ts, vals = self._series_for_uncertainty()
        n = len(ts)
        return (
            self.prediction_model_type,
            n,
            ts[-1] if n else None,
            vals[-1] if n and len(vals) else None,
            getattr(self._mtd_workflow, "skip_reason", "") if n == 0 else "",
        )

    def get_figure_uncertainty(self) -> go.Figure:
        cache_key = self._uncertainty_cache_key()
        cached = self._uncertainty_fig_cache
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        fig = self._build_figure_uncertainty()
        self._uncertainty_fig_cache = (cache_key, fig)
        return fig

    def _build_figure_uncertainty(self) -> go.Figure:
        if self.data_selection == "Diffuse Scattering":
            return waiting_figure(
                "Diffuse Scattering (not yet implemented)",
                "Uncertainty (%)",
            )
        if self._mtd_workflow is None:
            return go.Figure()
        ts, vals = self._series_for_uncertainty()
        # Legacy guard: uncertainty figure decided whether to plot based on
        # measure_times regardless of the active prediction-model series.
        # Preserved here for behavior parity with the pre-refactor code.
        guard_series = self._mtd_workflow.measure_times
        labels = self._label_overrides()
        return build_uncertainty_figure(
            ts,
            vals,
            self.prediction_model_type,
            guard_series=guard_series,
            title=labels.get("uncertainty_title"),
            yaxis=labels.get("uncertainty_yaxis"),
            skip_reason=getattr(self._mtd_workflow, "skip_reason", "") or None,
        )

    # ---------- mode-change buffer clear ----------

    def clear_plot_buffers(self) -> None:
        """Drop the per-cycle plot history + invalidate figure caches.

        Called whenever the *meaning* of the plotted scalar changes —
        mode switch, HKL edit in Individual/PeakRatio modes — so the
        figures don't show mixed-unit history.
        """
        self._intensity_fig_cache = None
        self._uncertainty_fig_cache = None
        if self._mtd_workflow is None:
            return
        wf = self._mtd_workflow
        try:
            wf.proton_charges.clear()
            wf.intensity_ratios.clear()
            wf.rsigs.clear()
            wf.measure_times.clear()
            wf.timeseries_plt = []
            wf.timeseries_data_plt = []
            wf.current_labels = {
                "intensity_title": None,
                "intensity_yaxis": None,
                "uncertainty_title": None,
                "uncertainty_yaxis": None,
            }
            wf.skip_reason = ""
        except Exception as e:
            logger.debug(f"clear_plot_buffers: {e}")

    def on_data_selection_change(self, new: str, old: str) -> None:
        """Thin wrapper around clear_plot_buffers for dropdown changes."""
        if new == old:
            return
        self.clear_plot_buffers()

    # ---------- figure snapshot persistence ----------

    def save_latest_figure_snapshot(self) -> Dict[str, str]:
        """Write current figures + their data to the live-monitoring dir.

        Files share a ``live_<bl>-ipts-<N>_run-<run>_<timestamp>`` prefix
        with the UB ``.mat`` saved by :meth:`MantidWorkflow.save_latest_ub`,
        though each call generates its own timestamp.

        Returns a dict of ``{kind: path}`` of files that were written;
        empty dict on failure or before any data is captured.
        """
        if self._mtd_workflow is None:
            return {}
        wf = self._mtd_workflow
        if not getattr(wf, "ipts", 0):
            return {}
        try:
            from .....core.beamline import active
            from .....core.paths import resolver_for
        except Exception:
            return {}
        try:
            fig_i = self.get_figure_intensity()
            fig_u = self.get_figure_uncertainty()
            bl_id = active().id
            import time as _time

            timestamp = _time.strftime("%Y%m%d-%H%M%S")
            run = getattr(wf, "current_run", "na")
            prefix = f"live_{bl_id}-ipts-{wf.ipts}_run-{run}_{timestamp}"
            output_dir = resolver_for(wf.ipts).live_monitor_dir + "/"
            return save_figure_snapshot(
                output_dir=output_dir,
                file_prefix=prefix,
                intensity_fig=fig_i,
                uncertainty_fig=fig_u,
                measure_times=wf.measure_times,
                intensity_ratios=wf.intensity_ratios,
                rsigs=wf.rsigs,
                proton_charges=wf.proton_charges,
            )
        except Exception as e:
            logger.debug(f"save_latest_figure_snapshot: {e}")
            return {}

    # ---------- live-data lifecycle (delegates to workflow) ----------

    def get_live_data(self) -> None:
        pass

    def generate_prediction_figure(self) -> go.Figure:
        return make_subplots(rows=1, cols=2)

    def stop_live_data(self) -> None:
        """Stop the Mantid MonitorLiveData thread if the workflow is running."""
        if self._mtd_workflow is not None:
            self._mtd_workflow.stop()

    def start_reading_live_mtd_data(self) -> None:
        if self._mtd_workflow is not None:
            self._mtd_workflow.stop()
        self._mtd_workflow = MantidWorkflow()
        models = self.get_models()
        if models is not None:
            self._mtd_workflow.update_experiment_info(models)
        self._mtd_workflow.start_live_data_collection_instances()
