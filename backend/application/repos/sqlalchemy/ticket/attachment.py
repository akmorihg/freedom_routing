from backend.application.repos.abstract.ticket.attachment import AbstractAttachmentRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import AttachmentEntity
from backend.domain.ticket.mappers import AttachmentMapper
from backend.infrastructure.db.models import Attachment


class SqlAlchemyAttachmentRepository(
    BaseSQLAlchemyRepo[Attachment, AttachmentEntity, AttachmentMapper],
    AbstractAttachmentRepository,
):
    model = Attachment
    entity_type = AttachmentEntity
    mapper = AttachmentMapper
