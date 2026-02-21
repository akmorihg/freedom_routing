from backend.application.repos.abstract.ticket.ticket_assignment import AbstractTicketAssignmentRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import TicketAssignmentEntity
from backend.domain.ticket.mappers import TicketAssignmentMapper
from backend.infrastructure.db.models import TicketAssignment


class SqlAlchemyTicketAssignmentRepository(
    BaseSQLAlchemyRepo[TicketAssignment, TicketAssignmentEntity, TicketAssignmentMapper],
    AbstractTicketAssignmentRepository,
):
    model = TicketAssignment
    entity_type = TicketAssignmentEntity
    mapper = TicketAssignmentMapper
