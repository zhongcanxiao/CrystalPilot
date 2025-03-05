"""Module for the main model."""

from pydantic import BaseModel, Field
from .angle_plan import AnglePlanModel
from .eic_control import EICControlModel
from .experiment_info import ExperimentInfoModel
from .css_status import CSSStatusModel
from .temporal_analysis import TemporalAnalysisModel

from .newtabtemplate import NewTabTemplateModel 


class MainModel(BaseModel):
    """
    A model class.

    This class uses Pydantic (https://docs.pydantic.dev/latest/),
    which allows for defining data validation rules,
    titles, descriptions, and examples that can be used in GUI elements or
    other interfaces for improved clarity and usability.
    """

    username: str = Field(
    default="test_name",
        min_length=1,
        title="User Name",
        description="Please provide the name of the user",
        examples=["user"],
    )
    password: str = Field(default="test_password", title="User Password")
    angleplan: AnglePlanModel = Field(default_factory=AnglePlanModel, title="Angle Plan")
    eiccontrol: EICControlModel = Field(default_factory=EICControlModel, title="EIC Control")
    experimentinfo: ExperimentInfoModel = Field(default_factory=ExperimentInfoModel, title="Experiment Info")
    cssstatus: CSSStatusModel = Field(default_factory=CSSStatusModel, title="CSS Status")
    temporalanalysis: TemporalAnalysisModel = Field(default_factory=TemporalAnalysisModel, title="Temporal Analysis")

    newtabtemplate: NewTabTemplateModel = Field(default_factory=NewTabTemplateModel, title="New Tab Template")
    #plotly: PlotlyModel = Field(default_factory=PlotlyModel, title="Plotly")