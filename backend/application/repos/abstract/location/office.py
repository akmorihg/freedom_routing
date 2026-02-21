from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.location.entities import OfficeEntity
from backend.domain.location.mappers import OfficeMapper
from backend.infrastructure.db.models import Office


class AbstractOfficeRepository(
    IDBRepository[Office, OfficeEntity, OfficeMapper],
    ABC,
):
    pass
