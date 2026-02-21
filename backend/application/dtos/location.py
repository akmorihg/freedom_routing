from typing import Optional
from pydantic import BaseModel


class CountryDTO(BaseModel):
    id_: int
    name: str


class RegionDTO(BaseModel):
    id_: int
    name: str
    country_id: int

    # relation
    country: Optional[CountryDTO] = None


class CityDTO(BaseModel):
    id_: int
    name: str
    region_id: int

    # relation
    region: Optional[RegionDTO] = None


class AddressDTO(BaseModel):
    id_: int
    country_id: int
    region_id: int
    city_id: int
    street: str
    home_number: str

    # relations
    country: Optional[CountryDTO] = None
    region: Optional[RegionDTO] = None
    city: Optional[CityDTO] = None


class OfficeDTO(BaseModel):
    id_: int
    city_id: Optional[int] = None
    address: str = ""

    # relation
    city: Optional[CityDTO] = None
