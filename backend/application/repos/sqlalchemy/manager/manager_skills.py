from backend.application.repos.abstract.manager.manager_skills import AbstractManagerSkillRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.manager.entities import ManagerSkillEntity
from backend.domain.manager.mappers import ManagerSkillMapper
from backend.infrastructure.db.models import ManagerSkills


class SqlAlchemyManagerSkillRepository(
    BaseSQLAlchemyRepo[ManagerSkills, ManagerSkillEntity, ManagerSkillMapper],
    AbstractManagerSkillRepository,
):
    model = ManagerSkills
    entity_type = ManagerSkillEntity
    mapper = ManagerSkillMapper
