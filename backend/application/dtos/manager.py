from typing import Optional, List
from pydantic import BaseModel, Field

from backend.application.dtos.location import CityDTO

class ManagerPositionDTO(BaseModel):
    id_: int
    name: str
    hierarchy_level: int


class SkillDTO(BaseModel):
    id_: int
    name: str


class ManagerDTO(BaseModel):
    id_: int
    position_id: Optional[int] = None
    city_id: Optional[int] = None
    in_progress_requests: int = 0

    # relations (optional)
    position: Optional[ManagerPositionDTO] = None
    # if you already have CityDTO from previous answer, reuse it:
    city: Optional[CityDTO] = None

    # convenient relation: manager skills as objects
    skills: List[SkillDTO] = Field(default_factory=list)