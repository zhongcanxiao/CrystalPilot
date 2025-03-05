
import plotly.graph_objects as go
from nova.trame.view.components import InputField
from nova.trame.view.layouts import GridLayout, HBoxLayout
from trame.widgets import plotly

from typing import List, Dict
from nova.trame.view.components import InputField,RemoteFileInput
from ..view_models.main import MainViewModel
from nova.trame.view.layouts import GridLayout, HBoxLayout
from trame.widgets import vuetify3 as vuetify


from ..view_models.main import MainViewModel

from trame.widgets import html

class NewTabTemplateView:
    """View class for Plotly."""

    def __init__(self, view_model: MainViewModel) -> None:
        self.view_model = view_model
        self.view_model.newtabtemplate_bind.connect("model_newtabtemplate")
        self.view_model.newtabtemplate_updatefig_bind.connect(self.update_figure)
        self.create_ui()


    def create_ui(self) -> None:
        with GridLayout(columns=4, classes="mb-2"):
            InputField(v_model="model_newtabtemplate.plot_type", items="model_newtabtemplate.plot_type_options", type="select")
            InputField(v_model="model_newtabtemplate.x_axis", items="model_newtabtemplate.axis_options", type="select")
            InputField(v_model="model_newtabtemplate.y_axis", items="model_newtabtemplate.axis_options", type="select")
            InputField(
                v_model="model_newtabtemplate.z_axis",
                disabled=("model_newtabtemplate.is_not_heatmap",),
                items="model_newtabtemplate.axis_options",
                type="select",
            )
        with HBoxLayout(halign="center", height="50vh"):
            self.figure = plotly.Figure()

    def update_figure(self, figure: go.Figure) -> None:
        self.figure.update(figure)
        self.figure.state.flush()  # 