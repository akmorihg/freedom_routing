from backend.application.repos.abstract.ticket.ticket import AbstractTicketRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import TicketEntity
from backend.domain.ticket.mappers import TicketMapper
from backend.infrastructure.db.models import Ticket


class SqlAlchemyTicketRepository(
    BaseSQLAlchemyRepo[Ticket, TicketEntity, TicketMapper],
    AbstractTicketRepository,
):
    model = Ticket
    entity_type = TicketEntity
    mapper = TicketMapper
