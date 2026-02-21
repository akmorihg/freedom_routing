from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.manager.entities import ManagerPositionEntity
from backend.domain.manager.mappers import ManagerPositionMapper
from backend.infrastructure.db.models import ManagerPosition


class AbstractManagerPositionRepository(
    IDBRepository[ManagerPosition, ManagerPositionEntity, ManagerPositionMapper],
    ABC,
):
    pass
