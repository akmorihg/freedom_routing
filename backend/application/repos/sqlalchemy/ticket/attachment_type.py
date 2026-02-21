from backend.application.repos.abstract.ticket.attachment_type import AbstractAttachmentTypeRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import AttachmentTypeEntity
from backend.domain.ticket.mappers import AttachmentTypeMapper
from backend.infrastructure.db.models import AttachmentType


class SqlAlchemyAttachmentTypeRepository(
    BaseSQLAlchemyRepo[AttachmentType, AttachmentTypeEntity, AttachmentTypeMapper],
    AbstractAttachmentTypeRepository,
):
    model = AttachmentType
    entity_type = AttachmentTypeEntity
    mapper = AttachmentTypeMapper
