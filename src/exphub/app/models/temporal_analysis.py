from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from typing import List, Dict


class TemporalAnalysisModel(BaseModel):
    headers: List[str] = Field(default=["Title", "Comment", "phi", "omega", "Wait For", "Value", "Or Time"])
    #headers: List[str] = Field(default=["Title", "Comment", "BL12:Mot:goniokm:phi", "BL12:Mot:goniokm:omega", "Wait For", "Value", "Or Time"])
    table_test: List[Dict] = Field(default=[{"title":"1","header":"h"}])
    def load_ap(self, file_path: str) -> None:
        print("load_ap")
        with open(file_path, mode='r') as apfile:
            print(apfile.read())
