"""Module for the Temporal Analysis tab."""

import time
from nova.trame.view.components import InputField, RemoteFileInput
from trame.widgets import vuetify3 as vuetify
from nova.trame.view.layouts import GridLayout, HBoxLayout
from ..view_models.main import MainViewModel

import plotly.graph_objects as go

def temporal_data_analysis():
    # Dummy data generation for the plot
    x_data = list(range(10))
    y_data = [i**2 for i in x_data]
    return x_data, y_data

class TemporalAnalysisView:
    """View class to render the Temporal Analysis tab."""

    def __init__(self,view_model:MainViewModel) -> None:
        self.view_model = view_model
        self.view_model.temporalanalysis_bind.connect("model_temporalanalysis")
        self.create_ui()

    def create_ui(self) -> None:
        x_data, y_data = temporal_data_analysis()
        with vuetify.VContainer(fluid=True, classes="pa-5"):
                vuetify.VCardTitle("Temporal Analysis"),
                vuetify.VCardText("Content for Temporal Analysis tab goes here."),
            #vuetify.VCard(
            #    vuetify.VCardTitle("Temporal Analysis"),
            #    vuetify.VCardText("Content for Temporal Analysis tab goes here."),
            #    #go.Figure(id="temporal_plot"),
            #    go.Scatter(x=x_data, y=y_data, mode='lines+markers')
            #)

    #def update_plot(self):
    #    x_data, y_data = temporal_data_analysis()
    #    fig = go.Figure(data=[go.Scatter(x=x_data, y=y_data, mode='lines+markers')])
    #    self.view_model.server.state.temporal_plot = fig
    #    self.view_model.server.state.flush()
    #    self.view_model.server.state.add_callback("update_plot", self.update_plot)
    #    time.sleep(10)