from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import AttachmentEntity
from backend.domain.ticket.mappers import AttachmentMapper
from backend.infrastructure.db.models import Attachment


class AbstractAttachmentRepository(
    IDBRepository[Attachment, AttachmentEntity, AttachmentMapper],
    ABC,
):
    pass
