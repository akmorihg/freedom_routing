import logging
from datetime import date
from typing import Optional, List, Any, Dict, Union
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from backend.core.dependency_injection.app_container import AppContainer
from backend.core.dependency_injection.repository_container import RepositoryContainer

from backend.core.base.entity import BaseEntity

from backend.application.dtos.location import AddressDTO

from backend.domain.ticket.entities import (
    ClientSegmentEntity,
    GenderEntity,
    AttachmentTypeEntity,
    AttachmentEntity,
    TicketEntity,
    TicketAttachmentEntity,
)

logger = logging.getLogger(__name__)

app_container = AppContainer()
ticket_router = APIRouter(prefix="/tickets", tags=["Tickets"])


# ============================================================
# DTOs (your style)
# ============================================================

class ClientSegmentDTO(BaseModel):
    id_: int
    name: str
    priority: int = 0


class GenderDTO(BaseModel):
    id_: int
    name: str


class AttachmentTypeDTO(BaseModel):
    id_: int
    name: str


class AttachmentDTO(BaseModel):
    id_: int
    type_id: int
    key: str

    type: Optional[AttachmentTypeDTO] = None
    url: Optional[str] = None


class TicketDTO(BaseModel):
    id_: UUID
    gender_id: int
    date_of_birth: date
    description: str = ""
    segment_id: int = 0
    address_id: int = 0

    gender: Optional[GenderDTO] = None
    segment: Optional[ClientSegmentDTO] = None
    address: Optional[AddressDTO] = None
    attachments: List[AttachmentDTO] = Field(default_factory=list)


# ============================================================
# Request DTOs
# ============================================================

class ClientSegmentCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    priority: int = Field(0, ge=0)


class ClientSegmentUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    priority: Optional[int] = Field(None, ge=0)


class GenderCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class GenderUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class AttachmentTypeCreateDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class AttachmentTypeUpdateDTO(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class AttachmentCreateDTO(BaseModel):
    type_id: int = Field(..., gt=0)
    key: str = Field(..., min_length=1, max_length=1024)


class AttachmentUpdateDTO(BaseModel):
    type_id: Optional[int] = Field(None, gt=0)
    key: Optional[str] = Field(None, min_length=1, max_length=1024)


class TicketCreateDTO(BaseModel):
    # if you don't want client to send UUID, you can omit this and generate it here
    id_: Optional[UUID] = None

    gender_id: int = Field(..., gt=0)
    date_of_birth: date
    description: str = Field("", max_length=5000)
    segment_id: int = Field(..., gt=0)
    address_id: int = Field(..., gt=0)

    attachment_ids: List[int] = Field(default_factory=list)


class TicketUpdateDTO(BaseModel):
    gender_id: Optional[int] = Field(None, gt=0)
    date_of_birth: Optional[date] = None
    description: Optional[str] = Field(None, max_length=5000)
    segment_id: Optional[int] = Field(None, gt=0)
    address_id: Optional[int] = Field(None, gt=0)

    # if provided -> replace attachments
    attachment_ids: Optional[List[int]] = None


class TicketAddAttachmentsDTO(BaseModel):
    attachment_ids: List[int] = Field(default_factory=list)


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


def _segment_dto(e: ClientSegmentEntity) -> ClientSegmentDTO:
    return ClientSegmentDTO(id_=int(e.id_), name=e.name, priority=e.priority)


def _gender_dto(e: GenderEntity) -> GenderDTO:
    return GenderDTO(id_=int(e.id_), name=e.name)


def _attachment_type_dto(e: AttachmentTypeEntity) -> AttachmentTypeDTO:
    return AttachmentTypeDTO(id_=int(e.id_), name=e.name)


def _attachment_dto(e: AttachmentEntity) -> AttachmentDTO:
    return AttachmentDTO(id_=int(e.id_), type_id=e.type_id, key=e.key)


def _ticket_dto(e: TicketEntity) -> TicketDTO:
    return TicketDTO(
        id_=e.id_,
        gender_id=e.gender_id,
        date_of_birth=e.date_of_birth,
        description=e.description,
        segment_id=e.segment_id,
        address_id=e.address_id,
    )


async def _load_ticket_attachment_links(
    repository_container: RepositoryContainer,
    ticket_id: UUID,
) -> List[TicketAttachmentEntity]:
    # ✅ Guaranteed to work with BaseSQLAlchemyRepo: get_all() + python filter
    all_links = await repository_container.ticket_attachment_repo_.get_all()
    return [x for x in all_links if x.ticket_id == ticket_id]


async def _replace_ticket_attachments(
    repository_container: RepositoryContainer,
    ticket_id: UUID,
    new_attachment_ids: List[int],
) -> None:
    link_repo = repository_container.ticket_attachment_repo_

    # delete old links
    links = await _load_ticket_attachment_links(repository_container, ticket_id)
    if links:
        pks = [{"ticket_id": x.ticket_id, "attachment_id": x.attachment_id} for x in links]
        await link_repo.batch_delete(pks)

    # create new links
    for aid in new_attachment_ids:
        await link_repo.create(TicketAttachmentEntity(ticket_id=ticket_id, attachment_id=aid))


async def _fill_ticket_relations(
    repository_container: RepositoryContainer,
    dto: TicketDTO,
    *,
    expand: bool,
    include_attachments: bool,
    include_attachment_type: bool,
    include_attachment_url: bool,
    attachment_bucket: str,
    attachment_url_ttl: int,
) -> None:
    if expand:
        g = await repository_container.gender_repo_.get(dto.gender_id)
        s = await repository_container.client_segment_repo_.get(dto.segment_id)
        a = await repository_container.address_repo_.get(dto.address_id)

        dto.gender = _gender_dto(g) if g else None
        dto.segment = _segment_dto(s) if s else None
        if a:
            dto.address = AddressDTO(
                id_=int(a.id_),
                country_id=a.country_id,
                region_id=a.region_id,
                city_id=a.city_id,
                street=a.street,
                home_number=a.home_number,
            )

    if include_attachments:
        links = await _load_ticket_attachment_links(repository_container, dto.id_)

        att_repo = repository_container.attachment_repo_
        att_type_repo = repository_container.attachment_type_repo_
        sf_repo = repository_container.static_file_repo_

        attachments: List[AttachmentDTO] = []
        for link in links:
            att = await att_repo.get(link.attachment_id)
            if not att:
                continue

            adto = _attachment_dto(att)

            if include_attachment_type:
                t = await att_type_repo.get(adto.type_id)
                adto.type = _attachment_type_dto(t) if t else None

            if include_attachment_url:
                # requires your MiniIORepository to implement get_presigned_url(...)
                try:
                    adto.url = await sf_repo.get_presigned_url(
                        bucket=attachment_bucket,
                        key=adto.key,
                        expires_in=attachment_url_ttl,
                        method="get_object",
                    )
                except Exception:
                    adto.url = None

            attachments.append(adto)

        dto.attachments = attachments


# ============================================================
# CLIENT SEGMENT CRUD
# ============================================================

@ticket_router.post("/segments", response_model=ClientSegmentDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_client_segment(
    repository_container: RepositoryContainer,
    payload: ClientSegmentCreateDTO,
):
    try:
        repo = repository_container.client_segment_repo_
        entity = await repo.create(_to_entity(ClientSegmentEntity, payload))
        return _segment_dto(entity)
    except Exception as e:
        logger.exception("Error creating client segment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create client segment") from e


@ticket_router.get("/segments/{segment_id}", response_model=ClientSegmentDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_client_segment(
    repository_container: RepositoryContainer,
    segment_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.client_segment_repo_
        entity = await repo.get(segment_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Client segment not found")
        return _segment_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting client segment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get client segment") from e


@ticket_router.get("/segments", response_model=List[ClientSegmentDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_client_segments(
    repository_container: RepositoryContainer,
):
    try:
        entities = await repository_container.client_segment_repo_.get_all()
        return [_segment_dto(x) for x in entities]
    except Exception as e:
        logger.exception("Error listing client segments: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list client segments") from e


@ticket_router.put("/segments/{segment_id}", response_model=ClientSegmentDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_client_segment(
    repository_container: RepositoryContainer,
    payload: ClientSegmentUpdateDTO,
    segment_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.client_segment_repo_
        existing = await repo.get(segment_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Client segment not found")

        entity = await repo.update(_to_entity(ClientSegmentEntity, payload, id_=segment_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Client segment not found")
        return _segment_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating client segment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update client segment") from e


@ticket_router.delete("/segments/{segment_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_client_segment(
    repository_container: RepositoryContainer,
    segment_id: int = Path(..., gt=0),
):
    try:
        ok = await repository_container.client_segment_repo_.delete(segment_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Client segment not found")
        return {"deleted": True, "id_": segment_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting client segment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete client segment") from e


# ============================================================
# GENDER CRUD
# ============================================================

@ticket_router.post("/genders", response_model=GenderDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_gender(
    repository_container: RepositoryContainer,
    payload: GenderCreateDTO,
):
    try:
        repo = repository_container.gender_repo_
        entity = await repo.create(_to_entity(GenderEntity, payload))
        return _gender_dto(entity)
    except Exception as e:
        logger.exception("Error creating gender: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create gender") from e


@ticket_router.get("/genders/{gender_id}", response_model=GenderDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_gender(
    repository_container: RepositoryContainer,
    gender_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.gender_repo_
        entity = await repo.get(gender_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Gender not found")
        return _gender_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting gender: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get gender") from e


@ticket_router.get("/genders", response_model=List[GenderDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_genders(
    repository_container: RepositoryContainer,
):
    try:
        entities = await repository_container.gender_repo_.get_all()
        return [_gender_dto(x) for x in entities]
    except Exception as e:
        logger.exception("Error listing genders: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list genders") from e


@ticket_router.put("/genders/{gender_id}", response_model=GenderDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_gender(
    repository_container: RepositoryContainer,
    payload: GenderUpdateDTO,
    gender_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.gender_repo_
        existing = await repo.get(gender_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Gender not found")

        entity = await repo.update(_to_entity(GenderEntity, payload, id_=gender_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Gender not found")
        return _gender_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating gender: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update gender") from e


@ticket_router.delete("/genders/{gender_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_gender(
    repository_container: RepositoryContainer,
    gender_id: int = Path(..., gt=0),
):
    try:
        ok = await repository_container.gender_repo_.delete(gender_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Gender not found")
        return {"deleted": True, "id_": gender_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting gender: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete gender") from e


# ============================================================
# ATTACHMENT TYPE CRUD
# ============================================================

@ticket_router.post("/attachment-types", response_model=AttachmentTypeDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_attachment_type(
    repository_container: RepositoryContainer,
    payload: AttachmentTypeCreateDTO,
):
    try:
        repo = repository_container.attachment_type_repo_
        entity = await repo.create(_to_entity(AttachmentTypeEntity, payload))
        return _attachment_type_dto(entity)
    except Exception as e:
        logger.exception("Error creating attachment type: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create attachment type") from e


@ticket_router.get("/attachment-types/{type_id}", response_model=AttachmentTypeDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_attachment_type(
    repository_container: RepositoryContainer,
    type_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.attachment_type_repo_
        entity = await repo.get(type_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Attachment type not found")
        return _attachment_type_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting attachment type: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get attachment type") from e


@ticket_router.get("/attachment-types", response_model=List[AttachmentTypeDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_attachment_types(
    repository_container: RepositoryContainer,
):
    try:
        entities = await repository_container.attachment_type_repo_.get_all()
        return [_attachment_type_dto(x) for x in entities]
    except Exception as e:
        logger.exception("Error listing attachment types: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list attachment types") from e


@ticket_router.put("/attachment-types/{type_id}", response_model=AttachmentTypeDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_attachment_type(
    repository_container: RepositoryContainer,
    payload: AttachmentTypeUpdateDTO,
    type_id: int = Path(..., gt=0),
):
    try:
        repo = repository_container.attachment_type_repo_
        existing = await repo.get(type_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Attachment type not found")

        entity = await repo.update(_to_entity(AttachmentTypeEntity, payload, id_=type_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Attachment type not found")
        return _attachment_type_dto(entity)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating attachment type: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update attachment type") from e


@ticket_router.delete("/attachment-types/{type_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_attachment_type(
    repository_container: RepositoryContainer,
    type_id: int = Path(..., gt=0),
):
    try:
        ok = await repository_container.attachment_type_repo_.delete(type_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Attachment type not found")
        return {"deleted": True, "id_": type_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting attachment type: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete attachment type") from e


# ============================================================
# ATTACHMENT CRUD (fixed)
# ============================================================

@ticket_router.post("/attachments", response_model=AttachmentDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_attachment(
    repository_container: RepositoryContainer,
    payload: AttachmentCreateDTO,
    expand_type: bool = Query(False),
    include_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        repo = repository_container.attachment_repo_
        entity = await repo.create(_to_entity(AttachmentEntity, payload))
        dto = _attachment_dto(entity)

        if expand_type:
            t = await repository_container.attachment_type_repo_.get(dto.type_id)
            dto.type = _attachment_type_dto(t) if t else None

        if include_url:
            try:
                dto.url = await repository_container.static_file_repo_.get_presigned_url(
                    bucket=attachment_bucket,
                    key=dto.key,
                    expires_in=attachment_url_ttl,
                    method="get_object",
                )
            except Exception:
                dto.url = None

        return dto
    except Exception as e:
        logger.exception("Error creating attachment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create attachment") from e


@ticket_router.get("/attachments/{attachment_id}", response_model=AttachmentDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_attachment(
    repository_container: RepositoryContainer,
    attachment_id: int = Path(..., gt=0),
    expand_type: bool = Query(False),
    include_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        entity = await repository_container.attachment_repo_.get(attachment_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Attachment not found")

        dto = _attachment_dto(entity)

        if expand_type:
            t = await repository_container.attachment_type_repo_.get(dto.type_id)
            dto.type = _attachment_type_dto(t) if t else None

        if include_url:
            try:
                dto.url = await repository_container.static_file_repo_.get_presigned_url(
                    bucket=attachment_bucket,
                    key=dto.key,
                    expires_in=attachment_url_ttl,
                    method="get_object",
                )
            except Exception:
                dto.url = None

        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting attachment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get attachment") from e


@ticket_router.get("/attachments", response_model=List[AttachmentDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_attachments(
    repository_container: RepositoryContainer,
    expand_type: bool = Query(False),
    include_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        entities = await repository_container.attachment_repo_.get_all()
        dtos = [_attachment_dto(x) for x in entities]

        if expand_type:
            for dto in dtos:
                t = await repository_container.attachment_type_repo_.get(dto.type_id)
                dto.type = _attachment_type_dto(t) if t else None

        if include_url:
            for dto in dtos:
                try:
                    dto.url = await repository_container.static_file_repo_.get_presigned_url(
                        bucket=attachment_bucket,
                        key=dto.key,
                        expires_in=attachment_url_ttl,
                        method="get_object",
                    )
                except Exception:
                    dto.url = None

        return dtos
    except Exception as e:
        logger.exception("Error listing attachments: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list attachments") from e


@ticket_router.put("/attachments/{attachment_id}", response_model=AttachmentDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_attachment(
    repository_container: RepositoryContainer,
    payload: AttachmentUpdateDTO,
    attachment_id: int = Path(..., gt=0),
    expand_type: bool = Query(False),
    include_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        repo = repository_container.attachment_repo_
        existing = await repo.get(attachment_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Attachment not found")

        entity = await repo.update(_to_entity(AttachmentEntity, payload, id_=attachment_id))
        if not entity:
            raise HTTPException(status_code=404, detail="Attachment not found")

        dto = _attachment_dto(entity)

        if expand_type:
            t = await repository_container.attachment_type_repo_.get(dto.type_id)
            dto.type = _attachment_type_dto(t) if t else None

        if include_url:
            try:
                dto.url = await repository_container.static_file_repo_.get_presigned_url(
                    bucket=attachment_bucket,
                    key=dto.key,
                    expires_in=attachment_url_ttl,
                    method="get_object",
                )
            except Exception:
                dto.url = None

        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating attachment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update attachment") from e


@ticket_router.delete("/attachments/{attachment_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_attachment(
    repository_container: RepositoryContainer,
    attachment_id: int = Path(..., gt=0),
):
    try:
        ok = await repository_container.attachment_repo_.delete(attachment_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Attachment not found")
        return {"deleted": True, "id_": attachment_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting attachment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete attachment") from e


# ============================================================
# TICKET CRUD (fixed + optional expand + attachments)
# ============================================================

@ticket_router.post("", response_model=TicketDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_ticket(
    repository_container: RepositoryContainer,
    payload: TicketCreateDTO,
    expand: bool = Query(False),
    include_attachments: bool = Query(True),
    include_attachment_type: bool = Query(False),
    include_attachment_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        repo = repository_container.ticket_repo_

        ticket_id = payload.id_ or uuid4()
        ticket_entity = TicketEntity(
            id_=ticket_id,
            gender_id=payload.gender_id,
            date_of_birth=payload.date_of_birth,
            description=payload.description,
            segment_id=payload.segment_id,
            address_id=payload.address_id,
        )
        created = await repo.create(ticket_entity)

        if payload.attachment_ids:
            await _replace_ticket_attachments(repository_container, created.id_, payload.attachment_ids)

        dto = _ticket_dto(created)
        await _fill_ticket_relations(
            repository_container,
            dto,
            expand=expand,
            include_attachments=include_attachments,
            include_attachment_type=include_attachment_type,
            include_attachment_url=include_attachment_url,
            attachment_bucket=attachment_bucket,
            attachment_url_ttl=attachment_url_ttl,
        )
        return dto
    except Exception as e:
        logger.exception("Error creating ticket: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create ticket") from e


@ticket_router.get("/{ticket_id}", response_model=TicketDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_ticket(
    repository_container: RepositoryContainer,
    ticket_id: UUID,
    expand: bool = Query(False),
    include_attachments: bool = Query(True),
    include_attachment_type: bool = Query(False),
    include_attachment_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        entity = await repository_container.ticket_repo_.get(ticket_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Ticket not found")

        dto = _ticket_dto(entity)
        await _fill_ticket_relations(
            repository_container,
            dto,
            expand=expand,
            include_attachments=include_attachments,
            include_attachment_type=include_attachment_type,
            include_attachment_url=include_attachment_url,
            attachment_bucket=attachment_bucket,
            attachment_url_ttl=attachment_url_ttl,
        )
        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting ticket: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get ticket") from e


@ticket_router.get("", response_model=List[TicketDTO])
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def list_tickets(
    repository_container: RepositoryContainer,
    expand: bool = Query(False),
    include_attachments: bool = Query(False),
    include_attachment_type: bool = Query(False),
    include_attachment_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        entities = await repository_container.ticket_repo_.get_all()
        dtos: List[TicketDTO] = []
        for e in entities:
            dto = _ticket_dto(e)
            await _fill_ticket_relations(
                repository_container,
                dto,
                expand=expand,
                include_attachments=include_attachments,
                include_attachment_type=include_attachment_type,
                include_attachment_url=include_attachment_url,
                attachment_bucket=attachment_bucket,
                attachment_url_ttl=attachment_url_ttl,
            )
            dtos.append(dto)
        return dtos
    except Exception as e:
        logger.exception("Error listing tickets: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list tickets") from e


@ticket_router.put("/{ticket_id}", response_model=TicketDTO)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_ticket(
    repository_container: RepositoryContainer,
    payload: TicketUpdateDTO,
    ticket_id: UUID,
    expand: bool = Query(False),
    include_attachments: bool = Query(True),
    include_attachment_type: bool = Query(False),
    include_attachment_url: bool = Query(False),
    attachment_bucket: str = Query("static"),
    attachment_url_ttl: int = Query(3600, ge=1, le=7 * 24 * 3600),
):
    try:
        repo = repository_container.ticket_repo_
        existing = await repo.get(ticket_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # merge update fields into entity
        updated_entity = TicketEntity(
            id_=ticket_id,
            gender_id=payload.gender_id if payload.gender_id is not None else existing.gender_id,
            date_of_birth=payload.date_of_birth if payload.date_of_birth is not None else existing.date_of_birth,
            description=payload.description if payload.description is not None else existing.description,
            segment_id=payload.segment_id if payload.segment_id is not None else existing.segment_id,
            address_id=payload.address_id if payload.address_id is not None else existing.address_id,
        )

        updated = await repo.update(updated_entity)
        if not updated:
            raise HTTPException(status_code=404, detail="Ticket not found")

        if payload.attachment_ids is not None:
            await _replace_ticket_attachments(repository_container, ticket_id, payload.attachment_ids)

        dto = _ticket_dto(updated)
        await _fill_ticket_relations(
            repository_container,
            dto,
            expand=expand,
            include_attachments=include_attachments,
            include_attachment_type=include_attachment_type,
            include_attachment_url=include_attachment_url,
            attachment_bucket=attachment_bucket,
            attachment_url_ttl=attachment_url_ttl,
        )
        return dto
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating ticket: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update ticket") from e


@ticket_router.delete("/{ticket_id}", response_model=dict)
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_ticket(
    repository_container: RepositoryContainer,
    ticket_id: UUID,
):
    try:
        repo = repository_container.ticket_repo_
        ok = await repo.delete(ticket_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # best-effort cleanup join-table links
        try:
            links = await _load_ticket_attachment_links(repository_container, ticket_id)
            if links:
                pks = [{"ticket_id": x.ticket_id, "attachment_id": x.attachment_id} for x in links]
                await repository_container.ticket_attachment_repo_.batch_delete(pks)
        except Exception:
            pass

        return {"deleted": True, "id_": str(ticket_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting ticket: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete ticket") from e