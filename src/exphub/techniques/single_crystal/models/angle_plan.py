"""Model for angle plan."""

import csv
import logging
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import plotly.graph_objects as go
from pydantic import BaseModel, Field, model_validator

from ....core.beamline import active as _active_beamline
from . import gonio_pvs

logger = logging.getLogger(__name__)


def _default_instrument_name() -> str:
    try:
        return _active_beamline().single_crystal.mantid.instrument_name
    except Exception:
        return ""


def _default_angle_list_read() -> List[Dict]:
    """Single placeholder row using the active beamline's gonio PV column names."""
    try:
        pvs = gonio_pvs.ANGLE_PVS[gonio_pvs.AMBIENT]
        row: Dict[str, Any] = {
            "Title": "",
            "Comment": "",
            "Wait For": "PCharge",
            "Value": 10,
            "Or Time": "",
        }
        for axis_pv in pvs.values():
            row[axis_pv] = 10
        return [row]
    except Exception:
        return [{"Title": "", "Comment": "", "Wait For": "PCharge", "Value": 10, "Or Time": ""}]


# Headers for the experiment-run-strategy table. The cryogenic stage drives
# only one rotation (CryoOmega), so its header omits phi; the ambient stage
# carries both omega and phi.
_AMBIENT_HEADERS: List[Dict] = [
    {"title": "Title", "value": "title", "sortable": True, "align": "center"},
    {"title": "Comment", "value": "comment", "sortable": True, "align": "center"},
    {"title": "phi", "value": "phi", "sortable": True, "align": "center"},
    {"title": "omega", "value": "omega", "sortable": True, "align": "center"},
    {"title": "Wait For", "value": "wait_for", "sortable": True, "align": "center"},
    {"title": "Value", "value": "value", "sortable": True, "align": "center"},
    {"title": "Action", "value": "actions", "sortable": False, "align": "center"},
]
_CRYOGENIC_HEADERS: List[Dict] = [
    {"title": "Title", "value": "title", "sortable": True, "align": "center"},
    {"title": "Comment", "value": "comment", "sortable": True, "align": "center"},
    {"title": "omega", "value": "omega", "sortable": True, "align": "center"},
    {"title": "Wait For", "value": "wait_for", "sortable": True, "align": "center"},
    {"title": "Value", "value": "value", "sortable": True, "align": "center"},
    {"title": "Action", "value": "actions", "sortable": False, "align": "center"},
]


class RunPlan(BaseModel):
    """Pydantic class for run plan.

    A row is either an angle step (drive goniometer, wait for PCharge or time)
    or a ramp step (drive Lakeshore Start->End at Rate K/min, soak).
    Ramp fields are None on angle rows; angle fields are still meaningful on
    ramp rows when the user wants to set position during the ramp.
    """

    title: str = Field(default="Untitled")
    comment: str = Field(default="")
    phi: float = Field(default=0.0)
    omega: float = Field(default=0.0)
    wait_for: str = Field(default="")
    value: float = Field(default=0.0)
    or_time: float = Field(default=0.0)
    step_type: Literal["angle", "ramp"] = Field(default="angle")
    ramp_start: Optional[float] = Field(default=None)
    ramp_end: Optional[float] = Field(default=None)
    ramp_rate: Optional[float] = Field(default=None)
    ramp_soak: Optional[float] = Field(default=None)
    ramp_run: Optional[int] = Field(default=None)


class AnglePlanModel(BaseModel):
    """Pydantic class for angle plan."""

    # Header layout was previously hardcoded with literal goniometer PV names; the
    # active rendering builds headers from the beamline context at runtime.
    angle_keys: List[str] = Field(
        default=[
            "id",
            "title",
            "comment",
            "chi",
            "phi",
            "omega",
            "wait_for",
            "value",
            "or_time",
            "step_type",
            "ramp_start",
            "ramp_end",
            "ramp_rate",
            "ramp_soak",
            "ramp_run",
        ]
    )
    angle_list_headers: List[Dict] = Field(default_factory=lambda: list(_AMBIENT_HEADERS))
    goniometer_type: str = Field(
        default="Ambient goniometer",
        title="Goniometer",
        description="Selects the goniometer in use; cryogenic mode hides the omega column.",
    )
    goniometer_type_options: List[str] = Field(
        default_factory=lambda: ["Ambient goniometer", "Cryogenic goniometer"],
    )

    @model_validator(mode="after")
    def sync_headers_with_goniometer_type(self) -> "AnglePlanModel":
        """Keep `angle_list_headers` aligned with the selected goniometer."""
        target = list(_CRYOGENIC_HEADERS) if self.goniometer_type == "Cryogenic goniometer" else list(_AMBIENT_HEADERS)
        if self.angle_list_headers != target:
            self.angle_list_headers = target
        return self

    show_coverage: bool = Field(
        default=False, title="Show Coverage", description="Flag to indicate if coverage is shown"
    )
    # Compute-only fields below: never read by the Vue view or the agent bridge —
    # mark exclude=True so they don't ride along on every state push to the
    # browser. After `optimize_angleplan` runs, these can grow to tens of KB
    # and would otherwise be re-serialized on every UI interaction.
    polyhedrons: List = Field(
        default=[],
        title="Polyhedrons",
        description="List of polyhedrons to be displayed",
        exclude=True,
    )

    # table_test: List[Dict] = Field(default=[{"title":"1","header":"h"}])
    # test: str = Field(default="test", title="Test", description="Test field")
    # test_list: List[str] = Field(default=["test1", "test2"])
    # test_dict: List[Dict] = Field(default=[{"key1": "testdict1", "key2": "testdict2"}])
    # test_dict: List[List] = Field(default=[[ "testlist1"],[  "testlist2"]])

    ###########################################################################################################################################
    # TODO: pydantic model variable realization for angle list: used for pydnatic table(vrow)
    # run_plan1=RunPlan(title="test_angleplan_1",comment="",phi=0,omega=0,wait_for="PCharge",value=10,or_time=0)
    # run_plan2=RunPlan(title="test_angleplan_2",comment="",phi=10,omega=10,wait_for="PCharge",value=10,or_time=0)
    # angle_list_pd:List[RunPlan]=Field(default=[run_plan1,run_plan2])
    angle_list_pd: List[RunPlan] = Field(
        default=[
            RunPlan(title="test_angleplan_1", comment="", phi=0, omega=0, wait_for="PCharge", value=10, or_time=0),
            RunPlan(title="test_angleplan_2", comment="", phi=10, omega=10, wait_for="PCharge", value=10, or_time=0),
        ],
        exclude=True,
    )
    ###########################################################################################################################################

    is_editing_run: bool = Field(
        default=False, title="Is Editing", description="Flag to indicate if the angle plan is being edited"
    )
    is_showing_coverage: bool = Field(
        default=False, title="Is Showing Coverage", description="Flag to indicate if the coverage is being shown"
    )
    run_record: Dict = Field(
        default={
            "id": 0,
            "title": "title",
            "comment": "",
            "chi": 0,
            "phi": 0,
            "omega": 0,
            "wait_for": "PCharge",
            "value": 0,
            "or_time": "",
            "step_type": "angle",
            "ramp_start": None,
            "ramp_end": None,
            "ramp_rate": None,
            "ramp_soak": None,
            "ramp_run": None,
        },
        title="Run Record",
        description="Record of the run plan",
    )
    runedit_dialog: bool = Field(
        default=False, title="Run Edit Dialog", description="Flag to indicate if the run edit dialog is open"
    )

    angle_list_read: List[Dict] = Field(
        default_factory=_default_angle_list_read,
        title="Angle Plan",
        description="List of angles to be measured",
        exclude=True,
    )
    ##############################################################################
    #    angle_list: List[Dict] = Field(default=[{"id":1,
    #                                             "title":"test_angleplan_1",
    #                                             "comment":"",
    #                                             "chi":0,
    #                                             "phi":0,
    #                                             "omega":0,
    #                                             "wait_for": "PCharge",
    #                                             "value": 1,
    #                                             "or_time": ""},
    #                                            {"id":2,
    #                                             "title":"test_angleplan_2",
    #                                             "comment":"",
    #                                             "chi":10,
    #                                             "phi":10,
    #                                             "omega":10,
    #                                             "wait_for": "PCharge",
    #                                             "value": 1,
    #                                             "or_time": ""},
    #                                             ],
    #                                    title="Angle Plan",
    #                                    description="List of angles to be measured",)
    angle_list: List[Dict] = Field(
        default=[],
        title="Angle Plan",
        description="List of angles to be measured",
    )

    plan_name: str = Field(default="CrystalPilot Plan", title="Strategy Name", description="Name of the plan")

    plan_file: str = Field(
        default="",
        title="Strategy File",
        description="File path to the plan file",
    )
    plan_type: str = Field(default="Crystal Plan", title="Strategy Type", description="Type of the plan")
    plan_type_list: List[str] = Field(default=["CrystalPlan", "NeuXstalViz"])
    wait_for_list: List[str] = Field(default=["PCharge", "seconds"])
    step_type_options: List[str] = Field(default=["angle", "ramp"])

    target_coverage: float = Field(
        default=0.9, title="Target coverage", description="Target coverage for the experiment"
    )
    qpane_cones: List = Field(
        default=[], title="Q Pane Cones", description="List of Q pane cones to be displayed", exclude=True
    )
    qpoints_all: List = Field(
        default=[], title="Q Points", description="List of Q points to be displayed", exclude=True
    )
    qpoints_covered: List = Field(
        default=[],
        title="Q Points Covered",
        description="List of Q points covered by the experiment",
        exclude=True,
    )

    instrument: str = Field(
        default_factory=_default_instrument_name,
        title="Instrument Name",
        description="Name of the instrument",
    )
    wavelength: float = Field(default=1.0, title="Wavelength", description="Wavelength of the beam")
    axes: List = Field(default=[[0, 1, 0]], title="Axes", description="List of axes to be used for the angle plan")
    limits: List = Field(default=[0, 360], title="Limits", description="Limits of the axes")
    UB: List = Field(
        default=[
            [-0.06196579, -0.0646735, 0.00629365],
            [0.05857223, -0.05941086, -0.03262031],
            [0.02816059, -0.01873959, 0.08169699],
        ],
        title="UB Matrix",
        description="UB matrix of the crystal",
    )
    d_min: float = Field(default=0.5, title="d_min", description="d_min of the crystal")
    d_max: float = Field(default=10, title="d_max", description="d_max of the crystal")
    offset: float = Field(default=0, title="Offset", description="Offset of the crystal")
    point_group: str = Field(default="m-3", title="Point Group", description="Point group of the crystal")
    lattice_centering: str = Field(
        default="P", title="Lattice Centering", description="Lattice centering of the crystal"
    )
    symmetry_operations: List = Field(
        default=[],
        title="Symmetry Operations",
        description="List of symmetry operations to be used for the angle plan",
        exclude=True,
    )

    def get_default_run_record(self) -> Dict:
        return {
            "id": 0,
            "title": "",
            "comment": "",
            "chi": 0,
            "phi": 0,
            "omega": 0,
            "wait_for": "PCharge",
            "value": 0,
            "or_time": "",
            "step_type": "angle",
            "ramp_start": None,
            "ramp_end": None,
            "ramp_rate": None,
            "ramp_soak": None,
            "ramp_run": None,
        }

    # @field_validator("angle_list", mode="before")
    def load_ap(self, file_path: str) -> None:
        logger.debug("load_ap")
        with open(file_path, mode="r") as apfile:
            reader = csv.DictReader(apfile)
            self.angle_list_read = list(reader)
        self.convert_plan_format(self.plan_type, self.angle_list_read)
        self.convert_angle_list_read_to_angle_list()

        # print(self.angle_list)

    def convert_plan_format(self, source_type: str, angle_list: List[Dict]) -> None:
        if not angle_list:
            self.angle_list_read = []
            return

        # Auto-detect goniometer type from the CSV columns and reconcile with the
        # current selection: if the file's columns don't match, surface a clear
        # error rather than silently importing zeros.
        columns = list(angle_list[0].keys())
        detected = gonio_pvs.detect_goniometer_type(columns)
        if detected != self.goniometer_type:
            raise ValueError(
                f"CSV columns indicate {detected!r} but goniometer_type is set "
                f"to {self.goniometer_type!r}. Switch the goniometer selector before importing."
            )

        new_angle_list: List[Dict] = []
        for row in angle_list:
            new_row: Dict = {}
            if source_type == "Crystal Plan":
                new_row["Title"] = row.get("Notes", row.get("Title", ""))
                new_row["Comment"] = row.get("Comment", "")
            elif source_type == "NeuXstalViz":
                new_row["Title"] = row.get("Title", "").replace("_", " ")
                new_row["Comment"] = row.get("Comment", "").replace("_", " ")
            else:
                new_row["Title"] = row.get("Title", row.get("Notes", ""))
                new_row["Comment"] = row.get("Comment", "")

            for col in gonio_pvs.angle_columns(self.goniometer_type):
                new_row[col] = row.get(col, "")

            if gonio_pvs.is_ramp_row(row):
                new_row["step_type"] = "ramp"
                for key, canonical in gonio_pvs.RAMP_PVS.items():
                    new_row[canonical] = gonio_pvs.ramp_value(row, key)
                new_row["Wait For"] = ""
                new_row["Value"] = ""
                new_row["Or Time"] = ""
            else:
                new_row["step_type"] = "angle"
                wait_for_key = next((key for key in row.keys() if key.startswith("Wait For")), None)
                wait_for = row[wait_for_key] if wait_for_key else "PCharge"
                if "PCharge" in wait_for:
                    wait_for = "PCharge"
                if source_type == "NeuXstalViz":
                    wait_for = wait_for.replace("_", " ")
                new_row["Wait For"] = wait_for
                new_row["Value"] = row.get("Value", "")
                or_time = row.get("Or Time", "")
                new_row["Or Time"] = or_time.replace("_", " ") if source_type == "NeuXstalViz" else or_time

            new_angle_list.append(new_row)

        self.angle_list_read = new_angle_list

    def convert_angle_list_read_to_angle_list(self) -> None:
        angle_pvs = gonio_pvs.ANGLE_PVS[self.goniometer_type]
        omega_col = angle_pvs["omega"]
        phi_col = angle_pvs.get("phi")  # None on cryogenic

        def _to_float(v: Any) -> float:
            if v in ("", None):
                return 0.0
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        def _to_opt_float(v: Any) -> Optional[float]:
            if v in ("", None):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _to_opt_int(v: Any) -> Optional[int]:
            f = _to_opt_float(v)
            return None if f is None else int(f)

        new_angle_list = []
        for i, angle in enumerate(self.angle_list_read):
            new_angle: Dict = {
                "id": i + 1,
                "title": angle.get("Title", ""),
                "comment": angle.get("Comment", ""),
                "chi": 0,
                "phi": _to_float(angle.get(phi_col)) if phi_col else 0.0,
                "omega": _to_float(angle.get(omega_col)),
                "wait_for": angle.get("Wait For", ""),
                "value": angle.get("Value", ""),
                "or_time": angle.get("Or Time", ""),
                "step_type": angle.get("step_type", "angle"),
                "ramp_start": _to_opt_float(angle.get(gonio_pvs.RAMP_PVS["start"])),
                "ramp_end": _to_opt_float(angle.get(gonio_pvs.RAMP_PVS["end"])),
                "ramp_rate": _to_opt_float(angle.get(gonio_pvs.RAMP_PVS["rate"])),
                "ramp_soak": _to_opt_float(angle.get(gonio_pvs.RAMP_PVS["soak"])),
                "ramp_run": _to_opt_int(angle.get(gonio_pvs.RAMP_PVS["run"])),
            }
            new_angle_list.append(new_angle)
        self.angle_list = new_angle_list

    #    @model_validator(mode="after")
    #    def validate_angle_list(self) -> bool:
    #        if isinstance(self.angle_list,list):
    #            for angle in self.angle_list:
    #                if not isinstance(angle, dict):
    #                    return False
    #                if len(angle) not in [5, 7]:
    #                    return False
    #            return True
    #        else:
    #            return False

    def export_to_nxv_csv(self, file_path: str) -> str:
        """Export angle_list to a CSV file in NeuXtalViz-compatible format.

        Column layout depends on goniometer_type:
        - Ambient:    Title, goniokm:omega, goniokm:phi, ramp PVs, Comment, Wait For, Value
        - Cryogenic:  Title, CryoOmega, ramp PVs, Comment, Wait For, Value
        Returns the file path written.
        """
        run_title_pv = _active_beamline().single_crystal.run_title_pv
        angle_cols = gonio_pvs.angle_columns(self.goniometer_type)
        ramp_cols = list(gonio_pvs.RAMP_PVS.values())
        fieldnames = [
            run_title_pv,
            *angle_cols,
            *ramp_cols,
            "Comment",
            "Wait For",
            "Value",
        ]
        with open(file_path, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for angle in self.angle_list:
                row: Dict = {
                    run_title_pv: angle.get("title", "CrystalPilot"),
                    "Comment": angle.get("comment", ""),
                }
                # Angle cells — always emit; useful even on ramp rows when the
                # user wants to drive to a position during the ramp.
                pvs = gonio_pvs.ANGLE_PVS[self.goniometer_type]
                row[pvs["omega"]] = angle.get("omega", 0)
                if "phi" in pvs:
                    row[pvs["phi"]] = angle.get("phi", 0)

                if angle.get("step_type") == "ramp":
                    row[gonio_pvs.RAMP_PVS["start"]] = angle.get("ramp_start", "")
                    row[gonio_pvs.RAMP_PVS["end"]] = angle.get("ramp_end", "")
                    row[gonio_pvs.RAMP_PVS["rate"]] = angle.get("ramp_rate", "")
                    row[gonio_pvs.RAMP_PVS["soak"]] = angle.get("ramp_soak", "")
                    row[gonio_pvs.RAMP_PVS["run"]] = angle.get("ramp_run", "")
                    row["Wait For"] = ""
                    row["Value"] = ""
                else:
                    wait_for = angle.get("wait_for", "PCharge")
                    row["Wait For"] = gonio_pvs.WAIT_FOR_PCHARGE_PV if wait_for == "PCharge" else wait_for
                    row["Value"] = angle.get("value", 10)
                writer.writerow(row)
        logger.debug(f"Exported {len(self.angle_list)} rows to {file_path}")
        return file_path

    def import_from_nxv_csv(self, file_path: str) -> None:
        """Import a CSV file written by NeuXtalViz back into angle_list.

        Auto-detects goniometer type from the column headers and updates
        self.goniometer_type to match. Ramp rows are detected by presence
        of any ramp PV (canonical or bare RampStart/...) column with values.
        """
        with open(file_path, mode="r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            logger.debug(f"import_from_nxv_csv: empty CSV at {file_path}")
            return

        all_cols = list(rows[0].keys())
        detected = gonio_pvs.detect_goniometer_type(all_cols)
        if detected != self.goniometer_type:
            self.goniometer_type = detected
        angle_pvs = gonio_pvs.ANGLE_PVS[detected]
        omega_col = angle_pvs["omega"]
        phi_col = angle_pvs.get("phi")

        title_col = all_cols[0]

        def _to_float(v: Any, default: float = 0.0) -> float:
            if v in ("", None):
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        def _to_opt_float(v: Any) -> Optional[float]:
            if v in ("", None):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _to_opt_int(v: Any) -> Optional[int]:
            f = _to_opt_float(v)
            return None if f is None else int(f)

        new_angle_list = []
        for i, row in enumerate(rows):
            is_ramp = gonio_pvs.is_ramp_row(row)
            wait_for = row.get("Wait For", "")
            if "PCharge" in wait_for:
                wait_for = "PCharge"
            elif "seconds" in wait_for.lower():
                wait_for = "seconds"

            new_angle_list.append(
                {
                    "id": i + 1,
                    "title": row.get(title_col, ""),
                    "comment": row.get("Comment", ""),
                    "chi": 0.0,
                    "phi": _to_float(row.get(phi_col)) if phi_col else 0.0,
                    "omega": _to_float(row.get(omega_col)),
                    "wait_for": "" if is_ramp else (wait_for if wait_for else "PCharge"),
                    "value": "" if is_ramp else _to_float(row.get("Value"), 10.0),
                    "or_time": "",
                    "step_type": "ramp" if is_ramp else "angle",
                    "ramp_start": _to_opt_float(gonio_pvs.ramp_value(row, "start")) if is_ramp else None,
                    "ramp_end": _to_opt_float(gonio_pvs.ramp_value(row, "end")) if is_ramp else None,
                    "ramp_rate": _to_opt_float(gonio_pvs.ramp_value(row, "rate")) if is_ramp else None,
                    "ramp_soak": _to_opt_float(gonio_pvs.ramp_value(row, "soak")) if is_ramp else None,
                    "ramp_run": _to_opt_int(gonio_pvs.ramp_value(row, "run")) if is_ramp else None,
                }
            )
        self.angle_list = new_angle_list
        logger.debug(f"Imported {len(new_angle_list)} rows from {file_path}")

    def submit_to_eic(self) -> None:
        # Implement the submit logic here
        pass

    # note to symmetry:
    # 1. mantid has
    #   # Create point group
    #   point_group = PointGroupFactory.createPointGroup(point_group_symbol)
    #   # Get symmetry operations
    #   sym_ops = point_group.getSymmetryOperations()
    # 2. symmetryopreation should have matrix() method
    #     not work in python
    # 3. sym_op.transformHKL([1,0,0])           # qspace
    #    sym_op.transformCoordinate[1,0,0])     # real space
    #    have strange  behaviro:  eg
    #
    #
    #         pg = PointGroupFactory.createPointGroup('6/mmm')
    #         s=pg.getSymmetryOperationStrings
    #         s
    #         Out[79]: <bound method getSymmetryOperationStrings of PointGroupFactory.createPointGroup("6/mmm")>
    #         pg.getSymmetryOperationStrings()
    #         Out[80]: <mantid.kernel._kernel.std_vector_str at 0x7ad2afb57df0>
    #         s=pg.getSymmetryOperationStrings()
    #         s
    #         Out[83]: <mantid.kernel._kernel.std_vector_str at 0x7ad2afb84970>
    #         s[0]
    #         Out[84]: '-x+y,-x,-z'
    #     not rotation matrix

    ####################
    # change strategey to use repeated q grids
    ####################
    #
    # def angleplan(self, instrument, logs, wavelength,peaks,laue):

    #
    #    def get_rotation_matrix(self, chi: float, phi: float, omega: float) -> np.array:
    #            rotation_matrix_omega = np.array([
    #                [np.cos(np.radians(omega)), 0, np.sin(np.radians(omega))],
    #                [0, 1, 0],
    #                [-np.sin(np.radians(omega)), 0, np.cos(np.radians(omega))]
    #            ])
    #            rotation_matrix_chi = np.array([
    #                [np.cos(np.radians(chi)), -np.sin(np.radians(chi)), 0],
    #                [np.sin(np.radians(chi)), np.cos(np.radians(chi)), 0],
    #                [0, 0, 1]
    #            ])
    #            rotation_matrix_phi = np.array([
    #                [np.cos(np.radians(phi)), 0, np.sin(np.radians(phi))],
    #                [0, 1, 0],
    #                [-np.sin(np.radians(phi)), 0, np.cos(np.radians(phi))]
    #            ])
    #            # Combine the rotation matrices
    #            rotation_matrix = rotation_matrix_omega @ rotation_matrix_chi @ rotation_matrix_phi
    #            return rotation_matrix

    def get_rotation_matrix(self, chi: float, phi: float, omega: float) -> List[float]:
        rotation_matrix_omega = [
            [np.cos(np.radians(omega)), 0, np.sin(np.radians(omega))],
            [0, 1, 0],
            [-np.sin(np.radians(omega)), 0, np.cos(np.radians(omega))],
        ]
        rotation_matrix_chi = [
            [np.cos(np.radians(chi)), -np.sin(np.radians(chi)), 0],
            [np.sin(np.radians(chi)), np.cos(np.radians(chi)), 0],
            [0, 0, 1],
        ]
        rotation_matrix_phi = [
            [np.cos(np.radians(phi)), 0, np.sin(np.radians(phi))],
            [0, 1, 0],
            [-np.sin(np.radians(phi)), 0, np.cos(np.radians(phi))],
        ]
        # Combine the rotation matrices
        rotation_matrix = (
            np.array(rotation_matrix_omega) @ np.array(rotation_matrix_chi) @ np.array(rotation_matrix_phi)
        ).tolist()
        return rotation_matrix

    def update_polyhedron_angle_list_0(self) -> List:
        # qcones = self.qpane_cones.copy()
        polyhedron_original_list = self.qpane_cones.copy()

        polyhedron_angle_list = []
        for p0 in polyhedron_original_list:
            v0, f0 = p0["qvertices"], p0["qfaces"]
            for angle in self.angle_list:
                # Extract vertices and faces
                chi, phi, omega = angle["chi"], angle["phi"], angle["omega"]
                r = self.get_rotation_matrix(chi, phi, omega)
                v = (r @ v0).tolist()  # Convert numpy array to list

                polyhedron_angle_list.append((v, f0))
        return polyhedron_angle_list

    def get_figure_coverage_0(self) -> go.Figure:
        # Implement the submit logic here

        def get_polyhedron_plot(vertices: Any, faces: Any) -> go.Mesh3d:
            # px1 = vertices[:, 0].tolist()
            # px2 = vertices[:, 0].tolist()
            # px=np.array(px1+px2)
            # py1 = vertices[:, 1].tolist()
            # py2 = vertices[:, 1].tolist()
            # py=np.array(py1+py2)
            # pz1 = vertices[:, 2].tolist()
            # pz2 = vertices[:, 2].tolist()
            # pz=np.array(pz1+pz2)

            # pi1=list(faces[:, 1])
            # pi2=list(faces[:, 3])
            # pi=np.array(pi1+pi2)
            # pj1=list(faces[:, 2])
            # pj2=list(faces[:, 4])
            # pj=np.array(pj1+pj2)
            # pk1=list(faces[:, 3])
            # pk2=list(faces[:, 1])
            # pk=np.array(pk1+pk2)
            px1 = vertices[:, 0].tolist()
            px2 = vertices[:, 0].tolist()
            px = px1 + px2
            py1 = vertices[:, 1].tolist()
            py2 = vertices[:, 1].tolist()
            py = py1 + py2
            pz1 = vertices[:, 2].tolist()
            pz2 = vertices[:, 2].tolist()
            pz = pz1 + pz2

            pi1 = list(faces[:, 1])
            pi2 = list(faces[:, 3])
            pi = pi1 + pi2
            pj1 = list(faces[:, 2])
            pj2 = list(faces[:, 4])
            pj = pj1 + pj2
            pk1 = list(faces[:, 3])
            pk2 = list(faces[:, 1])
            pk = pk1 + pk2
            polyhedron_plot = go.Mesh3d(
                x=px, y=py, z=pz, i=pi, j=pj, k=pk, color="lightblue", opacity=0.50, alphahull=0
            )
            return polyhedron_plot

        # vertices = np.array([
        #    [0, 0, 0],
        #    [1, 0, 0],
        #    [1, 1, 0],
        #    [0, 1, 0],
        #    [0, 0, 1],
        #    [1, 0, 1],
        #    [1, 1, 1],
        #    [0, 1, 1],
        # ])

        ## Define faces
        # faces = np.array([
        #    [4, 0, 1, 2, 3],  # bottom
        #    [4, 4, 5, 6, 7],  # top
        #    [4, 0, 1, 5, 4],  # front
        #    [4, 1, 2, 6, 5],  # right
        #    [4, 2, 3, 7, 6],  # back
        #    [4, 3, 0, 4, 7],  # left
        # ])

        # polyhedrons=[
        #    (vertices, faces),
        #    (vertices+0.5, faces)
        # ]

        fig = go.Figure()
        for polyhedron in self.polyhedrons:
            # Extract vertices and faces
            vertices, faces = polyhedron
            # Create a mesh plot
            polyhedron_plot = get_polyhedron_plot(vertices, faces)
            fig.add_trace(polyhedron_plot)

        fig.update_layout(
            scene={"xaxis_title": "X Axis", "yaxis_title": "Y Axis", "zaxis_title": "Z Axis", "aspectmode": "data"},
            title="3D Polyhedron Visualization",
        )
        return fig

        # self.is_under_development = True

    def get_figure_coverage(self) -> go.Figure:
        qcones = self.qpane_cones.copy()
        faces: List[Any] = []
        for pane in qcones:  # x24 cone iters
            faces = faces + pane["qfaces"]  # 6 faces iters

        all_faces = []
        for f in faces:
            for angle in self.angle_list:
                # Extract vertices and faces
                chi, phi, omega = angle["chi"], angle["phi"], angle["omega"]
                r = self.get_rotation_matrix(chi, phi, omega)
                newf = []
                for qpt in f:
                    newpt = np.dot(r, qpt).tolist()  # Convert numpy array to list
                    newf.append(newpt)
                all_faces.append(newf)
        logger.debug("all_faces")
        logger.debug(len(all_faces))

        def get_face_plot(face: Any) -> go.Mesh3d:
            px = [face[0][0], face[1][0], face[2][0], face[3][0]]
            py = [face[0][1], face[1][1], face[2][1], face[3][1]]
            pz = [face[0][2], face[1][2], face[2][2], face[3][2]]
            pi = [0, 1]
            pj = [1, 2]
            pk = [2, 3]
            # Create a mesh
            face_plot = go.Mesh3d(x=px, y=py, z=pz, i=pi, j=pj, k=pk, color="lightblue", opacity=0.50, alphahull=0)
            return face_plot

        fig = go.Figure()
        for f in all_faces:
            face_plot = get_face_plot(f)
            fig.add_trace(face_plot)

        fig.update_layout(
            scene={"xaxis_title": "X Axis", "yaxis_title": "Y Axis", "zaxis_title": "Z Axis", "aspectmode": "data"},
            title="3D Polyhedron Visualization",
        )
        return fig

    def get_coverage_figure_with_symmetry(
        self,
    ) -> go.Figure:
        logger.debug("update_coverage_figure_with_symmetry")
        qcones = self.qpane_cones.copy()
        faces: List[Any] = []
        for pane in qcones:  # x24 cone iters
            faces = faces + pane["qfaces"]  # 6 faces iters

        all_faces = []
        logger.debug("symmetry_operations")
        # print(self.symmetry_operations)
        for f in faces:
            for angle in self.angle_list:
                # Extract vertices and faces
                chi, phi, omega = angle["chi"], angle["phi"], angle["omega"]
                r = self.get_rotation_matrix(chi, phi, omega)
                for symop in self.symmetry_operations:
                    newf = []
                    for qpt in f:
                        # print(symop)
                        newpt = np.dot(symop, np.dot(r, qpt)).tolist()  # Convert numpy array to list
                        newf.append(newpt)
                    all_faces.append(newf)
        logger.debug("all_faces")
        logger.debug(len(all_faces))

        def get_face_plot(face: Any) -> go.Mesh3d:
            px = [face[0][0], face[1][0], face[2][0], face[3][0]]
            py = [face[0][1], face[1][1], face[2][1], face[3][1]]
            pz = [face[0][2], face[1][2], face[2][2], face[3][2]]
            pi = [0, 1]
            pj = [1, 2]
            pk = [2, 3]
            # Create a mesh
            face_plot = go.Mesh3d(x=px, y=py, z=pz, i=pi, j=pj, k=pk, color="lightblue", opacity=0.50, alphahull=0)
            return face_plot

        fig = go.Figure()
        for f in all_faces:
            face_plot = get_face_plot(f)
            fig.add_trace(face_plot)

        fig.update_layout(
            scene={"xaxis_title": "X Axis", "yaxis_title": "Y Axis", "zaxis_title": "Z Axis", "aspectmode": "data"},
            title="3D Polyhedron Visualization",
        )
        return fig
