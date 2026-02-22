from backend.application.repos.abstract.ticket.task_latencies import AbstractTaskLatenciesRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import TaskLatenciesEntity
from backend.domain.ticket.mappers import TaskLatenciesMapper
from backend.infrastructure.db.models import TaskLatencies


class SqlAlchemyTaskLatenciesRepository(
    BaseSQLAlchemyRepo[TaskLatencies, TaskLatenciesEntity, TaskLatenciesMapper],
    AbstractTaskLatenciesRepository,
):
    model = TaskLatencies
    entity_type = TaskLatenciesEntity
    mapper = TaskLatenciesMapper
