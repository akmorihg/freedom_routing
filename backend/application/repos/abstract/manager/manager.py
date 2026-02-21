from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.manager.entities import ManagerEntity
from backend.domain.manager.mappers import ManagerMapper
from backend.infrastructure.db.models import Manager


class AbstractManagerRepository(
    IDBRepository[Manager, ManagerEntity, ManagerMapper],
    ABC,
):
    pass
