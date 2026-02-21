from backend.application.repos.abstract.manager.manager import AbstractManagerRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.manager.entities import ManagerEntity
from backend.domain.manager.mappers import ManagerMapper
from backend.infrastructure.db.models import Manager


class SqlAlchemyManagerRepository(
    BaseSQLAlchemyRepo[Manager, ManagerEntity, ManagerMapper],
    AbstractManagerRepository,
):
    model = Manager
    entity_type = ManagerEntity
    mapper = ManagerMapper
