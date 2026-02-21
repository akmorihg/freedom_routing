from backend.application.repos.abstract.location.office import AbstractOfficeRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.location.entities import OfficeEntity
from backend.domain.location.mappers import OfficeMapper
from backend.infrastructure.db.models import Office


class SqlAlchemyOfficeRepository(
    BaseSQLAlchemyRepo[Office, OfficeEntity, OfficeMapper],
    AbstractOfficeRepository,
):
    model = Office
    entity_type = OfficeEntity
    mapper = OfficeMapper
