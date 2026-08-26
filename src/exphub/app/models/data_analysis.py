"""Model for data analysis."""

import plotly.graph_objects as go
from plotly.data import iris
from pydantic import BaseModel, Field, computed_field

IRIS_DATA = iris()


class DataAnalysisModel(BaseModel):
    """Configuration class for the Plotly example."""

    output_dir: str = Field(default="/SNS/TOPAZ/IPTS-12345/shared/", title="Output Directory")
    data_dir: str = Field(default="/SNS/TOPAZ/IPTS-12345/shared/", title="Data Directory")
    output_dir_nxv: str = Field(default="/SNS/TOPAZ/IPTS-12345/shared/nxv/", title="Output Directory for NeuXtalViz")
    output_dir_olex2: str = Field(default="/SNS/TOPAZ/IPTS-12345/shared/olex2/", title="Output Directory for Olex2")
    output_dir_shelx: str = Field(default="/SNS/TOPAZ/IPTS-12345/shared/shelx/", title="Output Directory for ShelX")
    output_dir_discus: str = Field(default="/SNS/TOPAZ/IPTS-12345/shared/discus/", title="Output Directory for Discus")
    output_dir_reduction: str = Field(
        default="/SNS/TOPAZ/IPTS-12345/shared/reduction/", title="Output Directory for Reduction"
    )

    axis_options: list[str] = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
    x_axis: str = Field(default="sepal_length", title="X Axis")
    y_axis: str = Field(default="sepal_width", title="Y Axis")
    z_axis: str = Field(default="petal_length", title="Color")
    plot_type: str = Field(default="scatter", title="Plot Type")
    plot_type_options: list[str] = ["heatmap", "scatter"]

    @computed_field  # type: ignore
    @property
    def is_not_heatmap(self) -> bool:
        return self.plot_type != "heatmap"

    def get_figure(self) -> go.Figure:
        match self.plot_type:
            case "heatmap":
                plot_data = go.Heatmap(
                    x=IRIS_DATA[self.x_axis].tolist(),
                    y=IRIS_DATA[self.y_axis].tolist(),
                    z=IRIS_DATA[self.z_axis].tolist(),
                )

            case "scatter":
                plot_data = go.Scatter(
                    x=IRIS_DATA[self.x_axis].tolist(), y=IRIS_DATA[self.y_axis].tolist(), mode="markers"
                )
            case _:
                raise ValueError(f"Invalid plot type: {self.plot_type}")

        figure = go.Figure(plot_data)
        figure.update_layout(
            title={"text": f"{self.plot_type}"},
            xaxis={"title": {"text": self.x_axis}},
            yaxis={"title": {"text": self.y_axis}},
        )

        return figure

    def set_ipts_number(self, ipts_number: str) -> None:
        self.output_dir = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/"
        self.data_dir = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/"
        self.output_dir_nxv = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/nxv/"
        self.output_dir_olex2 = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/olex2/"
        self.output_dir_shelx = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/shelx/"
        self.output_dir_discus = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/discus/"
        self.output_dir_reduction = f"/SNS/TOPAZ/IPTS-{ipts_number}/shared/reduction/"
