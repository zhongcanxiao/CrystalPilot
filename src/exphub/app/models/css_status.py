from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from typing import List, Dict
import csv
from nova.trame.view.components import InputField, RemoteFileInput
from trame.widgets import vuetify3 as vuetify
from nova.trame.view.layouts import GridLayout, HBoxLayout

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
from PIL import Image
import plotly.graph_objects as go
from nova.trame.view.components import InputField
from nova.trame.view.layouts import GridLayout, HBoxLayout
from trame.widgets import plotly
import io
from plotly.data import iris
IRIS_DATA = iris()


bl12cssstatus_urlsrc="https://status.sns.ornl.gov/dbwr/view.jsp?display=https%3A//webopi.sns.gov/bl12/files/bl12/opi/BL12_ADnED_2D_4x4.bob&macros=%7B%26quot%3BDET1%26quot%3B%3A%26quot%3BMain%20Detector%26quot%3B%2C%26quot%3BDET2%26quot%3B%3A%26quot%3BMain%20d-Space%26quot%3B%2C%26quot%3BDET3%26quot%3B%3A%26quot%3BMain%20q-Space%26quot%3B%2C%26quot%3BDET4%26quot%3B%3A%26quot%3BMain%204x4%20and%20ROI%20d-Space%26quot%3B%2C%26quot%3BDET5%26quot%3B%3A%26quot%3BMain%20ROI%20q-Space%26quot%3B%2C%26quot%3BIOCSTATS%26quot%3B%3A%26quot%3BBL12%3ACS%3AADnED%3A%26quot%3B%2C%26quot%3BP%26quot%3B%3A%26quot%3BBL12%3ADet%3A%26quot%3B%2C%26quot%3BR%26quot%3B%3A%26quot%3BN1%3A%26quot%3B%2C%26quot%3BTAB%26quot%3B%3A%26quot%3BMain%20Detector%26quot%3B%2C%26quot%3BTOPR%26quot%3B%3A%26quot%3BN1%3A%26quot%3B%2C%26quot%3BBL%26quot%3B%3A%26quot%3BBL12%26quot%3B%2C%26quot%3BDID%26quot%3B%3A%26quot%3BDID305%26quot%3B%2C%26quot%3BS%26quot%3B%3A%26quot%3BBL12%26quot%3B%7D"
def save_webpage_as_image(url, output_file="webpage.png"):
    # Configure headless Chrome browser
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Start browser and load page
    browser = webdriver.Chrome(options=options)
    browser.get(url)
    
    # Take screenshot and save it
    time.sleep(0.4)
    screenshot = browser.get_screenshot_as_png()
    with open(output_file, "wb") as file:
        file.write(screenshot)
    print(f"Screenshot saved to {output_file}")
    
    # Close browser
    
    return screenshot


save_webpage_as_image(bl12cssstatus_urlsrc)

class CSSStatusModel(BaseModel):
    headers: List[str] = Field(default=["Title", "Comment", "phi", "omega", "Wait For", "Value", "Or Time"])
    #headers: List[str] = Field(default=["Title", "Comment", "BL12:Mot:goniokm:phi", "BL12:Mot:goniokm:omega", "Wait For", "Value", "Or Time"])
    table_test: List[Dict] = Field(default=[{"title":"1","header":"h"}])
    angle_list: List[Dict] = Field(default=[{"Title":"test_angleplan_1",
                                             "Comment":"",
                                             "BL12:Mot:goniokm:phi":0,
                                             "BL12:Mot:goniokm:omega":0,
                                             "Wait For":"PCharge",
                                             "Value":10,
    }])
    plan_file: str = Field(default="angle_plan.csv")
    plan_file_list: List[str] = Field(default=["angle_plan.csv"])

    axis_options: list[str] = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
    x_axis: str = Field(default="sepal_length", title="X Axis")
    y_axis: str = Field(default="sepal_width", title="Y Axis")
    z_axis: str = Field(default="petal_length", title="Color")
    plot_type: str = Field(default="Detector", title="Plot Type")
    #plot_type: str = Field(default="Preview", title="Plot Type")
    #plot_type_options: list[str] = ["heatmap", "scatter"]
    plot_type_options: list[str] = ["Detector", "D-space"]
    #plot_type_options: list[str] = ["Detector", "D-space", "Q-space", "4x4 and ROI D-space", "ROI Q-space", "IOCSTATS", "Det", "N1", "Main Detector", "N1", "BL12", "DID", "S"]
    #fig: go.Figure = Field(default=go.Figure(), title="Figure")

    #@computed_field  # type: ignore
    #@property
    #def get_css_status(self) -> str:
    timestamp: float=Field(default=0.0,title="timestamp")

    def is_not_heatmap(self) -> bool:
        match self.plot_type:
            case "heatmap":
                return False
            case _:
                return True
    def get_figure(self) -> go.Figure:
        screenshot = save_webpage_as_image(bl12cssstatus_urlsrc)
        image = Image.open(io.BytesIO(screenshot))
        width, height = image.size
        timestamp = time.time()
        #self.timestamp = timestamp
        print("genratged fig md5sum:" + str(hash(image.tobytes())))
        match self.plot_type:
            case "Detector":
                cropscreen = image.crop((0, 0, int(width*0.7), int(height *0.457)))
            case "D-space":
                cropscreen = image.crop((0, int(height *0.457), int(width*0.7), int(height *1.000)))
        screenshot = io.BytesIO()
        cropscreen.save(screenshot, format="PNG")
        screenshot = screenshot.getvalue()
        image = Image.open(io.BytesIO(screenshot))
        print("genratged fig md5sum:" + str(hash(image.tobytes())))


        fig = go.Figure()
        fig.add_layout_image(
            dict(
                source=image,
                xref="paper", yref="paper",
                x=0, y=1,
                sizex=1, sizey=1,
                xanchor="left", yanchor="top"
            )
        )
        fig.update_layout(
            title="CSS Status: "+str(time.time()),
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        print("get plotly figure done") 
        return fig
    def is_not_heatmap(self) -> bool:
        return self.plot_type != "heatmap"
    def get_figure_0(self) -> go.Figure:
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
