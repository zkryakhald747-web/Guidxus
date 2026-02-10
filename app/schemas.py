from pydantic import BaseModel, Field, conint, constr, validator
from datetime import date
from typing import List, Optional, Literal

class CourseCreate(BaseModel):
    title: constr(strip_whitespace=True, min_length=3)
    description: Optional[str] = Field(default=None, max_length=1000)
    provider: Optional[str] = None
    provider_name: Optional[str] = None
    hours: float
    mode: Literal["in_person","online","hybrid"]
    start_date: date
    end_date: date
    capacity: conint(ge=1)
    registration_policy: Literal["open","approval","waitlist"]
    prevent_duplicates: bool = True
    attendance_verification: Literal["paper","qr"] = "paper"
    completion_threshold: conint(ge=0, le=100) = 80
    create_expected_roster: bool = True
    auto_issue_certificates: bool = True
    target_department_ids: List[int] = []

    @validator("end_date")
    def end_date_after_start(cls, v, values):
        if "start_date" in values and v < values["start_date"]:
            raise ValueError("end_date must be on/after start_date")
        return v