from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import TicketAttachmentEntity
from backend.domain.ticket.mappers import TicketAttachmentMapper
from backend.infrastructure.db.models import TickerAttachments


class AbstractTicketAttachmentRepository(
    IDBRepository[TickerAttachments, TicketAttachmentEntity, TicketAttachmentMapper],
    ABC,
):
    pass
