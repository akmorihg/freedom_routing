from backend.application.repos.abstract.manager.skill import AbstractSkillRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.manager.entities import SkillEntity
from backend.domain.manager.mappers import SkillMapper
from backend.infrastructure.db.models import Skill


class SqlAlchemySkillRepository(
    BaseSQLAlchemyRepo[Skill, SkillEntity, SkillMapper],
    AbstractSkillRepository,
):
    model = Skill
    entity_type = SkillEntity
    mapper = SkillMapper
