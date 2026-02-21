from backend.application.repos.abstract.location.address import AbstractAddressRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.location.entities import AddressEntity
from backend.domain.location.mappers import AddressMapper
from backend.infrastructure.db.models import Address


class SqlAlchemyAddressRepository(
    BaseSQLAlchemyRepo[Address, AddressEntity, AddressMapper],
    AbstractAddressRepository,
):
    model = Address
    entity_type = AddressEntity
    mapper = AddressMapper
