"""Module for the System tab."""

from trame.widgets import vuetify3 as vuetify


from nova.trame.view.components import InputField
from nova.trame.view.layouts import GridLayout

class ExperimentInfoView:
    """View class to render the System tab."""

    def __init__(self, view_model):
        self.view_model = view_model
        self.create_ui()

    def create_ui(self) -> None:


        with GridLayout():
            InputField(
                v_model="config.instrument",
                items="config.options.instrument_list",
                type="select",
            )
            InputField(v_model="config.expName")
            InputField(v_model="config.molecularFormula")
            InputField(v_model="config.Z", type="number")
            InputField(v_model="config.unitCellVolume", type="number")
            InputField(v_model="config.sampleRadius", type="number")
            InputField(
                v_model="config.crystalsystem",
                items="config.options.crystalsystem_list",
                type="select",
            )
            InputField(
                v_model="config.pointGroup",
                items="config.options.pointGroup_list",
                type="select",
            )
            InputField(
                v_model="config.centering",
                items="config.options.centering_list",
                type="select",
            )
    def save_settings(self):
        # Placeholder function to handle saving settings
        print("Settings saved")