from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.manager.entities import ManagerSkillEntity
from backend.domain.manager.mappers import ManagerSkillMapper
from backend.infrastructure.db.models import ManagerSkills


class AbstractManagerSkillRepository(
    IDBRepository[ManagerSkills, ManagerSkillEntity, ManagerSkillMapper],
    ABC,
):
    pass
