"""Module for the Sample Tab 2."""

from nova.trame.view.components import InputField, RemoteFileInput
from trame.widgets import vuetify3 as vuetify
from nova.trame.view.layouts import GridLayout, HBoxLayout
from ..view_models.main import MainViewModel



# In your View setup
class EICControlView:
    """Sample tab 2 view class. Renders text input for user password."""

    def __init__(self,view_model:MainViewModel) -> None:
        self.view_model = view_model
        self.view_model.eiccontrol_bind.connect("model_eiccontrol")
        self.create_ui()

    def create_ui(self) -> None:
        RemoteFileInput(v_model="model_eiccontrol.token_file", base_paths=["/HFIR", "/SNS"])
        with GridLayout(columns=1):
            vuetify.VBtn("Authenticate", click=self.view_model.call_load_token)
        InputField(v_model="model_eiccontrol.is_simulation", type="checkbox")
        InputField(v_model="model_eiccontrol.IPTS_number")
        InputField(v_model="model_eiccontrol.instrument_name")
        with GridLayout(columns=1):
            vuetify.VBtn("Submit through EIC", click=self.view_model.submit_angle_plan)


        with GridLayout(columns=1):
            vuetify.VBanner(
                    v_if="model_eiccontrol.eic_submission_success",
                    text="Submission Successful.",
                    #text="Submission Successful. Scan ID: {{model_eiccontrol.eic_submission_scan_id}}, Message: {{model_eiccontrol.eic_submission_message}}",
                    color="success",
                )
