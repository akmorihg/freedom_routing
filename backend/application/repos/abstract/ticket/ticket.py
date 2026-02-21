from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import TicketEntity
from backend.domain.ticket.mappers import TicketMapper
from backend.infrastructure.db.models import Ticket


class AbstractTicketRepository(
    IDBRepository[Ticket, TicketEntity, TicketMapper],
    ABC,
):
    pass
