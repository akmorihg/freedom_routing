from backend.core.base.mapper import BaseMapper
from backend.domain.ticket.entities import (
    AttachmentTypeEntity,
    AttachmentEntity,
    TicketEntity,
    TicketAnalysisEntity,
    TicketAttachmentEntity,
    TicketAssignmentEntity,
    GenderEntity,
    ClientSegmentEntity,
)
from backend.infrastructure.db.models import (
    Ticket,
    TicketAnalysis,
    TickerAttachments,
    TicketAssignment,
    Gender,
    ClientSegment,
)
from backend.infrastructure.db.models.attachment import AttachmentType, Attachment


class ClientSegmentMapper(BaseMapper[ClientSegment, ClientSegmentEntity]):
    model = ClientSegment
    entity = ClientSegmentEntity

    @classmethod
    def to_entity(cls, model: ClientSegment, lazy: bool = False) -> ClientSegmentEntity:
        return ClientSegmentEntity(
            id_=model.id,
            name=model.name,
            priority=model.priority,
        )

    @classmethod
    def to_model(cls, entity: ClientSegmentEntity, lazy: bool = False) -> ClientSegment:
        return ClientSegment(
            id=entity.id_,
            name=entity.name,
            priority=entity.priority,
        )


class GenderMapper(BaseMapper[Gender, GenderEntity]):
    model = Gender
    entity = GenderEntity

    @classmethod
    def to_entity(cls, model: Gender, lazy: bool = False) -> GenderEntity:
        return GenderEntity(
            id_=model.id,
            name=model.name,
        )

    @classmethod
    def to_model(cls, entity: GenderEntity, lazy: bool = False) -> Gender:
        return Gender(
            id=entity.id_,
            name=entity.name,
        )


class AttachmentTypeMapper(BaseMapper[AttachmentType, AttachmentTypeEntity]):
    model = AttachmentType
    entity = AttachmentTypeEntity

    @classmethod
    def to_entity(cls, model: AttachmentType, lazy: bool = False) -> AttachmentTypeEntity:
        return AttachmentTypeEntity(
            id_=model.id,
            name=model.name,
        )

    @classmethod
    def to_model(cls, entity: AttachmentTypeEntity, lazy: bool = False) -> AttachmentType:
        return AttachmentType(
            id=entity.id_,
            name=entity.name,
        )


class AttachmentMapper(BaseMapper[Attachment, AttachmentEntity]):
    model = Attachment
    entity = AttachmentEntity

    @classmethod
    def to_entity(cls, model: Attachment, lazy: bool = False) -> AttachmentEntity:
        return AttachmentEntity(
            id_=model.id,
            type_id=model.type,
            key=model.key,
        )

    @classmethod
    def to_model(cls, entity: AttachmentEntity, lazy: bool = False) -> Attachment:
        return Attachment(
            id=entity.id_,
            type=entity.type_id,
            key=entity.key,
        )


class TicketMapper(BaseMapper[Ticket, TicketEntity]):
    model = Ticket
    entity = TicketEntity

    @classmethod
    def to_entity(cls, model: Ticket, lazy: bool = False) -> TicketEntity:
        return TicketEntity(
            id_=model.id,
            gender_id=model.gender_id,
            date_of_birth=model.date_of_birth,
            description=model.description,
            segment_id=model.segment_id,
            address_id=model.address_id,
        )

    @classmethod
    def to_model(cls, entity: TicketEntity, lazy: bool = False) -> Ticket:
        return Ticket(
            id=entity.id_,
            gender_id=entity.gender_id,
            date_of_birth=entity.date_of_birth,
            description=entity.description,
            segment_id=entity.segment_id,
            address_id=entity.address_id,
        )


class TicketAnalysisMapper(BaseMapper[TicketAnalysis, TicketAnalysisEntity]):
    model = TicketAnalysis
    entity = TicketAnalysisEntity

    @classmethod
    def to_entity(cls, model: TicketAnalysis, lazy: bool = False) -> TicketAnalysisEntity:
        return TicketAnalysisEntity(
            ticket_id=model.ticket_id,
            request_type=model.request_type,
            sentiment=model.sentiment,
            urgency_score=model.urgency_score,
            language=model.language,
            summary=model.summary,
            image_enriched=model.image_enriched,
            latitude=model.latitude,
            longitude=model.longitude,
            formatted_address=model.formatted_address,
        )

    @classmethod
    def to_model(cls, entity: TicketAnalysisEntity, lazy: bool = False) -> TicketAnalysis:
        return TicketAnalysis(
            ticket_id=entity.ticket_id,
            request_type=entity.request_type,
            sentiment=entity.sentiment,
            urgency_score=entity.urgency_score,
            language=entity.language,
            summary=entity.summary,
            image_enriched=entity.image_enriched,
            latitude=entity.latitude,
            longitude=entity.longitude,
            formatted_address=entity.formatted_address,
        )


class TicketAttachmentMapper(BaseMapper[TickerAttachments, TicketAttachmentEntity]):
    model = TickerAttachments
    entity = TicketAttachmentEntity

    @classmethod
    def to_entity(cls, model: TickerAttachments, lazy: bool = False) -> TicketAttachmentEntity:
        return TicketAttachmentEntity(
            ticket_id=model.ticket_id,
            attachment_id=model.attachment_id,
        )

    @classmethod
    def to_model(cls, entity: TicketAttachmentEntity, lazy: bool = False) -> TickerAttachments:
        return TickerAttachments(
            ticket_id=entity.ticket_id,
            attachment_id=entity.attachment_id,
        )


class TicketAssignmentMapper(BaseMapper[TicketAssignment, TicketAssignmentEntity]):
    model = TicketAssignment
    entity = TicketAssignmentEntity

    @classmethod
    def to_entity(cls, model: TicketAssignment, lazy: bool = False) -> TicketAssignmentEntity:
        return TicketAssignmentEntity(
            ticket_id=model.ticket_id,
            manager_id=model.manager_id,
        )

    @classmethod
    def to_model(cls, entity: TicketAssignmentEntity, lazy: bool = False) -> TicketAssignment:
        return TicketAssignment(
            ticket_id=entity.ticket_id,
            manager_id=entity.manager_id,
        )
