from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import TaskLatenciesEntity
from backend.domain.ticket.mappers import TaskLatenciesMapper
from backend.infrastructure.db.models import TaskLatencies


class AbstractTaskLatenciesRepository(
    IDBRepository[TaskLatencies, TaskLatenciesEntity, TaskLatenciesMapper],
    ABC,
):
    pass
