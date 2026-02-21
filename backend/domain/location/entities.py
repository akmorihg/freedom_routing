from dataclasses import dataclass
from typing import Optional

from backend.core.base.entity import BaseEntity


@dataclass
class CountryEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""


@dataclass
class RegionEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""
    country_id: int = 0


@dataclass
class CityEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""
    region_id: int = 0


@dataclass
class AddressEntity(BaseEntity):
    id_: Optional[int] = None
    country_id: int = 0
    region_id: int = 0
    city_id: int = 0
    street: str = ""
    home_number: str = ""


@dataclass
class OfficeEntity(BaseEntity):
    id_: Optional[int] = None
    city_id: Optional[int] = None
    address: str = ""
