from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.location.entities import RegionEntity
from backend.domain.location.mappers import RegionMapper
from backend.infrastructure.db.models import Region


class AbstractRegionRepository(
    IDBRepository[Region, RegionEntity, RegionMapper],
    ABC,
):
    pass
