from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.manager.entities import SkillEntity
from backend.domain.manager.mappers import SkillMapper
from backend.infrastructure.db.models import Skill


class AbstractSkillRepository(
    IDBRepository[Skill, SkillEntity, SkillMapper],
    ABC,
):
    pass
