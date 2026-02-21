from backend.application.repos.abstract.ticket.ticket_attachment import AbstractTicketAttachmentRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import TicketAttachmentEntity
from backend.domain.ticket.mappers import TicketAttachmentMapper
from backend.infrastructure.db.models import TickerAttachments


class SqlAlchemyTicketAttachmentRepository(
    BaseSQLAlchemyRepo[TickerAttachments, TicketAttachmentEntity, TicketAttachmentMapper],
    AbstractTicketAttachmentRepository,
):
    model = TickerAttachments
    entity_type = TicketAttachmentEntity
    mapper = TicketAttachmentMapper
