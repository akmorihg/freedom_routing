import logging
from typing import Optional, List, Any, Dict, Union

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from backend.core.dependency_injection.app_container import AppContainer
from backend.core.dependency_injection.repository_container import RepositoryContainer

from backend.core.base.entity import BaseEntity
from backend.domain.location.entities import (
    CountryEntity,
    RegionEntity,
    CityEntity,
    AddressEntity,
    OfficeEntity,
)

logger = logging.getLogger(__name__)

app_container = AppContainer()
location_router = APIRouter(prefix="/location", tags=["Location"])


# ============================================================
# Response DTOs (yours)
# ============================================================

class CountryDTO(BaseModel):
    id_: int
    name: str


class RegionDTO(BaseModel):
    id_: int
    name: str
    country_id: int
    country: Optional[CountryDTO] = None


class CityDTO(BaseModel):
    id_: int
    name: str
    region_id: int
    region: Optional[RegionDTO] = None


class AddressDTO(BaseModel):
    id_: int
    country_id: int
    region_id: int
    city_id: int
    street: str
    home_number: str
    country: Optional[CountryDTO] = None
    region: Optional[RegionDTO] = None
    city: Optional[CityDTO] = None


class OfficeDTO(BaseModel):
    id_: int
    city_id: Optional[int] = None
    address: str = ""
    city: Optional[CityDTO] = None


# ============================================================
# Request DTOs
# ============================================================

class CountryCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class CountryUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class RegionCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    country_id: int = Field(..., gt=0)


class RegionUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    country_id: Optional[int] = Field(None, gt=0)


class CityCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    region_id: int = Field(..., gt=0)


class CityUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    region_id: Optional[int] = Field(None, gt=0)


class AddressCreateDTO(BaseModel):
    country_id: int = Field(..., gt=0)
    region_id: int = Field(..., gt=0)
    city_id: int = Field(..., gt=0)
    street: str = Field(..., min_length=1, max_length=255)
    home_number: str = Field(..., min_length=1, max_length=50)


class AddressUpdateDTO(BaseModel):
    country_id: Optional[int] = Field(None, gt=0)
    region_id: Optional[int] = Field(None, gt=0)
    city_id: Optional[int] = Field(None, gt=0)
    street: Optional[str] = Field(None, min_length=1, max_length=255)
    home_number: Optional[str] = Field(None, min_length=1, max_length=50)


class OfficeCreateDTO(BaseModel):
    city_id: Optional[int] = Field(None, gt=0)
    address: str = Field(..., min_length=1, max_length=255)


class OfficeUpdateDTO(BaseModel):
    city_id: Optional[int] = Field(None, gt=0)
    address: Optional[str] = Field(None, min_length=1, max_length=255)


# ============================================================
# ✅ Helpers: dict/DTO -> Entity, and Entity -> DTO
# ============================================================

EntityOrDict = Union[BaseEntity, Dict[str, Any]]

def _to_entity(entity_cls, data: Union[BaseModel, Dict[str, Any], BaseEntity], *, id_: Any = None):
    """
    Makes your router compatible with:
      - Pydantic DTO (payload)
      - dict
      - already-built entity

    Repo needs EntityT.
    """
    if isinstance(data, BaseEntity):
        # ensure id if given
        if id_ is not None and getattr(data, "id_", None) is None:
            setattr(data, "id_", id_)
        return data

    if isinstance(data, BaseModel):
        d = data.model_dump(exclude_unset=True)
    else:
        d = dict(data)

    if id_ is not None:
        d["id_"] = id_

    return entity_cls(**d)


def _country_dto(e: CountryEntity) -> CountryDTO:
    return CountryDTO(id_=int(e.id_), name=e.name)


def _region_dto(e: RegionEntity) -> RegionDTO:
    return RegionDTO(id_=int(e.id_), name=e.name, country_id=e.country_id)


def _city_dto(e: CityEntity) -> CityDTO:
    return CityDTO(id_=int(e.id_), name=e.name, region_id=e.region_id)


def _address_dto(e: AddressEntity) -> AddressDTO:
    return AddressDTO(
        id_=int(e.id_),
        country_id=e.country_id,
        region_id=e.region_id,
        city_id=e.city_id,
        street=e.street,
        home_number=e.home_number,
    )


def _office_dto(e: OfficeEntity) -> OfficeDTO:
    return OfficeDTO(id_=int(e.id_), city_id=e.city_id, address=e.address)


# ============================================================
# COUNTRY CRUD (fixed)
# ============================================================

@location_router.post("/countries", response_model=CountryDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_country(
    repository_container: RepositoryContainer,
    payload: CountryCreateDTO,
):
    try:
        repo = repository_container.country_repo_
        entity = await repo.create(_to_entity(CountryEntity, payload))
        return _country_dto(entity)
    except Exception as e:
        logger.exception("Error creating country: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create country") from e


@location_router.get("/countries/{country_id}", response_model=CountryDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_country(
    repository_container: RepositoryContainer,
    country_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.country_repo_
        entity = await repo.get(country_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Country not found")
        return _country_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting country: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get country") from e


@location_router.get("/countries", response_model=List[CountryDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_countries(
    repository_container: RepositoryContainer,
):
    try:
        repo = repository_container.country_repo_
        entities = await repo.get_all()
        return [_country_dto(x) for x in entities]
    except Exception as e:
        logger.exception("Error listing countries: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list countries") from e


@location_router.put("/countries/{country_id}", response_model=CountryDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_country(
    repository_container: RepositoryContainer,
    payload: CountryUpdateDTO,
    country_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.country_repo_

        # ensure exists (optional but gives 404 instead of "created-like" merge)
        existing = await repo.get(country_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Country not found")

        entity = await repo.update(_to_entity(CountryEntity, payload, id_=country_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Country not found")
        return _country_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating country: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update country") from e


@location_router.delete("/countries/{country_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_country(
    repository_container: RepositoryContainer,
    country_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.country_repo_
        ok = await repo.delete(country_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Country not found")
        return {"deleted": True, "id_": country_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting country: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete country") from e


# ============================================================
# REGION CRUD (fixed + optional expand)
# ============================================================

@location_router.post("/regions", response_model=RegionDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_region(
    repository_container: RepositoryContainer,
    payload: RegionCreateDTO,
):
    try:
        repo = repository_container.region_repo_
        entity = await repo.create(_to_entity(RegionEntity, payload))
        return _region_dto(entity)
    except Exception as e:
        logger.exception("Error creating region: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create region") from e


@location_router.get("/regions/{region_id}", response_model=RegionDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_region(
    repository_container: RepositoryContainer,
    region_id: int = Path(..., gt=0),
    expand_country: bool = Query(False),
):
    try:
        repo = repository_container.region_repo_
        entity = await repo.get(region_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Region not found")

        dto = _region_dto(entity)
        if expand_country:
            c = await repository_container.country_repo_.get(dto.country_id)
            dto.country = _country_dto(c) if c else None
        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting region: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get region") from e


@location_router.get("/regions", response_model=List[RegionDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_regions(
    repository_container: RepositoryContainer,
    expand_country: bool = Query(False),
):
    try:
        repo = repository_container.region_repo_
        entities = await repo.get_all()
        dtos = [_region_dto(x) for x in entities]

        if expand_country:
            for dto in dtos:
                c = await repository_container.country_repo_.get(dto.country_id)
                dto.country = _country_dto(c) if c else None

        return dtos
    except Exception as e:
        logger.exception("Error listing regions: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list regions") from e


@location_router.put("/regions/{region_id}", response_model=RegionDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_region(
    repository_container: RepositoryContainer,
    payload: RegionUpdateDTO,
    region_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.region_repo_
        existing = await repo.get(region_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Region not found")

        entity = await repo.update(_to_entity(RegionEntity, payload, id_=region_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Region not found")
        return _region_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating region: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update region") from e


@location_router.delete("/regions/{region_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_region(
    repository_container: RepositoryContainer,
    region_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.region_repo_
        ok = await repo.delete(region_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Region not found")
        return {"deleted": True, "id_": region_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting region: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete region") from e


# ============================================================
# CITY CRUD (fixed + optional expand)
# ============================================================

@location_router.post("/cities", response_model=CityDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_city(
    repository_container: RepositoryContainer,
    payload: CityCreateDTO,
):
    try:
        repo = repository_container.city_repo_
        entity = await repo.create(_to_entity(CityEntity, payload))
        return _city_dto(entity)
    except Exception as e:
        logger.exception("Error creating city: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create city") from e


@location_router.get("/cities/{city_id}", response_model=CityDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_city(
    repository_container: RepositoryContainer,
    city_id: int = Path(..., gt=0),
    expand_region: bool = Query(False),
):
    try:
        repo = repository_container.city_repo_
        entity = await repo.get(city_id)
        if not entity:
            raise HTTPException(status_code=404, detail="City not found")

        dto = _city_dto(entity)
        if expand_region:
            r = await repository_container.region_repo_.get(dto.region_id)
            dto.region = _region_dto(r) if r else None
        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting city: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get city") from e


@location_router.get("/cities", response_model=List[CityDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_cities(
    repository_container: RepositoryContainer,
    expand_region: bool = Query(False),
):
    try:
        repo = repository_container.city_repo_
        entities = await repo.get_all()
        dtos = [_city_dto(x) for x in entities]
        if expand_region:
            for dto in dtos:
                r = await repository_container.region_repo_.get(dto.region_id)
                dto.region = _region_dto(r) if r else None
        return dtos
    except Exception as e:
        logger.exception("Error listing cities: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list cities") from e


@location_router.put("/cities/{city_id}", response_model=CityDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_city(
    repository_container: RepositoryContainer,
    payload: CityUpdateDTO,
    city_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.city_repo_
        existing = await repo.get(city_id)
        if not existing:
            raise HTTPException(status_code=404, detail="City not found")

        entity = await repo.update(_to_entity(CityEntity, payload, id_=city_id))
        if not entity:
            raise HTTPException(status_code=404, detail="City not found")
        return _city_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating city: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update city") from e


@location_router.delete("/cities/{city_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_city(
    repository_container: RepositoryContainer,
    city_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.city_repo_
        ok = await repo.delete(city_id)
        if not ok:
            raise HTTPException(status_code=404, detail="City not found")
        return {"deleted": True, "id_": city_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting city: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete city") from e


# ============================================================
# ADDRESS CRUD (fixed + optional expand)
# ============================================================

@location_router.post("/addresses", response_model=AddressDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_address(
    repository_container: RepositoryContainer,
    payload: AddressCreateDTO,
):
    try:
        repo = repository_container.address_repo_
        entity = await repo.create(_to_entity(AddressEntity, payload))
        return _address_dto(entity)
    except Exception as e:
        logger.exception("Error creating address: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create address") from e


@location_router.get("/addresses/{address_id}", response_model=AddressDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_address(
    repository_container: RepositoryContainer,
    address_id: int = Path(..., gt=0),
    expand: bool = Query(False, description="Include country/region/city relations"),
):
    try:
        repo = repository_container.address_repo_
        entity = await repo.get(address_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Address not found")

        dto = _address_dto(entity)

        if expand:
            c = await repository_container.country_repo_.get(dto.country_id)
            r = await repository_container.region_repo_.get(dto.region_id)
            ci = await repository_container.city_repo_.get(dto.city_id)
            dto.country = _country_dto(c) if c else None
            dto.region = _region_dto(r) if r else None
            dto.city = _city_dto(ci) if ci else None

        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting address: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get address") from e


@location_router.get("/addresses", response_model=List[AddressDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_addresses(
    repository_container: RepositoryContainer,
    expand: bool = Query(False),
):
    try:
        repo = repository_container.address_repo_
        entities = await repo.get_all()
        dtos = [_address_dto(x) for x in entities]

        if expand:
            for dto in dtos:
                c = await repository_container.country_repo_.get(dto.country_id)
                r = await repository_container.region_repo_.get(dto.region_id)
                ci = await repository_container.city_repo_.get(dto.city_id)
                dto.country = _country_dto(c) if c else None
                dto.region = _region_dto(r) if r else None
                dto.city = _city_dto(ci) if ci else None

        return dtos
    except Exception as e:
        logger.exception("Error listing addresses: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list addresses") from e


@location_router.put("/addresses/{address_id}", response_model=AddressDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_address(
    repository_container: RepositoryContainer,
    payload: AddressUpdateDTO,
    address_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.address_repo_
        existing = await repo.get(address_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Address not found")

        entity = await repo.update(_to_entity(AddressEntity, payload, id_=address_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Address not found")
        return _address_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating address: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update address") from e


@location_router.delete("/addresses/{address_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_address(
    repository_container: RepositoryContainer,
    address_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.address_repo_
        ok = await repo.delete(address_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Address not found")
        return {"deleted": True, "id_": address_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting address: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete address") from e


# ============================================================
# OFFICE CRUD (fixed + optional expand)
# ============================================================

@location_router.post("/offices", response_model=OfficeDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_office(
    repository_container: RepositoryContainer,
    payload: OfficeCreateDTO,
):
    try:
        repo = repository_container.office_repo_
        entity = await repo.create(_to_entity(OfficeEntity, payload))
        return _office_dto(entity)
    except Exception as e:
        logger.exception("Error creating office: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create office") from e


@location_router.get("/offices/{office_id}", response_model=OfficeDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_office(
    repository_container: RepositoryContainer,
    office_id: int = Path(..., gt=0),
    expand_city: bool = Query(False),
):
    try:
        repo = repository_container.office_repo_
        entity = await repo.get(office_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Office not found")

        dto = _office_dto(entity)

        if expand_city and dto.city_id:
            ci = await repository_container.city_repo_.get(dto.city_id)
            dto.city = _city_dto(ci) if ci else None

        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting office: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get office") from e


@location_router.get("/offices", response_model=List[OfficeDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_offices(
    repository_container: RepositoryContainer,
    expand_city: bool = Query(False),
):
    try:
        repo = repository_container.office_repo_
        entities = await repo.get_all()
        dtos = [_office_dto(x) for x in entities]

        if expand_city:
            for dto in dtos:
                if dto.city_id:
                    ci = await repository_container.city_repo_.get(dto.city_id)
                    dto.city = _city_dto(ci) if ci else None

        return dtos
    except Exception as e:
        logger.exception("Error listing offices: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list offices") from e


@location_router.put("/offices/{office_id}", response_model=OfficeDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_office(
    repository_container: RepositoryContainer,
    payload: OfficeUpdateDTO,
    office_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.office_repo_
        existing = await repo.get(office_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Office not found")

        entity = await repo.update(_to_entity(OfficeEntity, payload, id_=office_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Office not found")
        return _office_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating office: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update office") from e


@location_router.delete("/offices/{office_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_office(
    repository_container: RepositoryContainer,
    office_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.office_repo_
        ok = await repo.delete(office_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Office not found")
        return {"deleted": True, "id_": office_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting office: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete office") from e
