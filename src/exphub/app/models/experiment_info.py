"""Model for experiment info."""

import os
import re
import shlex
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator


class Options(BaseModel):
    """A class for the configuration options."""

    instrument_list: List[str] = Field(default=["TOPAZ", "MANDI", "CORELLI"])
    centering_list: List[str] = Field(default=[])
    crystalsystem_list: List[str] = Field(
        default=[
            "Triclinic",
            "Monoclinic",
            "Orthorhombic",
            "Tetragonal",
            "Trigonal/Rhombohedral",
            "Trigonal/Hexagonal",
            "Hexagonal",
            "Cubic",
        ]
    )
    point_group_list: List[str] = Field(default=[])
    hklaxes: List[str] = Field(default=["H", "K", "L"])


class ExperimentInfoModel(BaseModel):
    """A class for the configuration object."""

    molecular_formula: str = Field(default="", title="Molecular Formula")
    Z: float = Field(default=0.0, title="Z")
    unit_cell_volume: float = Field(default=0.0, title="Unit cell volume")
    sample_radius: float = Field(default=0.0, title="Sample radius(mm)")
    centering: str = Field(default="P", title="Centering")
    crystalsystem: str = Field(
        default="Cubic",
        title="Crystal system",
        description="unconventional crystal systems",
    )
    point_group: str = Field(default="23", title="Point group")

    instrument: str = Field(default="TOPAZ", title="Instrument Name")
    ipts_number: str = Field(
        default="12345", title="IPTS Number", min_length=1, description="Proposal number for the experiment"
    )
    run_nums: str = Field(
        default="", title="Run Numbers", description="Comma separated list of run numbers, support ranges like 1:10"
    )
    base_dir: str = Field(default=os.getcwd(), title="Base Directory")
    data_directory: str = Field(default=os.getcwd()[: os.getcwd().find("shared")] + "nexus", title="Data Directory")
    exp_name: str = Field(
        default="test",
        title="Experiment Name",
        description="Will be used to create a directory in the shared folder under the IPTS directory.",
    )
    cal_filename: str = Field(
        default="/SNS/TOPAZ/shared/calibrations/2025B/TOPAZ_2025B_AG_2-3BN_AG.DetCal",
        title="Calibration File",
        description="Calibration file for the current cycle.",
    )
    subtract_bkg: Optional[bool] = Field(default=False, title="Subtract Background")
    background_filename: Optional[str] = Field(
        default=None,
        title="Background File",
        description="NXS file for the background measurement of the current cycle.",
    )
    read_ub: Optional[bool] = Field(default=False, title="Read UB Matrix")
    UBFileName: Optional[str] = Field(
        # default="/home/zx5/1-todo/4-integrate/nxv/nxv-git-zhongcanxiao/src/TOPAZ_44752_Tetragonal.mat",
        default="",
        title="UB File",
        description="Optional UB matrix file.",
    )
    max_q: float = Field(default=17.0, title="maxQ")
    split_threshold: int = Field(default=80, title="Split Threshold")
    edge_pixels: int = Field(default=0, title="Edge Pixels")
    num_peaks_to_find: int = Field(default=500, title="Number of Peaks to Find")
    abc_min: float = Field(default=3, title="Shortest lattice parameter")
    abc_max: float = Field(default=18, title="Longest lattice parameter")
    tolerance: float = Field(default=0.12, title="Indexing tolerance", description="Tolerance for indexing peaks.")
    predict_peaks: Optional[bool] = Field(default=True, title="Predict Peaks")
    live: Optional[bool] = Field(default=False, title="Live Mode")
    mod_struct: Optional[bool] = Field(default=False, title="Plot modulated structure in one Unit Cell")
    pred_min_dspacing: float = Field(default=0.499, title="Minimum d-spacing predicted")
    pred_max_dspacing: float = Field(default=11.0, title="Maximum d-spacing predicted")

    @model_validator(mode="after")
    def validate_min_less_than_max_d(self) -> "ExperimentInfoModel":
        min_value = self.pred_min_dspacing
        max_value = self.pred_max_dspacing
        if min_value is not None and max_value is not None and min_value >= max_value:
            raise ValueError("min value must be less than max value for predicted D-spacing")
        return self

    pred_min_wavelength: float = Field(default=0.4, title="Minimum wavelength predicted")
    pred_max_wavelength: float = Field(default=3.45, title="Maximum wavelength predicted")

    @model_validator(mode="after")
    def validate_min_less_than_max_pwl(self) -> "ExperimentInfoModel":
        min_value = self.pred_min_wavelength
        max_value = self.pred_max_wavelength
        if min_value is not None and max_value is not None and min_value >= max_value:
            raise ValueError("min value must be less than max value for predicted wavelength")
        return self

    ellipse_size_specified: Optional[bool] = Field(default=True, title="Specify Size")
    peak_radius: float = Field(default=0.11, title="Peak radius", description="Radius of the peak")
    bkg_inner_radius: float = Field(
        default=0.115,
        title="Background inner radius",
        description="Inner radius of the background shell (currently support sphere)",
    )
    bkg_outer_radius: float = Field(
        default=0.14,
        title="Background outer radius",
        description="Outer radius of the background shell (currently support sphere)",
    )

    @model_validator(mode="after")
    def validate_inner_less_than_outer_bkg_r(self) -> "ExperimentInfoModel":
        min_value = self.bkg_inner_radius
        max_value = self.bkg_outer_radius
        if min_value is not None and max_value is not None and min_value >= max_value:
            raise ValueError("inner radius must be smaller than outer radius")
        return self

    spectra_filename: str = Field(
        default="/SNS/TOPAZ/shared/calibrations/2019A/Calibration/Spectrum_32751_32758.dat",
        title="Name of spectrum file",
        description="Spectrum file for the current cycle.",
    )
    norm_to_wavelength: float = Field(default=1.0, title="Normalize spectra to this wavelength")
    scale_factor: float = Field(default=0.05, title="Scale factor")
    min_intensity: float = Field(default=10, title="Minimum integrated intensity")
    min_isigi: float = Field(default=2.0, title="Minimum I/sigI")
    border_pixels: int = Field(default=18, title="Width of border in which peaks are rejected")
    min_dspacing: float = Field(default=0.5, title="Minimum D-Spacing")
    max_dspacing: float = Field(default=30.0, title="Maximum D-Spacing")
    min_wavelength: float = Field(default=0.4, title="Minimum wavelength")
    max_wavelength: float = Field(default=3.5, title="Maximum wavelength")

    def validate_min_less_than_max_wl(self) -> "ExperimentInfoModel":
        min_value = int(self.min_wavelength)
        max_value = int(self.max_wavelength)
        if min_value is not None and max_value is not None and min_value >= max_value:
            raise ValueError("min value must be less than max value for wavelength")
        return self

    z_score: float = Field(default=4.0, title="Minimum I/sig(I) ratio")
    starting_batch_number: int = Field(default=1, title="Starting batch number")

    # plotting_input: PlottingInputs = PlottingInputs()

    # _h1: str = Field(default="H")
    # _k1: str = Field(default="K")
    # _l1: str = Field(default="L")
    # _xmin1: str = Field(default="")
    # _xmax1: str = Field(default="")
    # _xsteps1: int = Field(default=400)
    # _ymin1: str = Field(default="")
    # _ymax1: str = Field(default="")
    # _ysteps1: int = Field(default=400)
    # _slice1: float = Field(default=0.0)
    # _thickness1: float = Field(default=0.1)
    # _zmin1: float = Field(default=-0.005)
    # _zmax1: float = Field(default=0.005)
    # _h2: str = Field(default="H")
    # _k2: str = Field(default="L")
    # _l2: str = Field(default="K")
    # _xmin2: str = Field(default="")
    # _xmax2: str = Field(default="")
    # _xsteps2: int = Field(default=400)
    # _ymin2: str = Field(default="")
    # _ymax2: str = Field(default="")
    # _ysteps2: int = Field(default=400)
    # _slice2: float = Field(default=0.0)
    # _thickness2: float = Field(default=0.1)
    # _zmin2: float = Field(default=-0.005)
    # _zmax2: float = Field(default=0.005)
    # _h3: str = Field(default="K")
    # _k3: str = Field(default="L")
    # _l3: str = Field(default="H")
    # _xmin3: str = Field(default="")
    # _xmax3: str = Field(default="")
    # _xsteps3: int = Field(default=400)
    # _ymin3: str = Field(default="")
    # _ymax3: str = Field(default="")
    # _ysteps3: int = Field(default=400)
    # _slice3: float = Field(default=0.0)
    # _thickness3: float = Field(default=0.1)
    # _zmin3: float = Field(default=-0.005)
    # _zmax3: float = Field(default=0.005)
    SAFile: str = Field(
        default="",
        title="Solid Angle File",
        description="Vanadium file for flux for this run cycle (for plotting only).",
    )
    FluxFile: str = Field(
        default="",
        title="Flux File",
        description="Vanadium file for solid angle for this run cycle (for plotting only).",
    )
    template_file: str = Field(
        default=str(Path(Path(__file__).parent, "../templates/template.config")), title="Template File"
    )

    index_satellite_peaks: bool = Field(default=False, title="Index Satellite Peaks")
    tolerance_satellite: float = Field(default=0.08, title="Tolerance Satellite")
    mod_vec_1: str = Field(default="0.0,0.0,0.0", title="Modulation Vector 1")
    mod_vec_2: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], title="Modulation Vector 2")
    mod_vec_3: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], title="Modulation Vector 3")
    mod_vec_1_dh: float = Field(default=0.0, title="dh1")
    mod_vec_1_dk: float = Field(default=0.0, title="dk1")
    mod_vec_1_dl: float = Field(default=0.0, title="dl1")
    mod_vec_2_dh: float = Field(default=0.0, title="dh2")
    mod_vec_2_dk: float = Field(default=0.0, title="dk2")
    mod_vec_2_dl: float = Field(default=0.0, title="dl2")
    mod_vec_3_dh: float = Field(default=0.0, title="dh3")
    mod_vec_3_dk: float = Field(default=0.0, title="dk3")
    mod_vec_3_dl: float = Field(default=0.0, title="dl3")
    max_order: int = Field(default=0, title="Max Order")
    cross_terms: Optional[bool] = Field(default=False, title="Cross Terms")
    save_mod_info: Optional[bool] = Field(default=True, title="Save Mod Info")
    sat_peak_radius: float = Field(default=0.08, title="Satellite peak size")
    sat_peak_region_radius: float = Field(default=0.11, title="Satellite region radius")
    sat_peak_inner_radius: float = Field(default=0.09, title="Satellite inner size")
    sat_peak_outer_radius: float = Field(default=0.1, title="Satellite outer size")

    @model_validator(mode="after")
    def validate_inner_less_than_outer_sat_r(self) -> "ExperimentInfoModel":
        min_value = self.sat_peak_inner_radius
        max_value = self.sat_peak_outer_radius
        if min_value is not None and max_value is not None and min_value >= max_value:
            raise ValueError("inner radius must be less than outer radius")
        return self

    export_results: Optional[bool] = Field(default=True, title="Export Results")
    override_export_folder: Optional[bool] = Field(default=False, title="Use custom export folder")
    export_folder: str = Field(default="", title="Export Folder")

    options: Options = Field(default=Options())

    error_message: str = ""
    show_error: bool = False

    @computed_field  # type: ignore
    @property
    def is_max_order_zero(self) -> bool:
        return self.max_order == 0

    # class PlottingInputs(BaseModel):
    """Configuration for the plotting input tab."""

    flux_file: str = Field(
        default="",
        title="Flux File",
        description="Optional Vanadium file for flux for this run cycle for plotting only",
        examples=["/SNS/path/to/flux_file.h5"],
    )

    sa_file: str = Field(
        default="",
        title="SA File",
        description="Optional Vanadium file for solid angle for this run cycle for plotting only",
        examples=["/SNS/path/to/solid_angle.nxs"],
    )

    @computed_field  # type: ignore
    @property
    def flux_sa_notmatch(self) -> bool:
        return (len(self.flux_file) == 0 and len(self.sa_file) > 0) or (
            len(self.flux_file) > 0 and len(self.sa_file) == 0
        )

    @computed_field  # type: ignore
    @property
    def flux_sa_notprovided(self) -> bool:
        return len(self.flux_file) + len(self.sa_file) == 0

    @computed_field  # type: ignore
    @property
    def block_autoreduce(self) -> bool:
        return self.flux_sa_notmatch or not self.UBFileName

    # plot 1
    plot_1_axis1: str = Field(
        default="H",
        title="Plot 1 Integrated Axis:",
        description="The data is integrated along this axis to generate plot1.",
    )

    plot_1_slice_location: float = Field(
        default=0.0,
        title="Slice at:",
        description="The center of data slice on integrated axis.",
    )

    plot_1_thickness: float = Field(
        default=0.1, title="Thickness", description="The thickness of the slice for plot 1.", examples=[0.1]
    )

    plot_1_axis2: str = Field(
        default="K",
        title="X-axis",
        description="The x axis of the plotted data.",
    )

    plot_1_xmin: float = Field(
        default=-10.0,
        title="X-min",
        description="The minimum value along x axis of the plotted data.",
        examples=[-10.0],
    )

    plot_1_xmax: float = Field(
        default=+10.0,
        title="X-max",
        description="The maximum value along x axis of the plotted data.",
        examples=[+10.0],
    )

    plot_1_xstep: int = Field(
        default=400,
        title="#X-steps",
        description="The number of pixels along x axis of the plotted data.",
        examples=[100],
    )

    plot_1_axis3: str = Field(
        default="L",
        title="Y-axis",
        description="The y axis of the plotted data.",
    )

    plot_1_ymin: float = Field(
        default=-10.0,
        title="Y-min",
        description="The minimum value along y axis of the plotted data.",
        examples=[-10.0],
    )

    plot_1_ymax: float = Field(
        default=+10.0,
        title="Y-max",
        description="The maximum value along y axis of the plotted data.",
        examples=[+10.0],
    )

    plot_1_ystep: int = Field(
        default=400,
        title="#Y-steps",
        description="The number of pixels along y axis of the plotted data.",
        examples=[100],
    )

    plot_1_zmin: float = Field(
        default=-0.05,
        title="Z-min",
        description="The minimum value along integrated axis of the plotted data.",
        examples=[-10.0],
    )

    plot_1_zmax: float = Field(
        default=+0.05,
        title="Z-max",
        description="The maximum value along integrated axis of the plotted data.",
        examples=[+10.0],
    )

    # plot 2
    plot_2_axis1: str = Field(
        default="K",
        title="Plot 2 Integrated Axis:",
        description="The data is integrated along this axis to generate plot1.",
    )

    plot_2_slice_location: float = Field(
        default=0.0,
        title="Slice at:",
        description="The center of data slice on integrated axis.",
    )

    plot_2_thickness: float = Field(
        default=0.1, title="Thickness", description="The thickness of the slice for plot 1.", examples=[0.1]
    )

    plot_2_axis2: str = Field(
        default="H",
        title="X-axis",
        description="The x axis of the plotted data.",
    )

    plot_2_xmin: float = Field(
        default=-10.0,
        title="X-min",
        description="The minimum value along x axis of the plotted data.",
        examples=[-10.0],
    )

    plot_2_xmax: float = Field(
        default=+10.0,
        title="X-max",
        description="The maximum value along x axis of the plotted data.",
        examples=[+10.0],
    )

    plot_2_xstep: int = Field(
        default=400,
        title="#X-steps",
        description="The number of pixels along x axis of the plotted data.",
        examples=[100],
    )

    plot_2_axis3: str = Field(
        default="L",
        title="Y-axis",
        description="The y axis of the plotted data.",
    )

    plot_2_ymin: float = Field(
        default=-10.0,
        title="Y-min",
        description="The minimum value along y axis of the plotted data.",
        examples=[-10.0],
    )

    plot_2_ymax: float = Field(
        default=+10.0,
        title="Y-max",
        description="The maximum value along y axis of the plotted data.",
        examples=[+10.0],
    )

    plot_2_ystep: int = Field(
        default=400,
        title="#Y-steps",
        description="The number of pixels along y axis of the plotted data.",
        examples=[100],
    )

    plot_2_zmin: float = Field(
        default=-0.05,
        title="Z-min",
        description="The minimum value along integrated axis of the plotted data.",
        examples=[-10.0],
    )

    plot_2_zmax: float = Field(
        default=+0.05,
        title="Z-max",
        description="The maximum value along integrated axis of the plotted data.",
        examples=[+10.0],
    )

    # plot 3
    plot_3_axis1: str = Field(
        default="L",
        title="Plot 3 Integrated Axis:",
        description="The data is integrated along this axis to generate plot1.",
    )

    plot_3_slice_location: float = Field(
        default=0.0,
        title="Slice at:",
        description="The center of data slice on integrated axis.",
    )

    plot_3_thickness: float = Field(
        default=0.1, title="Thickness", description="The thickness of the slice for plot 1.", examples=[0.1]
    )

    plot_3_axis2: str = Field(
        default="K",
        title="X-axis",
        description="The x axis of the plotted data.",
    )

    plot_3_xmin: float = Field(
        default=-10.0,
        title="X-min",
        description="The minimum value along x axis of the plotted data.",
        examples=[-10.0],
    )

    plot_3_xmax: float = Field(
        default=+10.0,
        title="X-max",
        description="The maximum value along x axis of the plotted data.",
        examples=[+10.0],
    )

    plot_3_xstep: int = Field(
        default=400,
        title="#X-steps",
        description="The number of pixels along x axis of the plotted data.",
        examples=[100],
    )

    plot_3_axis3: str = Field(
        default="H",
        title="Y-axis",
        description="The y axis of the plotted data.",
    )

    plot_3_ymin: float = Field(
        default=-10.0,
        title="Y-min",
        description="The minimum value along y axis of the plotted data.",
        examples=[-10.0],
    )

    plot_3_ymax: float = Field(
        default=+10.0,
        title="Y-max",
        description="The maximum value along y axis of the plotted data.",
        examples=[+10.0],
    )

    plot_3_ystep: int = Field(
        default=400,
        title="#Y-steps",
        description="The number of pixels along y axis of the plotted data.",
        examples=[100],
    )

    plot_3_zmin: float = Field(
        default=-0.05,
        title="Z-min",
        description="The minimum value along integrated axis of the plotted data.",
        examples=[-10.0],
    )

    plot_3_zmax: float = Field(
        default=+0.05,
        title="Z-max",
        description="The maximum value along integrated axis of the plotted data.",
        examples=[+10.0],
    )

    @field_validator("sa_file", mode="after")
    @classmethod
    def check_safile_extension(cls, sa_file: str) -> str:
        if sa_file and not (sa_file.endswith(".nxs") or sa_file.endswith(".h5")):
            raise ValueError("If selected, the solid angle file must be an nexus HDF5 file.")
        return sa_file

    @field_validator("flux_file", mode="after")
    @classmethod
    def check_fluxfile_extension(cls, flux_file: str) -> str:
        if flux_file and not (flux_file.endswith(".nxs") or flux_file.endswith(".h5")):
            raise ValueError("If selected, the flux file must be an nexus HDF5 file.")
        return flux_file

    def copy_config_files(self) -> None:
        if not os.path.exists(f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/autoreduce/"):
            os.makedirs(f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/autoreduce/")
        timestr = time.strftime("%Y%m%d-%H%M%S")
        rd_filename = f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/autoreduce/autoreduce" + timestr + ".config"
        plt_filename = f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/autoreduce/plotConfig" + timestr + ".ini"

        self.plot_config(plt_filename)
        self.reduce_config(rd_filename)

    def reduce_config(self, filename: str) -> None:
        config_content = self.prepare_config_file()
        with open(filename, "w") as configfile:
            configfile.write(config_content)

    def plot_config(self, filename: str) -> None:
        import configparser

        self.plot_1_zmin = self.plot_1_slice_location - self.plot_1_thickness / 2
        self.plot_1_zmax = self.plot_1_slice_location + self.plot_1_thickness / 2
        self.plot_2_zmin = self.plot_2_slice_location - self.plot_2_thickness / 2
        self.plot_2_zmax = self.plot_2_slice_location + self.plot_2_thickness / 2
        self.plot_3_zmin = self.plot_3_slice_location - self.plot_3_thickness / 2
        self.plot_3_zmax = self.plot_3_slice_location + self.plot_3_thickness / 2
        if self.UBFileName:
            ub_directory = os.path.dirname(self.UBFileName)
        config = configparser.ConfigParser()
        config["PLOT1"] = {
            "axis1": self.plot_1_axis1,
            "axis2": self.plot_1_axis2,
            "axis3": self.plot_1_axis3,
            "xmin": str(self.plot_1_xmin),
            "xmax": str(self.plot_1_xmax),
            "xsteps": str(self.plot_1_xstep),
            "ymin": str(self.plot_1_ymin),
            "ymax": str(self.plot_1_ymax),
            "ysteps": str(self.plot_1_ystep),
            "zmin": str(self.plot_1_zmin),
            "zmax": str(self.plot_1_zmax),
        }
        config["PLOT2"] = {
            "axis1": self.plot_2_axis1,
            "axis2": self.plot_2_axis2,
            "axis3": self.plot_2_axis3,
            "xmin": str(self.plot_2_xmin),
            "xmax": str(self.plot_2_xmax),
            "xsteps": str(self.plot_2_xstep),
            "ymin": str(self.plot_2_ymin),
            "ymax": str(self.plot_2_ymax),
            "ysteps": str(self.plot_2_ystep),
            "zmin": str(self.plot_2_zmin),
            "zmax": str(self.plot_2_zmax),
        }
        config["PLOT3"] = {
            "axis1": self.plot_3_axis1,
            "axis2": self.plot_3_axis2,
            "axis3": self.plot_3_axis3,
            "xmin": str(self.plot_3_xmin),
            "xmax": str(self.plot_3_xmax),
            "xsteps": str(self.plot_3_xstep),
            "ymin": str(self.plot_3_ymin),
            "ymax": str(self.plot_3_ymax),
            "ysteps": str(self.plot_3_ystep),
            "zmin": str(self.plot_3_zmin),
            "zmax": str(self.plot_3_zmax),
        }
        config["REDUCTION"] = {"CalFile": self.cal_filename, "UBDirectory": ub_directory}
        config["NORMALIZATION"] = {"SAFile": self.sa_file, "FluxFile": self.flux_file}
        if not os.path.exists(f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/autoreduce/"):
            os.makedirs(f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/autoreduce/")

        with open(filename, "w") as configfile:
            config.write(configfile)

    def model_post_init(self, __context: Any) -> None:
        self.update_option_lists()

    def update_option_lists(self) -> None:
        crystal_system_point_group_map = {
            "Triclinic": ["1", "-1"],
            "Monoclinic": ["2", "m", "2/m", "112", "11m", "112/m"],
            "Orthorhombic": ["222", "mm2", "mmm"],
            "Tetragonal": ["4", "-4", "4/m", "422", "4mm", "-42m", "-4m2", "4/mmm"],
            "Trigonal/Rhombohedral": ["3 r", "-3 r", "32 r", "3m r", "-3m r"],
            "Trigonal/Hexagonal": [
                "3",
                "-3",
                "312",
                "31m",
                "32",
                "321",
                "3m",
                "-31m",
                "-3m",
                "-3m1",
            ],
            "Hexagonal": ["6", "-6", "6/m", "622", "6mm", "-62m", "-6m2", "6/mmm"],
            "Cubic": ["23", "m-3", "432", "-43m", "m-3m"],
        }

        point_group_centering_map = {
            "1": ["P"],
            "-1": ["P"],
            "2": ["P", "C"],
            "m": ["P", "C"],
            "2/m": ["P", "C"],
            "112": ["P", "C"],
            "11m": ["P", "C"],
            "112/m": ["P", "C"],
            "222": ["P", "I", "C", "A", "B"],
            "mm2": ["P", "I", "C", "A", "B"],
            "mmm": ["P", "I", "C", "A", "B"],
            "4": ["P", "I"],
            "-4": ["P", "I"],
            "4/m": ["P", "I"],
            "422": ["P", "I"],
            "4mm": ["P", "I"],
            "-42m": ["P", "I"],
            "-4m2": ["P", "I"],
            "4/mmm": ["P", "I"],
            "3 r": ["R"],
            "-3 r": ["R"],
            "32 r": ["R"],
            "3m r": ["R"],
            "-3m r": ["R"],
            "3": ["Robv", "Rrev"],
            "-3": ["Robv", "Rrev"],
            "312": ["Robv", "Rrev"],
            "31m": ["Robv", "Rrev"],
            "32": ["Robv", "Rrev"],
            "321": ["Robv", "Rrev"],
            "3m": ["Robv", "Rrev"],
            "-31m": ["Robv", "Rrev"],
            "-3m": ["Robv", "Rrev"],
            "-3m1": ["Robv", "Rrev"],
            "6": ["P"],
            "-6": ["P"],
            "6/m": ["P"],
            "622": ["P"],
            "6mm": ["P"],
            "-62m": ["P"],
            "-6m2": ["P"],
            "6/mmm": ["P"],
            "23": ["P", "I", "F"],
            "m-3": ["P", "I", "F"],
            "432": ["P", "I", "F"],
            "-43m": ["P", "I", "F"],
            "m-3m": ["P", "I", "F"],
        }

        self.options.point_group_list = crystal_system_point_group_map.get(self.crystalsystem, [])
        if self.point_group not in self.options.point_group_list:
            self.point_group = self.options.point_group_list[0]

        self.options.centering_list = point_group_centering_map.get(self.point_group, [])
        if self.centering not in self.options.centering_list:
            self.centering = self.options.centering_list[0]

        return

    def reset(self) -> None:
        default_model = ExperimentInfoModel()
        for field, value in default_model:
            setattr(self, field, value)

    @model_validator(mode="after")
    def adjust_export_folder(self) -> "ExperimentInfoModel":
        if not self.override_export_folder:
            self.export_folder = f"/SNS/TOPAZ/{self.get_ipts_name()}/shared/ndip/{self.exp_name}"
        return self

    @model_validator(mode="after")
    def set_max_order_depedencies(self) -> "ExperimentInfoModel":
        if self.is_max_order_zero:
            self.cross_terms = False
            self.save_mod_info = False

        return self

    def get_ipts_name(self) -> str:
        if self.ipts_number.startswith("IPTS"):
            return self.ipts_number
        else:
            return f"IPTS-{self.ipts_number}"

    def prepare_config_file(self) -> str:
        base_dir = os.getcwd()
        out_dir = base_dir[: base_dir.find("shared")] + "shared/" + self.exp_name
        pg = self.point_group
        kw = {
            "molecularFormula": '"{}"'.format(self.molecular_formula),
            "Z": self.Z,
            "unitCellVolume": self.unit_cell_volume,
            "sampleRadius": self.sample_radius,
            "instrument": self.instrument,
            "calFileName": self.cal_filename,
            "maxQ": self.max_q,
            "split_threshold": self.split_threshold,
            "backgroundFileName": self.background_filename,
            "subtract_bkg": self.subtract_bkg,
            "outputDirectory": out_dir,
            "data_directory": self.data_directory,
            "UB_filename": self.UBFileName,
            "read_UB": self.read_ub,
            "centering": self.centering,
            "cell_type": self.crystalsystem,
            "numPeaksToFind": self.num_peaks_to_find,
            "abcMin": self.abc_min,
            "abcMax": self.abc_max,
            "tolerance": self.tolerance,
            "predictPeaks": self.predict_peaks,
            "modStruct": self.mod_struct,
            "live": self.live,
            "min_pred_dspacing": self.pred_min_dspacing,
            "max_pred_dspacing": self.pred_max_dspacing,
            "min_pred_wl": self.pred_min_wavelength,
            "max_pred_wl": self.pred_max_wavelength,
            "peak_radius": self.peak_radius,
            "bkg_inner_radius": self.bkg_inner_radius,
            "bkg_outer_radius": self.bkg_outer_radius,
            "ellipse_size_specified": self.ellipse_size_specified,
            "n_bad_edge_pixels": self.edge_pixels,
            "exp_name": self.exp_name,
            "run_nums": self.run_nums,
            "spectraFileName": self.spectra_filename,
            "normToWavelength": self.norm_to_wavelength,
            "minIsigI": self.min_isigi,
            "numBorderCh": self.border_pixels,
            "minIntensity": self.min_intensity,
            "min_dspacing": self.min_dspacing,
            "scaleFactor": self.scale_factor,
            "min_wl": self.min_wavelength,
            "max_wl": self.max_wavelength,
            "pg_symbol": pg,
            "z_score": self.z_score,
            "starting_batch_number": self.starting_batch_number,
            "tolerance_satellite": self.tolerance_satellite,
            "mod_vector1": "{},{},{}".format(self.mod_vec_1_dh, self.mod_vec_1_dk, self.mod_vec_1_dl),
            "mod_vector2": "{},{},{}".format(self.mod_vec_2_dh, self.mod_vec_2_dk, self.mod_vec_2_dl),
            "mod_vector3": "{},{},{}".format(self.mod_vec_3_dh, self.mod_vec_3_dk, self.mod_vec_3_dl),
            "max_order": self.max_order,
            "cross_terms": self.cross_terms,
            "save_mod_info": self.save_mod_info,
            "satellite_peak_size": self.sat_peak_radius,
            "satellite_region_radius": self.sat_peak_region_radius,
            "satellite_background_inner_size": self.sat_peak_inner_radius,
            "satellite_background_outer_size": self.sat_peak_outer_radius,
            "ipts_number": self.ipts_number,
        }
        # if value in dictionary is missing, set to None
        for key in list(kw.keys()):
            if key not in kw:
                kw[key] = "None"

        template_path = self.template_file
        return self.format_template(template_path, "", **kw)

    def format_template(self, name: str, outfile: str, **kwargs: Any) -> str:
        """Fills in the values for the template called 'name' and writes it to 'outfile'."""
        if "mod3" in name and "mod3" not in outfile:
            outfile = "mod3/" + outfile
        template = open(name).read()
        formatter = string.Formatter()
        return formatter.format(template, **kwargs)

    def has_satellite_params(self, params_dict: dict[str, Any]) -> bool:
        satellite_params = [
            "satellite_peak_size",
            "satellite_background_inner_size",
            "satellite_background_outer_size",
            "satellite_region_radius",
            "tolerance_satellite",
            "mod_vector1",
            "mod_vector2",
            "mod_vector3",
            "max_order",
            "cross_terms",
            "save_mod_info",
        ]

        for param in satellite_params:
            if param in params_dict:
                return True

        return False

    def clear_error(self) -> None:
        self.error_message = ""
        self.show_error = False

    def load_config(self, file_contents: str) -> None:
        try:
            self._load_config(file_contents)
        except Exception as err:
            self.error_message = f"unable to upload full config: {err}"
            self.show_error = True

    def _load_config(self, file_contents: str) -> None:
        # TODO: this seems to be unused, would be better to replace with JSON if necessary still
        config_data = file_contents.splitlines()
        params_dictionary: Dict[str, Any] = {}
        exec(file_contents, None, params_dictionary)
        self.molecular_formula = str(params_dictionary["formulaString"])
        self.Z = self.to_float(params_dictionary["zParameter"])
        self.unit_cell_volume = self.to_float(params_dictionary["unitCellVolume"])
        self.sample_radius = self.to_float(params_dictionary.get("sampleRadius", "1.0"))
        self.centering = params_dictionary["centering"]
        self.crystalsystem = params_dictionary["cell_type"]
        self.point_group = params_dictionary["pg_symbol"]
        self.instrument = params_dictionary["instrument_name"]
        for line in config_data:
            line = line.strip()
            line = line.rstrip()
            if (not line.startswith("#")) and len(line) > 2:
                words = shlex.split(line)
                if len(words) > 1:
                    if words[0] == "run_nums":
                        self.run_nums = words[1]
        self.run_nums = str(self.run_nums).strip("[]")
        self.run_nums = self.run_nums.replace(" ", "")
        self.run_nums = self.run_nums.replace("'", "")
        self.data_directory = params_dictionary["data_directory"]
        # Do not copy experiment name, so you will not overwrite previous data
        # self.exp_name = str(params_dictionary[ "exp_name" ])
        self.cal_filename = params_dictionary["calibration_file_1"]
        self.subtract_bkg = params_dictionary["subtract_bkg"]
        self.background_filename = params_dictionary["no_sample_event_nxs_fname"]
        self.read_ub = params_dictionary["read_UB"]
        self.UBFileName = params_dictionary["UB_filename"]
        self.max_q = self.to_float(self.to_float(params_dictionary.get("Qmax", "20")))
        self.split_threshold = self.to_int(params_dictionary["split_threshold"])
        self.edge_pixels = self.to_int(params_dictionary["n_bad_edge_pixels"])
        self.num_peaks_to_find = self.to_int(params_dictionary["num_peaks_to_find"])
        self.abc_min = self.to_float(params_dictionary["min_d"])
        self.abc_max = self.to_float(params_dictionary["max_d"])
        self.tolerance = self.to_float(params_dictionary["tolerance"])
        self.predict_peaks = self.to_bool(params_dictionary["integrate_predicted_peaks"])
        self.mod_struct = self.to_bool(params_dictionary.get("modStruct", "false"))
        self.live = self.to_bool(params_dictionary.get("live", "false"))
        self.pred_min_dspacing = self.to_float(params_dictionary["min_pred_dspacing"])
        self.pred_max_dspacing = self.to_float(params_dictionary["max_pred_dspacing"])
        self.pred_min_wavelength = self.to_float(params_dictionary["min_pred_wl"])
        self.pred_max_wavelength = self.to_float(params_dictionary["max_pred_wl"])
        self.ellipse_size_specified = self.to_bool(params_dictionary["ellipse_size_specified"])
        self.peak_radius = self.to_float(params_dictionary["peak_radius"])
        self.bkg_inner_radius = self.to_float(params_dictionary["bkg_inner_radius"])
        self.bkg_outer_radius = self.to_float(params_dictionary["bkg_outer_radius"])
        self.spectra_filename = str(params_dictionary["spectraFile"])
        self.norm_to_wavelength = self.to_float(params_dictionary["normToWavelength"])
        self.scale_factor = self.to_float(params_dictionary["scaleFactor"])
        self.min_intensity = self.to_float(params_dictionary["intiMin"])
        self.min_isigi = self.to_float(params_dictionary["minIsigI"])
        self.border_pixels = self.to_int(params_dictionary["numBorderCh"])
        self.min_dspacing = self.to_float(params_dictionary["dMin"])
        self.max_dspacing = self.to_float(params_dictionary["dMax"])
        self.min_wavelength = self.to_float(params_dictionary["wlMin"])
        self.max_wavelength = self.to_float(params_dictionary["wlMax"])
        self.z_score = self.to_float(params_dictionary["z_score"])
        self.starting_batch_number = self.to_int(params_dictionary.get("starting_batch_number", "1"))
        if self.has_satellite_params(params_dictionary):
            self.index_satellite_peaks = True
            self.tolerance_satellite = self.to_float(params_dictionary.get("tolerance_satellite", 0.08))
            mod_vec_1 = params_dictionary.get("mod_vector1", "0.0,0.0,0.0")
            mod_vec_2 = params_dictionary.get("mod_vector2", "0.0,0.0,0.0")
            mod_vec_3 = params_dictionary.get("mod_vector3", "0.0,0.0,0.0")
            self.mod_vec_1_dh = self.to_float(mod_vec_1.split(",")[0])
            self.mod_vec_1_dk = self.to_float(mod_vec_1.split(",")[1])
            self.mod_vec_1_dl = self.to_float(mod_vec_1.split(",")[2])
            self.mod_vec_2_dh = self.to_float(mod_vec_2.split(",")[0])
            self.mod_vec_2_dk = self.to_float(mod_vec_2.split(",")[1])
            self.mod_vec_2_dl = self.to_float(mod_vec_2.split(",")[2])
            self.mod_vec_3_dh = self.to_float(mod_vec_3.split(",")[0])
            self.mod_vec_3_dk = self.to_float(mod_vec_3.split(",")[1])
            self.mod_vec_3_dl = self.to_float(mod_vec_3.split(",")[2])
            self.max_order = self.to_int(params_dictionary.get("max_order", 0))
            #            self.hide_satellites() ???
            self.cross_terms = self.to_bool(params_dictionary.get("cross_terms", False))
            self.save_mod_info = self.to_bool(params_dictionary.get("save_mod_info", True))
            self.sat_peak_radius = self.to_float(params_dictionary.get("satellite_peak_size", 0.08))
            self.sat_peak_region_radius = self.to_float(params_dictionary.get("satellite_region_radius", 0.11))
            self.sat_peak_inner_radius = self.to_float(params_dictionary.get("satellite_background_inner_size", 0.09))
            self.sat_peak_outer_radius = self.to_float(params_dictionary.get("satellite_background_outer_size", 0.1))
        else:
            self.index_satellite_peaks = False
            self.tolerance_satellite = self.to_float(0.08)
            self.mod_vec_1_dh = 0.0
            self.mod_vec_1_dk = 0.0
            self.mod_vec_1_dl = 0.0
            self.mod_vec_2_dh = 0.0
            self.mod_vec_2_dk = 0.0
            self.mod_vec_2_dl = 0.0
            self.mod_vec_3_dh = 0.0
            self.mod_vec_3_dk = 0.0
            self.mod_vec_3_dl = 0.0
            self.max_order = 0
            self.cross_terms = False
            self.save_mod_info = True
            self.sat_peak_radius = self.to_float(0.08)
            self.sat_peak_region_radius = self.to_float(0.11)
            self.sat_peak_inner_radius = self.to_float(0.09)
            self.sat_peak_outer_radius = self.to_float(0.1)

        ipts_number = params_dictionary.get("ipts_number", "")
        # Try to load from the data directory as a fallback
        if not ipts_number:
            search_result = re.search(r"IPTS-[\d]+", self.data_directory)
            if search_result:
                ipts_number = re.sub(r"\D", "", search_result.group(0))

        if ipts_number:
            self.ipts_number = ipts_number
        else:
            self.ipts_number = " "
            self.error_message = (
                "Unable to determine IPTS number from the config file. "
                "The data file appears to be in an unconventional location. "
                "Please verify the information is correct, then manually set the IPTS number "
                "in the reduction input tab."
            )
            self.show_error = True

        self.update_option_lists()
        self.model_validate(self.model_dump(), strict=True)

    def to_bool(self, temp: Any) -> bool:
        try:
            result = bool(temp)
        except Exception:
            result = False
        return result

    def to_int(self, temp: Any) -> int:
        try:
            result = int(temp)
        except Exception:
            result = 0
        return result

    def to_float(self, temp: Any) -> float:
        # for python strings
        try:
            if type(temp) is float:
                return temp
            elif "." in temp or "e" in temp:
                result = float(temp)
            else:
                temp_int = int(temp)
                result = float(temp_int)
        except Exception:
            result = 0
        return result


class SharedConfig:
    """A shared instance of the Config class."""

    _instance = None

    @classmethod
    def get_instance(cls) -> ExperimentInfoModel:
        if not cls._instance:
            cls._instance = ExperimentInfoModel()
        return cls._instance
