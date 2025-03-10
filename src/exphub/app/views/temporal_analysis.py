"""Module for the Temporal Analysis tab."""

import time
from nova.trame.view.components import InputField, RemoteFileInput
from trame.widgets import vuetify3 as vuetify
from nova.trame.view.layouts import GridLayout, HBoxLayout
from ..view_models.main import MainViewModel

import plotly.graph_objects as go
from PIL import Image
from trame.widgets import html
from trame.widgets import plotly
import hashlib

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
        self.view_model.temporalanalysis_updatefigure_intensity_bind.connect(self.update_figure_intensity)
        self.view_model.temporalanalysis_updatefigure_uncertainty_bind.connect(self.update_figure_uncertainty)
        self.create_ui()

    def create_ui(self) -> None:
        x_data, y_data = temporal_data_analysis()
        #with vuetify.VContainer(fluid=True, classes="pa-5"):
        #        vuetify.VCardTitle("Temporal Analysis"),
        #        vuetify.VCardText("Content for Temporal Analysis tab goes here."),
        with GridLayout(columns=1, classes="mb-2"):
            InputField(v_model="model_temporalanalysis.prediction_model_type", items="model_temporalanalysis.prediction_model_type_options", type="select")
        #with GridLayout(columns=4, classes="mb-2"):
            #InputField(v_model="model_cssstatus.plot_type", items="model_cssstatus.plot_type_options", type="select")
            #InputField(v_model="model_cssstatus.x_axis", items="model_cssstatus.axis_options", type="select")
            #InputField(v_model="model_cssstatus.y_axis", items="model_cssstatus.axis_options", type="select")
            #InputField(
            #    v_model="model_cssstatus.z_axis",
            #    disabled=("model_cssstatus.is_not_heatmap",),
            #    items="model_cssstatus.axis_options",
            #    type="select",
            #)
        with GridLayout(columns=1):
            InputField(
                v_model="model_temporalanalysis.time_interval",
            )
        with GridLayout(columns=2, classes="mb-2"):
            with HBoxLayout(halign="center", height="50vh"):
                vuetify.VCardTitle("Prediction of Intensity"),
                self.figure_intensity = plotly.Figure()
            with HBoxLayout(halign="center", height="50vh"):
                vuetify.VCardTitle("Prediction of Uncertainty"),
                self.figure_uncertainty = plotly.Figure()
            
        vuetify.VBtn("Auto Update", click=self.view_model.create_auto_update_temporalanalysis_figure)


    def update_figure_intensity(self, figure_intensity: go.Figure) -> None:
        self.figure_intensity.update(figure_intensity)
        self.figure_intensity.state.flush()
        print("============================================================================================")
        print("update_figure_intensity")
        print("============================================================================================")
        #print("Currently plotted data:", self.figure_intensity.data)
        #print("Currently plotted data:", self.figure_intensity.layout)
        #print("Currently plotted data:", self.figure_intensity.layout.title)
        #print("Currently plotted data:", self.figure_intensity.layout.images)
        #print("number of images:", len(self.figure_intensity.layout.images))
        #for image in self.figure_intensity.layout.images:
        #    md5sum = hashlib.md5(image.source.encode('utf-8')).hexdigest()
        #    print("image source md5sum:", md5sum)
        #print("Currently plotted data:", self.figure_intensity.layout.images)     
        #print(er, "update_figure")
        #self.figure.state.flush()  # 
    def update_figure_uncertainty(self,figure_uncertainty:go.Figure) -> None:
        self.figure_uncertainty.update(figure_uncertainty)
        self.figure_uncertainty.state.flush()
        print("============================================================================================")
        print("update_figure_uncertainty")
        print("============================================================================================")
        #print("Currently plotted data:", self.figure.data)
        #print("Currently plotted data:", self.figure.layout)
        #print(er, "update_figure")
        #self.figure.state.flush()  # 
        ##print("figure info:", figure)
        ##print("figure data:", figure.data)
        ##print("figure layout:", figure.layout)
        #print("figure layout title:", figure.layout.title)
        ##print("figure layout image:", figure.layout.images)
        #print("number of images:", len(figure.layout.images))
        #for image in figure.layout.images:
        #    md5sum = hashlib.md5(image.source.encode('utf-8')).hexdigest()
        #    print("image source md5sum:", md5sum)
 

        #    #vuetify.VCard(
        #    #    vuetify.VCardTitle("Temporal Analysis"),
        #    #    vuetify.VCardText("Content for Temporal Analysis tab goes here."),
        #    #    #go.Figure(id="temporal_plot"),
        #    #    go.Scatter(x=x_data, y=y_data, mode='lines+markers')
        #    #)

    #def update_plot(self):
    #    x_data, y_data = temporal_data_analysis()
    #    fig = go.Figure(data=[go.Scatter(x=x_data, y=y_data, mode='lines+markers')])
    #    self.view_model.server.state.temporal_plot = fig
    #    self.view_model.server.state.flush()
    #    self.view_model.server.state.add_callback("update_plot", self.update_plot)
    #    time.sleep(10)