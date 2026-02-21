from backend.core.base.mapper import BaseMapper
from backend.domain.location.entities import CountryEntity, RegionEntity, CityEntity, AddressEntity, OfficeEntity
from backend.infrastructure.db.models import Office

from backend.infrastructure.db.models.geoposition import Country, Region, City, Address


class CountryMapper(BaseMapper[Country, CountryEntity]):
    model = Country
    entity = CountryEntity

    @classmethod
    def to_entity(cls, model: Country, lazy: bool = False) -> CountryEntity:
        return CountryEntity(
            id_=model.id,
            name=model.name,
        )

    @classmethod
    def to_model(cls, entity: CountryEntity, lazy: bool = False) -> Country:
        return Country(
            id=entity.id_,
            name=entity.name,
        )


class RegionMapper(BaseMapper[Region, RegionEntity]):
    model = Region
    entity = RegionEntity

    @classmethod
    def to_entity(cls, model: Region, lazy: bool = False) -> RegionEntity:
        return RegionEntity(
            id_=model.id,
            name=model.name,
            country_id=model.country_id,
        )

    @classmethod
    def to_model(cls, entity: RegionEntity, lazy: bool = False) -> Region:
        return Region(
            id=entity.id_,
            name=entity.name,
            country_id=entity.country_id,
        )


class CityMapper(BaseMapper[City, CityEntity]):
    model = City
    entity = CityEntity

    @classmethod
    def to_entity(cls, model: City, lazy: bool = False) -> CityEntity:
        return CityEntity(
            id_=model.id,
            name=model.name,
            region_id=model.region_id,
        )

    @classmethod
    def to_model(cls, entity: CityEntity, lazy: bool = False) -> City:
        return City(
            id=entity.id_,
            name=entity.name,
            region_id=entity.region_id,
        )


class AddressMapper(BaseMapper[Address, AddressEntity]):
    model = Address
    entity = AddressEntity

    @classmethod
    def to_entity(cls, model: Address, lazy: bool = False) -> AddressEntity:
        return AddressEntity(
            id_=model.id,
            country_id=model.country_id,
            region_id=model.region_id,
            city_id=model.city_id,
            street=model.street,
            home_number=model.home_number,
        )

    @classmethod
    def to_model(cls, entity: AddressEntity, lazy: bool = False) -> Address:
        return Address(
            id=entity.id_,
            country_id=entity.country_id,
            region_id=entity.region_id,
            city_id=entity.city_id,
            street=entity.street,
            home_number=entity.home_number,
        )


class OfficeMapper(BaseMapper[Office, OfficeEntity]):
    model = Office
    entity = OfficeEntity

    @classmethod
    def to_entity(cls, model: Office, lazy: bool = False) -> OfficeEntity:
        return OfficeEntity(
            id_=model.id,
            city_id=model.city_id,
            address=model.address,
        )

    @classmethod
    def to_model(cls, entity: OfficeEntity, lazy: bool = False) -> Office:
        return Office(
            id=entity.id_,
            city_id=entity.city_id,
            address=entity.address,
        )
