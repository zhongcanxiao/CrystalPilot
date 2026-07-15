"""Pure figure builders for the live-data tab.

Each builder takes a slice of :class:`MantidWorkflow` series + the
prediction-model name and returns a fully laid-out plotly ``Figure``.
Functions are deliberately pure (no I/O, no module/class state) so they
can be reused across selection modes and dropped onto a unit test.

The caller (:class:`TemporalAnalysisModel`) decides which series to feed
in based on the active prediction model and peak-selection mode. Optional
``title`` / ``yaxis`` overrides let selectors customise labels per mode
(e.g. ``Peak Ratio`` plotting ``I_a / I_b`` instead of "Signal Noise Ratio").
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional, Sequence

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from sklearn.linear_model import LinearRegression

from ._debug import trace

logger = logging.getLogger(__name__)

FIG_MARGIN = {"l": 50, "r": 15, "t": 35, "b": 40}
GRID_KWARGS = {
    "showgrid": True,
    "gridcolor": "rgba(120,120,120,0.35)",
    "gridwidth": 1,
    "griddash": "dot",
}


def _apply_axes(fig: go.Figure) -> None:
    fig.update_xaxes(showline=True, linewidth=2, linecolor="black", mirror=True, **GRID_KWARGS)
    fig.update_yaxes(showline=True, linewidth=2, linecolor="black", mirror=True, **GRID_KWARGS)


def _waiting_for_data(
    fig: go.Figure,
    title: str,
    yaxis_title: str,
    message: Optional[str] = None,
) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        xaxis_title="Time Steps (s)",
        yaxis_title=yaxis_title,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=FIG_MARGIN,
    )
    _apply_axes(fig)
    text = message if message else "Waiting for data"
    fig.add_annotation(
        text=text,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 18, "color": "red"},
        align="center",
    )
    return fig


def waiting_figure(title: str, yaxis_title: str, message: Optional[str] = None) -> go.Figure:
    """Public helper: return a stand-alone placeholder figure.

    ``message`` overrides the default "Waiting for data" annotation —
    used by selector-aware callers to surface a more specific reason
    (e.g. "Peak (1,0,0) not indexed in workspace").
    """
    return _waiting_for_data(go.Figure(), title, yaxis_title, message=message)


def build_intensity_figure(
    time_steps: List[float],
    intensity_data: Any,
    model_type: str,
    title: Optional[str] = None,
    yaxis: Optional[str] = None,
    skip_reason: Optional[str] = None,
) -> go.Figure:
    """Top figure: intensity-ratio history + extrapolated prediction line.

    ``title`` and ``yaxis`` override the defaults derived from
    ``model_type`` (used by modes like ``Peak Ratio`` that plot a
    different quantity).
    """
    fig = go.Figure()

    if title is None or yaxis is None:
        if model_type == "Linear Interpolation":
            default_title = "Prediction of Intensity"
            default_yaxis = "Intensity"
        else:
            default_title = "Prediction of Signal Noise Ratio"
            default_yaxis = "Signal Noise Ratio"
        title = title or default_title
        yaxis = yaxis or default_yaxis

    if len(time_steps) > 0:
        logger.debug("============================================================================================")
        trace("time_steps")
        trace(time_steps)
        trace("intensity_data")
        trace(intensity_data)
        logger.debug("============================================================================================")

        x = np.array(time_steps).reshape(-1, 1) ** 0.5
        y = np.array(intensity_data)

        model = LinearRegression()
        model.fit(x, y)
        slope = model.coef_[0]
        intercept = model.intercept_
        trace(f"Slope: {slope}, Intercept: {intercept}")

        if model_type == "Linear Interpolation":
            x_range = np.linspace(max(time_steps), max(time_steps) + 2000, 100)
            y_range = np.zeros_like(x_range) + np.array(intensity_data)[-1]
        else:
            x_range = np.linspace(max(time_steps), max(time_steps) + 2000, 100)
            y_range = slope * x_range**0.5 + intercept

        fig.add_trace(go.Scatter(x=x_range, y=y_range, mode="lines", name="Prediction Line", line={"dash": "dash"}))
        fig.add_trace(go.Scatter(x=time_steps, y=intensity_data, mode="lines+markers", name="History Data"))
        fig.update_layout(
            title={"text": title, "x": 0.5, "xanchor": "center"},
            xaxis_title="Time Steps (s)",
            yaxis_title=yaxis,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=FIG_MARGIN,
        )
        _apply_axes(fig)
    else:
        _waiting_for_data(fig, title, yaxis, message=skip_reason)
    return fig


def build_uncertainty_figure(
    time_steps: List[float],
    uncertainty_data: Any,
    model_type: str,
    guard_series: Optional[List[float]] = None,
    title: Optional[str] = None,
    yaxis: Optional[str] = None,
    skip_reason: Optional[str] = None,
) -> go.Figure:
    """Bottom figure: σ(I)/I (Rsig) history + fitted prediction curve.

    The legacy build guarded plotting on ``len(measure_times)`` regardless
    of the active series; ``guard_series`` reproduces that behavior. Pass
    ``None`` to guard on ``time_steps`` directly. ``title`` and ``yaxis``
    override defaults per mode.
    """
    fig = go.Figure()

    if title is None or yaxis is None:
        if model_type == "Linear Interpolation":
            default_title = "Prediction of Uncertainty"
            default_yaxis = "Uncertainty (%)"
        else:
            default_title = "Prediction of σ(I)/I"
            default_yaxis = "σ(I)/I (%)"
        title = title or default_title
        yaxis = yaxis or default_yaxis

    if model_type == "Linear Interpolation":
        ts_arr = np.array(time_steps)
        un_arr = np.array(uncertainty_data)
        nozero_mask = np.where(ts_arr > 0)
        x_pre = np.array(ts_arr[nozero_mask]).reshape(-1, 1)
        y_pre = np.array(un_arr[nozero_mask])
        if len(y_pre) > 0:
            x_transformed_pre = 1 / x_pre**0.5
            trace("X_transformed")
            trace(x_transformed_pre)
            trace("y")
            trace(y_pre)
            model_pre = LinearRegression()
            model_pre.fit(x_transformed_pre, y_pre)
            trace(f"Slope: {model_pre.coef_[0]}, Intercept: {model_pre.intercept_}")

    guard = guard_series if guard_series is not None else time_steps
    if len(guard) > 0:
        un_arr = np.array(uncertainty_data)
        ts_arr = np.array(time_steps)
        x = np.array(ts_arr).reshape(-1, 1)
        y = np.array(un_arr) ** -1
        x_transformed = x**0.5
        trace("X_transformed")
        trace(x_transformed)
        trace("y")
        trace(y)

        model = LinearRegression()
        model.fit(x_transformed, y)
        slope = model.coef_[0]
        intercept = model.intercept_
        trace(f"Slope: {slope}, Intercept: {intercept}")

        x_range = np.linspace(max(ts_arr), max(ts_arr) + 2000, 100)
        y_range = (slope * (x_range**0.5) + intercept) ** -1

        fig.add_trace(go.Scatter(x=x_range, y=y_range, mode="lines", name="Fitted Line", line={"dash": "dash"}))
        logger.debug("============================================================================================")
        trace("time_steps")
        trace(ts_arr)
        trace("uncertainty_data")
        trace(un_arr)
        logger.debug("============================================================================================")
        fig.add_trace(go.Scatter(x=ts_arr, y=un_arr, mode="lines+markers", name="Uncertainty Data"))
        fig.update_layout(
            title={"text": title, "x": 0.5, "xanchor": "center"},
            xaxis_title="Time Steps (s)",
            yaxis_title=yaxis,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=FIG_MARGIN,
        )
        _apply_axes(fig)
    else:
        _waiting_for_data(fig, title, yaxis, message=skip_reason)
    return fig


# ---------- snapshot persistence ----------


def save_figure_snapshot(
    output_dir: str,
    file_prefix: str,
    *,
    intensity_fig: go.Figure,
    uncertainty_fig: go.Figure,
    measure_times: Sequence[float],
    intensity_ratios: Sequence[float],
    rsigs: Sequence[float],
    proton_charges: Optional[Sequence[float]] = None,
) -> dict[str, str]:
    """Persist the current figures + their underlying data to ``output_dir``.

    Three files are written, all sharing ``file_prefix``:

    - ``<prefix>_intensity.html``    — interactive top plot
    - ``<prefix>_uncertainty.html``  — interactive bottom plot
    - ``<prefix>_data.csv``          — the buffers driving the figures

    Returns a dict of ``{kind: path}`` for the files that were written.
    Missing values (empty buffers, write errors) are silently skipped;
    this runs on every reduction cycle and must not raise.
    """
    written: dict[str, str] = {}
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        logger.debug(f"save_figure_snapshot: could not create {output_dir}: {e}")
        return written

    intensity_path = os.path.join(output_dir, f"{file_prefix}_intensity.html")
    uncertainty_path = os.path.join(output_dir, f"{file_prefix}_uncertainty.html")
    data_path = os.path.join(output_dir, f"{file_prefix}_data.csv")

    try:
        pio.write_html(intensity_fig, file=intensity_path, include_plotlyjs="cdn", auto_open=False)
        written["intensity"] = intensity_path
    except Exception as e:
        logger.warning(f"save_figure_snapshot: write_html(intensity) failed: {e}")

    try:
        pio.write_html(uncertainty_fig, file=uncertainty_path, include_plotlyjs="cdn", auto_open=False)
        written["uncertainty"] = uncertainty_path
    except Exception as e:
        logger.warning(f"save_figure_snapshot: write_html(uncertainty) failed: {e}")

    try:
        n = len(measure_times)
        if n > 0:
            cols = [np.asarray(measure_times, dtype=float)]
            header = ["time_s"]
            if proton_charges is not None and len(proton_charges) == n:
                cols.append(np.asarray(proton_charges, dtype=float))
                header.append("proton_charge_C")
            cols.append(np.asarray(intensity_ratios[:n], dtype=float))
            header.append("intensity_ratio")
            cols.append(np.asarray(rsigs[:n], dtype=float))
            header.append("rsig_or_uncertainty_pct")
            stacked = np.column_stack(cols)
            np.savetxt(
                data_path,
                stacked,
                delimiter=",",
                header=",".join(header),
                comments="",
            )
            written["data"] = data_path
    except Exception as e:
        logger.warning(f"save_figure_snapshot: data CSV write failed: {e}")

    return written
