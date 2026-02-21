from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.location.entities import CountryEntity
from backend.domain.location.mappers import CountryMapper
from backend.infrastructure.db.models import Country


class AbstractCountryRepository(
    IDBRepository[Country, CountryEntity, CountryMapper],
    ABC,
):
    pass
