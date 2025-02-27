"""Module for the Tab panel."""

from trame.widgets import vuetify3 as vuetify

from ..view_models.main import MainViewModel


class TabsPanel:
    """View class to render tabs."""

    def __init__(self, view_model: MainViewModel):
        #self.view_model = view_model
        #self.view_model.model_bind.connect("config")
        self.create_ui()

    def create_ui(self) -> None:
        with vuetify.VTabs(v_model=("active_tab", 0), classes="pl-5"):
            vuetify.VTab("IPTS Info",           value=1)  # New tab for CCS Status
            vuetify.VTab("Live Data",           value=2)  # New tab for CCS Status
            vuetify.VTab("Experiment Plan",     value=3)
            vuetify.VTab("EIC Control",         value=4)
            vuetify.VTab("Instrument Status",   value=5)  # New tab for CCS Status