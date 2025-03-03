"""Module for the main ViewModel."""

from typing import Any, Dict
from nova.mvvm.interface import BindingInterface


from ..models.main_model import MainModel
from ..models.angle_plan import AnglePlanModel
from ..models.experiment_info import ExperimentInfoModel
from ..models.eic_control import EICControlModel
#from ..models.ccs_status import CCSStatusModel
#from ..models.temporal_analysis import TemporalAnalysisModel    



class MainViewModel:
    """Viewmodel class, used to create data<->view binding and react on changes from GUI."""

    def __init__(self, model: MainModel, binding: BindingInterface):
        self.model = model
        #self.angleplan = AnglePlanModel()

        # here we create a bind that connects ViewModel with View. It returns a communicator object,
        # that allows to update View from ViewModel (by calling update_view).
        # self.model will be updated automatically on changes of connected fields in View,
        # but one also can provide a callback function if they want to react to those events
        # and/or process errors.
        self.model_bind = binding.new_bind(self.model, callback_after_update=self.change_callback)
        self.experimentinfo_bind = binding.new_bind(self.model.experimentinfo, callback_after_update=self.change_callback)
        self.angleplan_bind = binding.new_bind(self.model.angleplan, callback_after_update=self.change_callback)
        self.eiccontrol_bind = binding.new_bind(self.model.eiccontrol, callback_after_update=self.change_callback)



    def change_callback(self, results: Dict[str, Any]) -> None:
        if results["error"]:
            print(f"error in fields {results['errored']}, model not changed")
        else:
            print(f"model fields updated: {results['updated']}")

    def update_view(self) -> None:
        #self.model_bind.update_in_view(self.model)
        self.model.angleplan.load_ap(self.model.angleplan.plan_file)
        self.angleplan_bind.update_in_view(self.model.angleplan)
        self.eiccontrol_bind.update_in_view(self.model.eiccontrol)
        print(self.model.angleplan.test_list)

    def submit_angle_plan(self) -> None:
        #print("submit_angle_plan")
        self.model.eiccontrol.submit_eic(self.model.angleplan.angle_list)
        self.update_view()

    def call_load_token(self) -> None:
        self.model.eiccontrol.load_token(self.model.eiccontrol.token_file)
        self.update_view()
