from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import GenderEntity
from backend.domain.ticket.mappers import GenderMapper
from backend.infrastructure.db.models import Gender


class AbstractGenderRepository(
    IDBRepository[Gender, GenderEntity, GenderMapper],
    ABC,
):
    pass
