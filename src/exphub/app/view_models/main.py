"""Module for the main ViewModel."""

from typing import Any, Dict
import time
from nova.mvvm.interface import BindingInterface


from ..models.main_model import MainModel
from ..models.angle_plan import AnglePlanModel
from ..models.experiment_info import ExperimentInfoModel
from ..models.eic_control import EICControlModel
from ..models.newtabtemplate import NewTabTemplateModel

#from ..models.plotly import PlotlyConfig
#from pyvista import Plotter  # just for typing
#from ..models.pyvista import PyVistaConfig

from trame.app.asynchronous import create_task
import asyncio

#from ..models.css_status import CSSStatusModel
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
        #self.temporalanalysis_bind = binding.new_bind(self.model.temporalanalysis, callback_after_update=self.change_callback)
        self.temporalanalysis_bind = binding.new_bind(self.model.temporalanalysis, callback_after_update=self.update_temporalanalysis_figure)

        #self.cssstatus_bind = binding.new_bind(self.model.cssstatus, callback_after_update=self.change_callback)
        self.cssstatus_bind = binding.new_bind(self.model.cssstatus, callback_after_update=self.update_cssstatus_figure)
        self.cssstatus_updatefig_bind = binding.new_bind()
        self.temporalanalysis_updatefigure_uncertainty_bind = binding.new_bind()
        self.temporalanalysis_updatefigure_intensity_bind = binding.new_bind()
######################################################################################################################################################
# wrong
#        self.newtabtemplate_bind = binding.new_bind(self.model.newtabtemplate, callback_after_update=self.change_callback)
#        self.newtabtemplate_updatefig_bind = binding.new_bind(self.model.newtabtemplate, callback_after_update=self.update_newtabtemplate_figure)
######################################################################################################################################################
        self.newtabtemplate_bind = binding.new_bind(self.model.newtabtemplate,
                                                callback_after_update=self.update_newtabtemplate_figure)
        self.newtabtemplate_updatefig_bind = binding.new_bind()
######################################################################################################################################################

        #self.pyvista_config = PyVistaConfig()

        #self.plotly_config_bind = binding.new_bind(
        #    linked_object=self.plotly_config, callback_after_update=self.update_plotly_figure
        #)
        #self.plotly_figure_bind = binding.new_bind(linked_object=self.plotly_config)
        #self.pyvista_config_bind = binding.new_bind(linked_object=self.pyvista_config)


        #self.create_auto_update_cssstatus_figure()





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
        self.cssstatus_bind.update_in_view(self.model.cssstatus)
######################################################################################################################################################
        self.newtabtemplate_bind.update_in_view(self.model.newtabtemplate)
######################################################################################################################################################
        #print(self.model.angleplan.test_list)

    def submit_angle_plan(self) -> None:
        #print("submit_angle_plan")
        self.model.eiccontrol.submit_eic(self.model.angleplan.angle_list)
        self.update_view()

    def call_load_token(self) -> None:
        self.model.eiccontrol.load_token(self.model.eiccontrol.token_file)
        self.update_view()
#
#
#    def update_pyvista_volume(self, plotter: Plotter) -> None:
#        self.pyvista_config.render(plotter)
#
#    def update_plotly_figure(self, _: Any = None) -> None:
#        self.plotly_config_bind.update_in_view(self.plotly_config)
#        self.plotly_figure_bind.update_in_view(self.plotly_config.get_figure())
#

    def update_cssstatus_figure(self, _: Any = None) -> None:
        self.cssstatus_bind.update_in_view(self.model.cssstatus)
        self.cssstatus_updatefig_bind.update_in_view(self.model.cssstatus.get_figure())
        #time.sleep(7)

    async def auto_update_cssstatus_figure(self) -> None:
        while True:
            self.update_cssstatus_figure()
            await asyncio.sleep(1)

    def create_auto_update_cssstatus_figure(self) -> None:
        asyncio.create_task(self.auto_update_cssstatus_figure())        


 
    def update_temporalanalysis_figure(self, _: Any = None) -> None:
        self.temporalanalysis_bind.update_in_view(self.model.temporalanalysis)
        #self.temporalanalysis_updatefig_bind.update_in_view(self.model.temporalanalysis.get_figure_intensity(),self.model.temporalanalysis.get_figure_uncertainty())
        self.temporalanalysis_updatefigure_intensity_bind.update_in_view(self.model.temporalanalysis.get_figure_intensity())
        self.temporalanalysis_updatefigure_uncertainty_bind.update_in_view(self.model.temporalanalysis.get_figure_uncertainty())
        #time.sleep(7)

    async def auto_update_temporalanalysis_figure(self) -> None:
        while True:
            self.update_temporalanalysis_figure()
            await asyncio.sleep(1)

    def create_auto_update_temporalanalysis_figure(self) -> None:
        self.model.temporalanalysis.start_reading_live_mtd_data()
        asyncio.create_task(self.get_live_mtd_data()) 
        asyncio.create_task(self.auto_update_temporalanalysis_figure()) 


    def get_live_mtd_data(self) -> None:
        while True:
            self.model.temporalanalysis.mtd_workflow.live_data_reduction()
            asyncio.sleep(10)
        


    def update_newtabtemplate_figure(self, _: Any = None) -> None:
        self.newtabtemplate_bind.update_in_view(self.model.newtabtemplate)
        self.newtabtemplate_updatefig_bind.update_in_view(self.model.newtabtemplate.get_figure())
