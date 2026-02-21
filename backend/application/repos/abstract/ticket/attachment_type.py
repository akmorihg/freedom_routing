from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import AttachmentTypeEntity
from backend.domain.ticket.mappers import AttachmentTypeMapper
from backend.infrastructure.db.models import AttachmentType


class AbstractAttachmentTypeRepository(
    IDBRepository[AttachmentType, AttachmentTypeEntity, AttachmentTypeMapper],
    ABC,
):
    pass
