from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import AnalysisMetaEntity
from backend.domain.ticket.mappers import AnalysisMetaMapper
from backend.infrastructure.db.models import AnalysisMeta


class AbstractAnalysisMetaRepository(
    IDBRepository[AnalysisMeta, AnalysisMetaEntity, AnalysisMetaMapper],
    ABC,
):
    pass
