from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.location.entities import AddressEntity
from backend.domain.location.mappers import AddressMapper
from backend.infrastructure.db.models import Address


class AbstractAddressRepository(
    IDBRepository[Address, AddressEntity, AddressMapper],
    ABC,
):
    pass
