from backend.application.repos.abstract.ticket.analysis_meta import AbstractAnalysisMetaRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import AnalysisMetaEntity
from backend.domain.ticket.mappers import AnalysisMetaMapper
from backend.infrastructure.db.models import AnalysisMeta


class SqlAlchemyAnalysisMetaRepository(
    BaseSQLAlchemyRepo[AnalysisMeta, AnalysisMetaEntity, AnalysisMetaMapper],
    AbstractAnalysisMetaRepository,
):
    model = AnalysisMeta
    entity_type = AnalysisMetaEntity
    mapper = AnalysisMetaMapper
