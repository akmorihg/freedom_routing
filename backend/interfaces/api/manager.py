import logging
from typing import Optional, List, Any, Dict, Union

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from backend.core.dependency_injection.app_container import AppContainer
from backend.core.dependency_injection.repository_container import RepositoryContainer

from backend.core.base.entity import BaseEntity
from backend.application.dtos.location import CityDTO  # your existing DTO
from backend.domain.location.entities import CityEntity  # if you need manual mapping

from backend.domain.manager.entities import (
    ManagerPositionEntity,
    ManagerEntity,
    SkillEntity,
    ManagerSkillEntity,
)

logger = logging.getLogger(__name__)

app_container = AppContainer()
manager_router = APIRouter(prefix="/managers", tags=["Managers"])


# ============================================================
# DTOs (your style)
# ============================================================

class ManagerPositionDTO(BaseModel):
    id_: int
    name: str
    hierarchy_level: int


class SkillDTO(BaseModel):
    id_: int
    name: str


class ManagerDTO(BaseModel):
    id_: int
    position_id: Optional[int] = None
    city_id: Optional[int] = None
    in_progress_requests: int = 0

    position: Optional[ManagerPositionDTO] = None
    city: Optional[CityDTO] = None
    skills: List[SkillDTO] = Field(default_factory=list)


# ============================================================
# Request DTOs
# ============================================================

class ManagerPositionCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    hierarchy_level: int = Field(..., ge=0)


class ManagerPositionUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    hierarchy_level: Optional[int] = Field(None, ge=0)


class SkillCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class SkillUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class ManagerCreateDTO(BaseModel):
    position_id: Optional[int] = Field(None, gt=0)
    city_id: Optional[int] = Field(None, gt=0)
    in_progress_requests: int = Field(0, ge=0)

    # like MessageDTO.media
    skill_ids: List[int] = Field(default_factory=list)


class ManagerUpdateDTO(BaseModel):
    position_id: Optional[int] = Field(None, gt=0)
    city_id: Optional[int] = Field(None, gt=0)
    in_progress_requests: Optional[int] = Field(None, ge=0)

    # if provided -> replace skills
    skill_ids: Optional[List[int]] = None


# ============================================================
# Helpers: dict/DTO -> Entity; Entity -> DTO
# ============================================================

def _to_entity(entity_cls, data: Union[BaseModel, Dict[str, Any], BaseEntity], *, id_: Any = None):
    if isinstance(data, BaseEntity):
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


def _position_dto(e: ManagerPositionEntity) -> ManagerPositionDTO:
    return ManagerPositionDTO(id_=int(e.id_), name=e.name, hierarchy_level=e.hierarchy_level)


def _skill_dto(e: SkillEntity) -> SkillDTO:
    return SkillDTO(id_=int(e.id_), name=e.name)


def _manager_dto(e: ManagerEntity) -> ManagerDTO:
    return ManagerDTO(
        id_=int(e.id_),
        position_id=e.position_id,
        city_id=e.city_id,
        in_progress_requests=e.in_progress_requests,
    )


async def _fill_manager_relations(
    repository_container: RepositoryContainer,
    dto: ManagerDTO,
    *,
    expand_position: bool,
    expand_city: bool,
    expand_skills: bool,
) -> None:
    if expand_position and dto.position_id:
        pos = await repository_container.manager_position_repo_.get(dto.position_id)
        dto.position = _position_dto(pos) if pos else None

    if expand_city and dto.city_id:
        city = await repository_container.city_repo_.get(dto.city_id)
        if city:
            # assuming your CityDTO is (id_, name, region_id, region optional)
            dto.city = CityDTO(id_=int(city.id_), name=city.name, region_id=city.region_id)

    if expand_skills:
        links = await repository_container.manager_skill_repo_.search(
            filters=[repository_container.manager_skill_repo_.primary_keys["manager_id"] == dto.id_]
        )
        # NOTE: above line depends on how your ManagerSkillRepo exposes model columns.
        # Safer fallback: get_all then filter in python (less efficient but works everywhere).
        if links is None:
            links = []

        skills: List[SkillDTO] = []
        for link in links:
            s = await repository_container.skill_repo_.get(link.skill_id)
            if s:
                skills.append(_skill_dto(s))
        dto.skills = skills


async def _load_manager_skill_links(
    repository_container: RepositoryContainer,
    manager_id: int,
) -> List[ManagerSkillEntity]:
    # Generic way that works with your BaseSQLAlchemyRepo API:
    # It doesn't support list-by-filter directly, so use get_all + python filter,
    # OR use search() if your concrete repo provides model columns / filters.

    # ✅ Guaranteed to work (but not optimal):
    all_links = await repository_container.manager_skill_repo_.get_all()
    return [x for x in all_links if x.manager_id == manager_id]


async def _replace_manager_skills(
    repository_container: RepositoryContainer,
    manager_id: int,
    new_skill_ids: List[int],
) -> None:
    link_repo = repository_container.manager_skill_repo_

    # delete old links
    links = await _load_manager_skill_links(repository_container, manager_id)
    if links:
        pks = [{"manager_id": x.manager_id, "skill_id": x.skill_id} for x in links]
        await link_repo.batch_delete(pks)

    # create new links
    for sid in new_skill_ids:
        await link_repo.create(ManagerSkillEntity(manager_id=manager_id, skill_id=sid))


# ============================================================
# MANAGER POSITION CRUD (fixed for entity-based repo)
# ============================================================

@manager_router.post("/positions", response_model=ManagerPositionDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_manager_position(
    repository_container: RepositoryContainer,
    payload: ManagerPositionCreateDTO,
):
    try:
        repo = repository_container.manager_position_repo_
        entity = await repo.create(_to_entity(ManagerPositionEntity, payload))
        return _position_dto(entity)
    except Exception as e:
        logger.exception("Error creating manager position: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create manager position") from e


@manager_router.get("/positions/{position_id}", response_model=ManagerPositionDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_manager_position(
    repository_container: RepositoryContainer,
    position_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.manager_position_repo_
        entity = await repo.get(position_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Manager position not found")
        return _position_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting manager position: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get manager position") from e


@manager_router.get("/positions", response_model=List[ManagerPositionDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_manager_positions(
    repository_container: RepositoryContainer,
):
    try:
        repo = repository_container.manager_position_repo_
        entities = await repo.get_all()
        return [_position_dto(x) for x in entities]
    except Exception as e:
        logger.exception("Error listing manager positions: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list manager positions") from e


@manager_router.put("/positions/{position_id}", response_model=ManagerPositionDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_manager_position(
    repository_container: RepositoryContainer,
    payload: ManagerPositionUpdateDTO,
    position_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.manager_position_repo_
        existing = await repo.get(position_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Manager position not found")

        entity = await repo.update(_to_entity(ManagerPositionEntity, payload, id_=position_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Manager position not found")
        return _position_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating manager position: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update manager position") from e


@manager_router.delete("/positions/{position_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_manager_position(
    repository_container: RepositoryContainer,
    position_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.manager_position_repo_
        ok = await repo.delete(position_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Manager position not found")
        return {"deleted": True, "id_": position_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting manager position: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete manager position") from e


# ============================================================
# SKILL CRUD (fixed)
# ============================================================

@manager_router.post("/skills", response_model=SkillDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_skill(
    repository_container: RepositoryContainer,
    payload: SkillCreateDTO,
):
    try:
        repo = repository_container.skill_repo_
        entity = await repo.create(_to_entity(SkillEntity, payload))
        return _skill_dto(entity)
    except Exception as e:
        logger.exception("Error creating skill: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create skill") from e


@manager_router.get("/skills/{skill_id}", response_model=SkillDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_skill(
    repository_container: RepositoryContainer,
    skill_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.skill_repo_
        entity = await repo.get(skill_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Skill not found")
        return _skill_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting skill: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get skill") from e


@manager_router.get("/skills", response_model=List[SkillDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_skills(
    repository_container: RepositoryContainer,
):
    try:
        repo = repository_container.skill_repo_
        entities = await repo.get_all()
        return [_skill_dto(x) for x in entities]
    except Exception as e:
        logger.exception("Error listing skills: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list skills") from e


@manager_router.put("/skills/{skill_id}", response_model=SkillDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_skill(
    repository_container: RepositoryContainer,
    payload: SkillUpdateDTO,
    skill_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.skill_repo_
        existing = await repo.get(skill_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Skill not found")

        entity = await repo.update(_to_entity(SkillEntity, payload, id_=skill_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Skill not found")
        return _skill_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating skill: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update skill") from e


@manager_router.delete("/skills/{skill_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_skill(
    repository_container: RepositoryContainer,
    skill_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.skill_repo_
        ok = await repo.delete(skill_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"deleted": True, "id_": skill_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting skill: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete skill") from e


# ============================================================
# MANAGER CRUD (fixed + skills via ManagerSkillEntity)
# ============================================================

@manager_router.post("", response_model=ManagerDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_manager(
    repository_container: RepositoryContainer,
    payload: ManagerCreateDTO,
    expand_position: bool = Query(False),
    expand_city: bool = Query(False),
    expand_skills: bool = Query(True),
):
    try:
        repo = repository_container.manager_repo_

        entity = await repo.create(_to_entity(ManagerEntity, payload.model_dump(exclude={"skill_ids"})))
        dto = _manager_dto(entity)

        if payload.skill_ids:
            await _replace_manager_skills(repository_container, dto.id_, payload.skill_ids)

        await _fill_manager_relations(
            repository_container,
            dto,
            expand_position=expand_position,
            expand_city=expand_city,
            expand_skills=expand_skills,
        )
        return dto
    except Exception as e:
        logger.exception("Error creating manager: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create manager") from e


@manager_router.get("/{manager_id}", response_model=ManagerDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_manager(
    repository_container: RepositoryContainer,
    manager_id: int = Path(..., gt=0),
    expand_position: bool = Query(False),
    expand_city: bool = Query(False),
    expand_skills: bool = Query(True),
):
    try:
        repo = repository_container.manager_repo_
        entity = await repo.get(manager_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Manager not found")

        dto = _manager_dto(entity)
        await _fill_manager_relations(
            repository_container,
            dto,
            expand_position=expand_position,
            expand_city=expand_city,
            expand_skills=expand_skills,
        )
        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting manager: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get manager") from e


@manager_router.get("", response_model=List[ManagerDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_managers(
    repository_container: RepositoryContainer,
    expand_position: bool = Query(False),
    expand_city: bool = Query(False),
    expand_skills: bool = Query(False),
):
    try:
        repo = repository_container.manager_repo_
        entities = await repo.get_all()
        dtos = [_manager_dto(x) for x in entities]

        if expand_position or expand_city or expand_skills:
            for dto in dtos:
                await _fill_manager_relations(
                    repository_container,
                    dto,
                    expand_position=expand_position,
                    expand_city=expand_city,
                    expand_skills=expand_skills,
                )

        return dtos
    except Exception as e:
        logger.exception("Error listing managers: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list managers") from e


@manager_router.put("/{manager_id}", response_model=ManagerDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_manager(
    repository_container: RepositoryContainer,
    payload: ManagerUpdateDTO,
    manager_id: int = Path(..., gt=0),
    expand_position: bool = Query(False),
    expand_city: bool = Query(False),
    expand_skills: bool = Query(True),
):
    try:
        repo = repository_container.manager_repo_
        existing = await repo.get(manager_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Manager not found")

        # update manager fields
        entity = await repo.update(_to_entity(ManagerEntity, payload.model_dump(exclude_unset=True, exclude={"skill_ids"}), id_=manager_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Manager not found")

        dto = _manager_dto(entity)

        # replace skills if skill_ids provided
        if payload.skill_ids is not None:
            await _replace_manager_skills(repository_container, manager_id, payload.skill_ids)

        await _fill_manager_relations(
            repository_container,
            dto,
            expand_position=expand_position,
            expand_city=expand_city,
            expand_skills=expand_skills,
        )
        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating manager: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update manager") from e


@manager_router.delete("/{manager_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_manager(
    repository_container: RepositoryContainer,
    manager_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.manager_repo_
        ok = await repo.delete(manager_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Manager not found")

        # cleanup join-table links (best effort)
        try:
            links = await _load_manager_skill_links(repository_container, manager_id)
            if links:
                pks = [{"manager_id": x.manager_id, "skill_id": x.skill_id} for x in links]
                await repository_container.manager_skill_repo_.batch_delete(pks)
        except Exception:
            pass

        return {"deleted": True, "id_": manager_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting manager: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete manager") from e
