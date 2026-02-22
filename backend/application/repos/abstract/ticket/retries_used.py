from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import RetriesUsedEntity
from backend.domain.ticket.mappers import RetriesUsedMapper
from backend.infrastructure.db.models import RetriesUsed


class AbstractRetriesUsedRepository(
    IDBRepository[RetriesUsed, RetriesUsedEntity, RetriesUsedMapper],
    ABC,
):
    pass
