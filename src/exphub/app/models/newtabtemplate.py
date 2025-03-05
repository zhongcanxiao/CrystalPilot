from typing import List, Dict
import plotly.graph_objects as go
from plotly.data import iris
from pydantic import BaseModel, Field, computed_field

IRIS_DATA = iris()

class NewTabTemplateModel(BaseModel):
    """Configuration class for the Plotly example."""

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
                    z=IRIS_DATA[self.z_axis].tolist()
                )
                
            case "scatter":
                plot_data = go.Scatter(
                    x=IRIS_DATA[self.x_axis].tolist(),
                    y=IRIS_DATA[self.y_axis].tolist(),
                    mode="markers"
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