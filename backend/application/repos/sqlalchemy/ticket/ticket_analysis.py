from backend.application.repos.abstract.ticket.ticket_analysis import AbstractTicketAnalysisRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import TicketAnalysisEntity
from backend.domain.ticket.mappers import TicketAnalysisMapper
from backend.infrastructure.db.models import TicketAnalysis


class SqlAlchemyTicketAnalysisRepository(
    BaseSQLAlchemyRepo[TicketAnalysis, TicketAnalysisEntity, TicketAnalysisMapper],
    AbstractTicketAnalysisRepository,
):
    model = TicketAnalysis
    entity_type = TicketAnalysisEntity
    mapper = TicketAnalysisMapper
