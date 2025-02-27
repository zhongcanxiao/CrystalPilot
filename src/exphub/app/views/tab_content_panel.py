"""Module for the Tab Content panel."""

from trame.widgets import vuetify3 as vuetify
from trame_server import Server

from ..view_models.main import MainViewModel
from .temporal_analysis import TemporalAnalysisView  # Import the new view
from .angle_plan import AnglePlanView
from .eic_control import EICControlView
from .ccs_status import CCSStatusView
from .experiment_info import ExperimentInfoView


class TabContentPanel:
    """View class to render content for a selected tab."""

    def __init__(self, server: Server, view_model: MainViewModel) -> None:
        self.view_model = view_model
        self.server = server
        self.ctrl = server.controller
        self.create_ui()

    def create_ui(self) -> None:
        with vuetify.VForm(ref="form") as self.f:
            with vuetify.VContainer(classes="pa-0", fluid=True):
                with vuetify.VCard():
                    with vuetify.VWindow(v_model="active_tab"):
                        with vuetify.VWindowItem(value=1):
                            ExperimentInfoView(self.view_model)
                        with vuetify.VWindowItem(value=2):
                            TemporalAnalysisView(self.view_model)
                        with vuetify.VWindowItem(value=3):
                            AnglePlanView(self.view_model)
                        with vuetify.VWindowItem(value=4):
                            EICControlView(self.view_model)
                        with vuetify.VWindowItem(value=5):
                            CCSStatusView(self.view_model)
            with vuetify.VCardActions():
                vuetify.VBtn("Data Visualization", click=self.open_data_visualization)
                vuetify.VBtn("Data Reduction", click=self.open_data_reduction)
                vuetify.VBtn("Structure Analysis", click=self.open_data_refinement)
                #vuetify.VBtn("Data Visualization", click=self.open_data_visualization)
                #vuetify.VBtn("Data Reduction", click=self.open_data_reduction)
                #vuetify.VBtn("Data Refinement", click=self.open_data_refinement)

    def open_data_visualization() -> None:
        """Open the Data Visualization tab."""
        print("Open Data Visualization tab")
    def open_data_reduction() -> None:
        """Open the Data Reduction tab."""
        print("Open Data Reduction tab")
    def open_data_refinement() -> None:
        """Open the Data Refinement tab."""
        print("Open Data Refinement tab")
        