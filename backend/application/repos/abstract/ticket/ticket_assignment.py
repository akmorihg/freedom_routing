from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import TicketAssignmentEntity
from backend.domain.ticket.mappers import TicketAssignmentMapper
from backend.infrastructure.db.models import TicketAssignment


class AbstractTicketAssignmentRepository(
    IDBRepository[TicketAssignment, TicketAssignmentEntity, TicketAssignmentMapper],
    ABC,
):
    pass
