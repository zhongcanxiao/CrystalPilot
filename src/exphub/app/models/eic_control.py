from pydantic import BaseModel, Field

from typing import List, Dict
import csv

from .EICClient import EICClient


class EICControlModel(BaseModel):

    class Config:
        arbitrary_types_allowed = True  # Allow arbitrary types like EICClient

    username: str = Field(
    default="test_name",
        min_length=1,
        title="User Name",
        description="Please provide the name of the user",
        examples=["user"],
    )
    token: str = Field(default="test_password", title="IPTS token")
    token_file: str = Field(default="/home/zx5/1-todo/6-hardware/code/token.txt", title="IPTS token")
    is_simulation: bool = Field(default=True, title="Simulation")
    IPTS_number: str = Field(default="34246", title="IPTS number")
    instrument_name: str = Field(default="TOPAZ", title="Instrument name", description="Name of the instrument",
                                 type="select", items=["TOPAZ", "CORELLI", "SEQUOIA", "HYSPEC", "ARCS", "VISION"])
    beamline: str = Field(default="bl12", title="Beamline", description="Name of the beamline")
    #eic_client: EICClient = Field(default_factory=EICClient, title="EIC Client")
    #eic_client: EICClient = Field(default_factory=EICClient, title="EIC Client")
    beamline_database: Dict = Field(default={
                                     "TOPAZ": "bl12",
                                     "CORELLI": "bl9"}
                                     , title="Beamline Database")

    eic_submission_success: bool = Field(default=False, title="EIC Submission Success")
    eic_submission_message: str = Field(default="No message", title="EIC Submission Message")
    eic_submission_scan_id: int = Field(default=-1, title="EIC Submission Scan ID")
    eic_submission_status: str = Field(default="No status", title="EIC Submission Status")

    def load_token(self, file_path: str) -> None:
        with open(file_path, mode='r') as tokenfile:
            self.token = tokenfile.read()
            print(self.token)
    def submit_eic(self,angleplan:List[Dict]) -> None:
        # Implement the submit logic here
        self.beamline = self.beamline_database[self.instrument_name]
        eic_client = EICClient(self.token, beamline=self.beamline, ipts_number=self.IPTS_number)
        eic_client.is_eic_enabled(print_results=True)

        desc="CrystalPilot Submission"
        if self.beamline == "bl12":
            headers=['Title','Comment','BL12:Mot:goniokm:phi','BL12:Mot:goniokm:omega','Wait For','Value','Or Time']
        rows=[[angle[key] for key in headers] for angle in angleplan]

        success, scan_id, response_data = eic_client.submit_table_scan( 
            parms={'run_mode': 0, 'headers': headers, 'rows': rows}, desc=desc, simulate_only=self.is_simulation)
        print(success, scan_id, response_data)
        self.eic_submission_success=success
        self.eic_submission_message=response_data['eic_response_message']
        self.eic_submission_scan_id=scan_id

        #self.eic_submission_status=eic_client.get_scan_status(scan_id=scan_id)
        #print(self.eic_submission_status)