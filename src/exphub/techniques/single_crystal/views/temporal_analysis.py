"""Module for the Temporal Analysis tab."""

import logging
import time
from typing import List, Tuple

import plotly.graph_objects as go
from nova.epics.trame import PVInput
from nova.trame.view.components import InputField
from nova.trame.view.layouts import GridLayout, HBoxLayout, VBoxLayout
from trame.widgets import html, plotly
from trame.widgets import vuetify3 as vuetify

from ....core.beamline import active as _active_beamline
from ..view_models.steering import SingleCrystalSteeringViewModel

logger = logging.getLogger(__name__)

# Plotly layout shared across the live-data plots in this view.
_FIG_MARGIN = {"l": 50, "r": 15, "t": 35, "b": 40}
_GRID_KWARGS = {
    "showgrid": True,
    "gridcolor": "rgba(120,120,120,0.35)",
    "gridwidth": 1,
    "griddash": "dot",
}


def temporal_data_analysis() -> Tuple[List[int], List[int]]:
    # Dummy data generation for the plot
    x_data = list(range(10))
    y_data = [i**2 for i in x_data]
    return x_data, y_data


class TemporalAnalysisView:
    """View class to render the Temporal Analysis tab."""

    def __init__(self, view_model: SingleCrystalSteeringViewModel) -> None:
        self.view_model = view_model
        # guards to avoid re-entrant or too-frequent view updates
        self._updating_intensity = False
        self._last_intensity_time = 0.0
        self._min_interval_intensity = 0.5

        self._updating_uncertainty = False
        self._last_uncertainty_time = 0.0
        self._min_interval_uncertainty = 0.5
        self.view_model.temporalanalysis_bind.connect("model_temporalanalysis")
        # The steering view-state (HKL popover visibility + live-update flag)
        # is owned by the steering VM and exposed under its own ``steering``
        # namespace — the app shell owns ``controls``. This view is the only
        # consumer of those flags, so it connects the bind here.
        self.view_model.view_state_bind.connect("steering")
        self.view_model.temporalanalysis_updatefigure_intensity_bind.connect(self.update_figure_intensity)
        self.view_model.temporalanalysis_updatefigure_uncertainty_bind.connect(self.update_figure_uncertainty)
        # Allow the view model to push placeholder figures immediately on start
        self.view_model._temporal_view = self
        self.create_ui()

    def create_ui(self) -> None:
        x_data, y_data = temporal_data_analysis()
        # with vuetify.VContainer(fluid=True, classes="pa-5"):
        #        vuetify.VCardTitle("Temporal Analysis"),
        #        vuetify.VCardText("Content for Temporal Analysis tab goes here."),
        with GridLayout(columns=3, gap="0.5em"):
            InputField(
                v_model="model_temporalanalysis.prediction_model_type",
                items="model_temporalanalysis.prediction_model_type_options",
                type="select",
            )
            # Peak-selection dropdown + inline HKL chips. The chips are
            # always in DOM (v-show, not v-if) so VMenu's activator selector
            # can resolve them at mount time. An explicit click handler on
            # each chip toggles the menu's v-model as a fallback if the
            # activator binding misbehaves.
            with html.Div(
                style="display: flex; align-items: center; gap: 0.5em; flex-wrap: wrap;",
            ):
                with html.Div(style="flex: 1 1 auto; min-width: 180px;"):
                    InputField(
                        v_model="model_temporalanalysis.data_selection",
                        items="model_temporalanalysis.data_selection_options",
                        type="select",
                    )
                vuetify.VChip(
                    "HKL [{{ model_temporalanalysis.individual_peak_h }},"
                    " {{ model_temporalanalysis.individual_peak_k }},"
                    " {{ model_temporalanalysis.individual_peak_l }}] ✎",
                    id="hkl-chip-individual",
                    v_show="model_temporalanalysis.data_selection === 'Individual Peak'",
                    size="small",
                    variant="outlined",
                    style="cursor: pointer;",
                    click="steering.hkl_individual_menu = !steering.hkl_individual_menu",
                )
                with vuetify.VMenu(
                    activator="#hkl-chip-individual",
                    v_model=("steering.hkl_individual_menu", False),
                    close_on_content_click=False,
                    location="bottom",
                ):
                    with vuetify.VCard(min_width=280, classes="pa-2"):
                        vuetify.VCardSubtitle("Edit individual-peak HKL")
                        with vuetify.VCardText():
                            with GridLayout(columns=3, gap="0.5em"):
                                InputField(
                                    v_model="model_temporalanalysis.individual_peak_h",
                                    type="number",
                                    label="h",
                                    density="compact",
                                )
                                InputField(
                                    v_model="model_temporalanalysis.individual_peak_k",
                                    type="number",
                                    label="k",
                                    density="compact",
                                )
                                InputField(
                                    v_model="model_temporalanalysis.individual_peak_l",
                                    type="number",
                                    label="l",
                                    density="compact",
                                )
                        with vuetify.VCardActions():
                            vuetify.VBtn(
                                "Apply",
                                click=self.view_model.apply_individual_hkl,
                                color="primary",
                                size="small",
                                variant="elevated",
                            )
                vuetify.VChip(
                    "[{{ model_temporalanalysis.peak_ratio_a_h }},"
                    " {{ model_temporalanalysis.peak_ratio_a_k }},"
                    " {{ model_temporalanalysis.peak_ratio_a_l }}]"
                    " / [{{ model_temporalanalysis.peak_ratio_b_h }},"
                    " {{ model_temporalanalysis.peak_ratio_b_k }},"
                    " {{ model_temporalanalysis.peak_ratio_b_l }}] ✎",
                    id="hkl-chip-peak-ratio",
                    v_show="model_temporalanalysis.data_selection === 'Peak Ratio'",
                    size="small",
                    variant="outlined",
                    style="cursor: pointer;",
                    click="steering.hkl_peak_ratio_menu = !steering.hkl_peak_ratio_menu",
                )
                with vuetify.VMenu(
                    activator="#hkl-chip-peak-ratio",
                    v_model=("steering.hkl_peak_ratio_menu", False),
                    close_on_content_click=False,
                    location="bottom",
                ):
                    with vuetify.VCard(min_width=320, classes="pa-2"):
                        vuetify.VCardSubtitle("Edit peak-ratio HKLs (numerator / denominator)")
                        with vuetify.VCardText():
                            with html.Div(
                                style="display: flex; align-items: center; gap: 0.5em; margin-bottom: 0.3em;",
                            ):
                                vuetify.VLabel("Peak A", style="min-width: 60px; font-size: 0.85em;")
                                with html.Div(style="flex: 1 1 auto;"):
                                    with GridLayout(columns=3, gap="0.3em"):
                                        InputField(
                                            v_model="model_temporalanalysis.peak_ratio_a_h",
                                            type="number",
                                            label="h",
                                            density="compact",
                                        )
                                        InputField(
                                            v_model="model_temporalanalysis.peak_ratio_a_k",
                                            type="number",
                                            label="k",
                                            density="compact",
                                        )
                                        InputField(
                                            v_model="model_temporalanalysis.peak_ratio_a_l",
                                            type="number",
                                            label="l",
                                            density="compact",
                                        )
                            with html.Div(
                                style="display: flex; align-items: center; gap: 0.5em;",
                            ):
                                vuetify.VLabel("Peak B", style="min-width: 60px; font-size: 0.85em;")
                                with html.Div(style="flex: 1 1 auto;"):
                                    with GridLayout(columns=3, gap="0.3em"):
                                        InputField(
                                            v_model="model_temporalanalysis.peak_ratio_b_h",
                                            type="number",
                                            label="h",
                                            density="compact",
                                        )
                                        InputField(
                                            v_model="model_temporalanalysis.peak_ratio_b_k",
                                            type="number",
                                            label="k",
                                            density="compact",
                                        )
                                        InputField(
                                            v_model="model_temporalanalysis.peak_ratio_b_l",
                                            type="number",
                                            label="l",
                                            density="compact",
                                        )
                        with vuetify.VCardActions():
                            vuetify.VBtn(
                                "Apply",
                                click=self.view_model.apply_peak_ratio_hkls,
                                color="primary",
                                size="small",
                                variant="elevated",
                            )
            InputField(
                v_model="model_temporalanalysis.time_interval",
            )
            # with GridLayout(columns=4):
            # InputField(v_model="model_cssstatus.plot_type", items="model_cssstatus.plot_type_options", type="select")
            # InputField(v_model="model_cssstatus.x_axis", items="model_cssstatus.axis_options", type="select")
            # InputField(v_model="model_cssstatus.y_axis", items="model_cssstatus.axis_options", type="select")
            # InputField(
            #    v_model="model_cssstatus.z_axis",
            #    disabled=("model_cssstatus.is_not_heatmap",),
            #    items="model_cssstatus.axis_options",
            #    type="select",
            # )
        fig_i = go.Figure()
        fig_i.update_layout(
            title={"text": "Prediction of Signal Noise Ratio", "x": 0.5, "xanchor": "center"},
            xaxis_title="Time Steps (s)",
            yaxis_title=" ",
            xaxis={"range": [0, 2000]},
            yaxis={"range": [0, 100]},
            paper_bgcolor="rgba(10,10,10,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=_FIG_MARGIN,
        )

        fig_u = go.Figure()
        fig_u.update_layout(
            title={"text": "Prediction of Uncertainty", "x": 0.5, "xanchor": "center"},
            xaxis_title="Time Steps (s)",
            paper_bgcolor="rgba(10,10,10,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="",
            xaxis={"range": [0, 2000]},
            yaxis={"range": [0, 100]},
            showlegend=False,
            margin=_FIG_MARGIN,
        )
        fig_u.update_xaxes(showline=True, linewidth=2, linecolor="black", mirror=True, **_GRID_KWARGS)
        fig_u.update_yaxes(showline=True, linewidth=2, linecolor="black", mirror=True, **_GRID_KWARGS)

        fig_i.update_xaxes(showline=True, linewidth=2, linecolor="black", mirror=True, **_GRID_KWARGS)
        fig_i.update_yaxes(showline=True, linewidth=2, linecolor="black", mirror=True, **_GRID_KWARGS)

        # with HBoxLayout(halign="left",  height="50vh"):
        #    self.figure_intensity
        # with HBoxLayout(halign="right", height="50vh"):
        #    self.figure_uncertainty
        # with GridLayout(columns=2):
        #    self.figure_intensity
        #    self.figure_uncertainty

        # Figures own the lion's share of vertical space.
        with html.Div(style=("flex: 4 1 0;min-height: 0;display: flex;flex-direction: column;")):
            with GridLayout(columns=2, gap="0.5em", stretch=True):
                self.figure_intensity = plotly.Figure()
                self.figure_intensity.update(fig_i)

                self.figure_uncertainty = plotly.Figure()
                self.figure_uncertainty.update(fig_u)

        # Compact side-table: latest UB + lattice + live beam readouts.
        # UB and lattice render side-by-side in the left card so the whole
        # info strip is short vertically.
        cell_style = (
            "font-family: monospace;"
            "font-size: 0.85em;"
            "text-align: right;"
            "padding: 2px 6px;"
            "border: 1px solid rgba(0,0,0,0.12);"
            "border-radius: 3px;"
            "min-width: 70px;"
        )
        section_label = "font-weight: 600; font-size: 0.85em;"
        meta_label = "font-size: 0.75em; color: rgba(0,0,0,0.6);"

        # Use a fixed flex ratio so this strip never bloats: ~1 unit of
        # vertical space against 4 units of figure space (configurable via
        # the parent VBoxLayout from tab_content_panel.py).
        with html.Div(style="flex: 0 0 auto;"):
            with GridLayout(columns=2, gap="0.5em"):
                # Left card: UB + lattice, rendered side by side.
                with html.Div(
                    classes="border-md pa-2",
                    style="display: flex; gap: 0.75em; align-items: flex-start;",
                ):
                    # UB matrix column
                    with html.Div(style="flex: 1 1 0;"):
                        vuetify.VLabel("Latest UB", style=section_label)
                        vuetify.VLabel(
                            "{{ model_temporalanalysis.latest_ub_timestamp"
                            " ? 'updated ' + model_temporalanalysis.latest_ub_timestamp"
                            " : 'no UB yet' }}",
                            style=meta_label,
                        )
                        with GridLayout(columns=3, gap="0.15em"):
                            for i in range(3):
                                for j in range(3):
                                    vuetify.VLabel(
                                        "{{ (model_temporalanalysis.latest_ub["
                                        + str(i)
                                        + "] || [])["
                                        + str(j)
                                        + "] != null"
                                        " ? Number(model_temporalanalysis.latest_ub["
                                        + str(i)
                                        + "]["
                                        + str(j)
                                        + "]).toFixed(5) : '—' }}",
                                        style=cell_style,
                                    )
                    # Lattice column
                    with html.Div(style="flex: 1 1 0;"):
                        vuetify.VLabel(
                            "Lattice (Å, °, Å³)",
                            style=section_label,
                        )
                        vuetify.VLabel("", style=meta_label)  # spacer to align with UB
                        lattice_cells: list[tuple[str, str, int]] = [
                            ("a", "Å", 3),
                            ("b", "Å", 3),
                            ("c", "Å", 3),
                            ("alpha", "°", 2),
                            ("beta", "°", 2),
                            ("gamma", "°", 2),
                        ]
                        with GridLayout(columns=3, gap="0.15em"):
                            for key, unit, prec in lattice_cells:
                                vuetify.VLabel(
                                    "{{ (model_temporalanalysis.latest_lattice && "
                                    "model_temporalanalysis.latest_lattice['" + key + "'] != null)"
                                    " ? Number(model_temporalanalysis.latest_lattice['"
                                    + key
                                    + "']).toFixed("
                                    + str(prec)
                                    + ") + ' "
                                    + unit
                                    + "' : '—' }}",
                                    style=cell_style,
                                )
                        # Volume on its own short row, spans the full width.
                        vuetify.VLabel(
                            "{{ (model_temporalanalysis.latest_lattice && "
                            "model_temporalanalysis.latest_lattice['volume'] != null)"
                            " ? 'V = ' + Number(model_temporalanalysis.latest_lattice['volume']).toFixed(2) + ' Å³'"
                            " : '' }}",
                            style="font-family: monospace; font-size: 0.8em; padding-top: 2px;",
                        )

                # Right card: beam status, compact.
                with VBoxLayout(classes="border-md pa-2", gap="0.15em"):
                    vuetify.VLabel("Beam status (live)", style=section_label)
                    with GridLayout(columns=2, gap="0.2em"):
                        _mon = _active_beamline().detector.monitor_pvs
                        if _mon.get("proton_charge"):
                            PVInput(_mon["proton_charge"], append="C", label="Proton Charge")
                        if _mon.get("beam_power"):
                            PVInput(_mon["beam_power"], append="MW", label="Beam Power")
                    # Saved-path line goes here so it doesn't pad the UB card.
                    vuetify.VLabel(
                        "{{ model_temporalanalysis.latest_ub_saved_path"
                        " ? 'UB saved: ' + model_temporalanalysis.latest_ub_saved_path"
                        " : '' }}",
                        style="font-size: 0.7em; color: rgba(0,0,0,0.55); word-break: break-all;",
                    )

        with HBoxLayout(halign="left"):
            vuetify.VBtn(
                "Start Live Data Monitoring",
                click=self.view_model.create_auto_update_temporalanalysis_figure,
                disabled=("steering.is_live_update_running",),
                size="small",
            )
            vuetify.VBtn(
                "Stop Live Data Monitoring",
                click=self.view_model.stop_live_update,
                disabled=("!steering.is_live_update_running",),
                size="small",
            )

    @staticmethod
    def _make_placeholder(title: str) -> go.Figure:
        """Return an empty figure with a centered 'Collecting live data...' annotation."""
        fig = go.Figure()
        fig.update_layout(
            title={"text": title, "x": 0.5, "xanchor": "center"},
            xaxis={"visible": False},
            yaxis={"visible": False},
            paper_bgcolor="rgba(10,10,10,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=_FIG_MARGIN,
            annotations=[
                {
                    "text": "Collecting live data\u2026",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 24, "color": "gray"},
                }
            ],
        )
        return fig

    def show_placeholders(self) -> None:
        """Push placeholder figures to both chart widgets."""
        self.update_figure_intensity(self._make_placeholder("Prediction of Signal Noise Ratio"))
        self.update_figure_uncertainty(self._make_placeholder("Prediction of Uncertainty"))

    def update_figure_intensity(self, figure_intensity: go.Figure) -> None:
        # debounce / re-entrancy guard
        now = time.time()
        if self._updating_intensity:
            return
        if now - self._last_intensity_time < self._min_interval_intensity:
            return
        self._updating_intensity = True
        try:
            self.figure_intensity.update(figure_intensity)
            # flush view state to ensure it is rendered; this can trigger state listeners,
            # so keep it guarded to avoid feedback loops
            self.figure_intensity.state.flush()
            self._last_intensity_time = now
            logger.debug("============================================================================================")
            logger.debug("update_figure_intensity")
            logger.debug("============================================================================================")
        finally:
            self._updating_intensity = False
        # print("Currently plotted data:", self.figure_intensity.data)
        # print("Currently plotted data:", self.figure_intensity.layout)
        # print("Currently plotted data:", self.figure_intensity.layout.title)
        # print("Currently plotted data:", self.figure_intensity.layout.images)
        # print("number of images:", len(self.figure_intensity.layout.images))
        # for image in self.figure_intensity.layout.images:
        #    md5sum = hashlib.md5(image.source.encode('utf-8')).hexdigest()
        #    print("image source md5sum:", md5sum)
        # print("Currently plotted data:", self.figure_intensity.layout.images)
        # print(er, "update_figure")
        # self.figure.state.flush()  #

    def update_figure_uncertainty(self, figure_uncertainty: go.Figure) -> None:
        # debounce / re-entrancy guard
        now = time.time()
        if self._updating_uncertainty:
            return
        if now - self._last_uncertainty_time < self._min_interval_uncertainty:
            return
        self._updating_uncertainty = True
        try:
            self.figure_uncertainty.update(figure_uncertainty)
            # flush view state; keep guarded to avoid feedback loops
            self.figure_uncertainty.state.flush()
            self._last_uncertainty_time = now
            logger.debug("============================================================================================")
            logger.debug("update_figure_uncertainty")
            logger.debug("============================================================================================")
        finally:
            self._updating_uncertainty = False
        # print("Currently plotted data:", self.figure.data)
        # print("Currently plotted data:", self.figure.layout)
        # print(er, "update_figure")
        # self.figure.state.flush()  #
        ##print("figure info:", figure)
        ##print("figure data:", figure.data)
        ##print("figure layout:", figure.layout)
        # print("figure layout title:", figure.layout.title)
        ##print("figure layout image:", figure.layout.images)
        # print("number of images:", len(figure.layout.images))
        # for image in figure.layout.images:
        #    md5sum = hashlib.md5(image.source.encode('utf-8')).hexdigest()
        #    print("image source md5sum:", md5sum)

        #    #vuetify.VCard(
        #    #    vuetify.VCardTitle("Temporal Analysis"),
        #    #    vuetify.VCardText("Content for Temporal Analysis tab goes here."),
        #    #    #go.Figure(id="temporal_plot"),
        #    #    go.Scatter(x=x_data, y=y_data, mode='lines+markers')
        #    #)

    # def update_plot(self):
    #    x_data, y_data = temporal_data_analysis()
    #    fig = go.Figure(data=[go.Scatter(x=x_data, y=y_data, mode='lines+markers')])
    #    self.view_model.server.state.temporal_plot = fig
    #    self.view_model.server.state.flush()
    #    self.view_model.server.state.add_callback("update_plot", self.update_plot)
    #    time.sleep(10)
