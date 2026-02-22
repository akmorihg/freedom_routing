from backend.application.repos.abstract.ticket.retries_used import AbstractRetriesUsedRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import RetriesUsedEntity
from backend.domain.ticket.mappers import RetriesUsedMapper
from backend.infrastructure.db.models import RetriesUsed


class SqlAlchemyRetriesUsedRepository(
    BaseSQLAlchemyRepo[RetriesUsed, RetriesUsedEntity, RetriesUsedMapper],
    AbstractRetriesUsedRepository,
):
    model = RetriesUsed
    entity_type = RetriesUsedEntity
    mapper = RetriesUsedMapper
