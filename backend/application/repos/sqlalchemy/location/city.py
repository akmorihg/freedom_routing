from backend.application.repos.abstract.location.city import AbstractCityRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.location.entities import CityEntity
from backend.domain.location.mappers import CityMapper
from backend.infrastructure.db.models import City


class SqlAlchemyCityRepository(
    BaseSQLAlchemyRepo[City, CityEntity, CityMapper],
    AbstractCityRepository,
):
    model = City
    entity_type = CityEntity
    mapper = CityMapper
