from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.location.entities import CityEntity
from backend.domain.location.mappers import CityMapper
from backend.infrastructure.db.models import City


class AbstractCityRepository(
    IDBRepository[City, CityEntity, CityMapper],
    ABC,
):
    pass
