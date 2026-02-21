from backend.application.repos.abstract.ticket.gender import AbstractGenderRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import GenderEntity
from backend.domain.ticket.mappers import GenderMapper
from backend.infrastructure.db.models import Gender


class SqlAlchemyGenderRepository(
    BaseSQLAlchemyRepo[Gender, GenderEntity, GenderMapper],
    AbstractGenderRepository,
):
    model = Gender
    entity_type = GenderEntity
    mapper = GenderMapper
