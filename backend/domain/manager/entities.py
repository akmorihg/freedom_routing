from dataclasses import dataclass
from typing import Optional, Union, Any, Dict

from backend.core.base.entity import BaseEntity


@dataclass
class ManagerPositionEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""
    hierarchy_level: int = 0


@dataclass
class ManagerEntity(BaseEntity):
    id_: Optional[int] = None
    position_id: Optional[int] = None
    city_id: Optional[int] = None
    in_progress_requests: int = 0


@dataclass
class SkillEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""


@dataclass
class ManagerSkillEntity(BaseEntity):
    manager_id: int = 0
    skill_id: int = 0

    @property
    def primary_key(self) -> Union[Any, Dict[str, Any]]:
        return {
            "manager_id": self.manager_id,
            "skill_id": self.skill_id,
        }
