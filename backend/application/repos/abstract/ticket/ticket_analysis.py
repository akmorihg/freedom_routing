from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import TicketAnalysisEntity
from backend.domain.ticket.mappers import TicketAnalysisMapper
from backend.infrastructure.db.models import TicketAnalysis


class AbstractTicketAnalysisRepository(
    IDBRepository[TicketAnalysis, TicketAnalysisEntity, TicketAnalysisMapper],
    ABC,
):
    pass
