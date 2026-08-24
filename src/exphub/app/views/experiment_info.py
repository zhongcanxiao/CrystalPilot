"""Module for the System tab."""

from nova.trame.view.components import InputField, RemoteFileInput
from nova.trame.view.layouts import GridLayout

from ..view_models.main import MainViewModel


class ExperimentInfoView:
    """View class to render the System tab."""

    def __init__(self, view_model: MainViewModel) -> None:
        self.view_model = view_model

        self.view_model.experimentinfo_bind.connect("config")
        self.create_ui()

    def create_ui(self) -> None:
        with GridLayout(columns=2, gap="0.5em"):
            InputField(v_model="config.exp_name")
            InputField(v_model="config.ipts_number")
            InputField(v_model="config.instrument", items="config.options.instrument_list", type="select")
            InputField(v_model="config.molecular_formula")
        with GridLayout(columns=3, gap="0.5em"):
            InputField(v_model="config.crystalsystem", items="config.options.crystalsystem_list", type="select")
            InputField(v_model="config.point_group", items="config.options.point_group_list", type="select")
            InputField(v_model="config.centering", items="config.options.centering_list", type="select")
        with GridLayout(columns=2, gap="0.5em"):
            RemoteFileInput(v_model="config.UBFileName", base_paths=["/HFIR", "/SNS"])
            RemoteFileInput(v_model="config.cal_filename", base_paths=["/HFIR", "/SNS"])
            InputField(v_model="config.min_dspacing")
            InputField(v_model="config.max_dspacing")

    def save_settings(self) -> None:
        # Placeholder function to handle saving settings
        print("Settings saved")
