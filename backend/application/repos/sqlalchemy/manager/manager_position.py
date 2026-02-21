from backend.application.repos.abstract.manager.manager_position import AbstractManagerPositionRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.manager.entities import ManagerPositionEntity
from backend.domain.manager.mappers import ManagerPositionMapper
from backend.infrastructure.db.models import ManagerPosition


class SqlAlchemyManagerPositionRepository(
    BaseSQLAlchemyRepo[ManagerPosition, ManagerPositionEntity, ManagerPositionMapper],
    AbstractManagerPositionRepository,
):
    model = ManagerPosition
    entity_type = ManagerPositionEntity
    mapper = ManagerPositionMapper
