"""SANS I(Q) reduction / live tab view (P4.2 placeholder).

Occupies the LIVE tab slot (the SANS analogue of the single-crystal Temporal
Analysis / live-data tab). Where single-crystal runs a Mantid live-reduction
loop producing per-peak intensity time-series, SANS would reduce to an
azimuthally-averaged I(Q). That pipeline is TBD with the SANS scientist (see
``DECISION DEFAULTS`` in the P4 task brief), so this view renders:

  - a small Q-range / binning form (carried on the model so the UI has
    something to edit; no pipeline reads it yet)
  - the prediction-model dropdown pinned to ``"TBD"``
  - a placeholder I(Q) figure (log-log frame with a "reduction pipeline TBD"
    annotation) pushed from the steering VM's ``iqreduction_updatefig_bind``

Binds the I(Q) reduction model under the ``model_iqreduction`` namespace.
"""

from nova.trame.view.components import InputField
from nova.trame.view.layouts import GridLayout, HBoxLayout, VBoxLayout
from trame.widgets import plotly
from trame.widgets import vuetify3 as vuetify

from ..view_models.steering import SansSteeringViewModel


class SansIQReductionView:
    """View class to render the SANS I(Q) reduction (live) tab placeholder."""

    def __init__(self, view_model: SansSteeringViewModel) -> None:
        self.view_model = view_model
        self.view_model.iqreduction_bind.connect("model_iqreduction")
        self.view_model.iqreduction_updatefig_bind.connect(self.update_figure_iq)
        self.create_ui()

    def create_ui(self) -> None:
        with VBoxLayout(gap="0.5em"):
            vuetify.VAlert(
                "SANS I(Q) reduction pipeline is not yet wired. The controls "
                "below are placeholders; the reduction model stays 'TBD' until "
                "the SANS reduction workflow is specified.",
                type="info",
                variant="tonal",
                density="compact",
            )
            with GridLayout(columns=2, gap="0.5em"):
                InputField(
                    v_model="model_iqreduction.prediction_model",
                    items="model_iqreduction.prediction_model_options",
                    type="select",
                    label="Reduction / Prediction Model",
                )
            # Placeholder I(Q) figure. Seeded through the VM accessor (the view
            # never reaches into the model); refreshed via the figure-push bind.
            with HBoxLayout(halign="left", height="45vh"):
                self.figure_iq = plotly.Figure()
                self.figure_iq.update(self.view_model.get_iq_figure())

    def update_figure_iq(self, fig: object) -> None:
        self.figure_iq.update(fig)
        self.figure_iq.state.flush()
