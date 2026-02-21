from backend.application.repos.abstract.location.region import AbstractRegionRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.location.entities import RegionEntity
from backend.domain.location.mappers import RegionMapper
from backend.infrastructure.db.models import Region


class SqlAlchemyRegionRepository(
    BaseSQLAlchemyRepo[Region, RegionEntity, RegionMapper],
    AbstractRegionRepository,
):
    model = Region
    entity_type = RegionEntity
    mapper = RegionMapper
