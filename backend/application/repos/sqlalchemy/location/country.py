from backend.application.repos.abstract.location.country import AbstractCountryRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.location.entities import CountryEntity
from backend.domain.location.mappers import CountryMapper
from backend.infrastructure.db.models import Country


class SqlAlchemyCountryRepository(
    BaseSQLAlchemyRepo[Country, CountryEntity, CountryMapper],
    AbstractCountryRepository,
):
    model = Country
    entity_type = CountryEntity
    mapper = CountryMapper
