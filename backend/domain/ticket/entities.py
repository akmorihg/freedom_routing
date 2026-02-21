from dataclasses import dataclass
from datetime import date
from typing import Optional, Union, Any, Dict
from uuid import UUID

from backend.core.base.entity import BaseEntity


@dataclass
class ClientSegmentEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""
    priority: int = 0


@dataclass
class GenderEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""


@dataclass
class AttachmentTypeEntity(BaseEntity):
    id_: Optional[int] = None
    name: str = ""


@dataclass
class AttachmentEntity(BaseEntity):
    id_: Optional[int] = None
    type_id: int = 0
    key: str = ""


@dataclass
class TicketEntity(BaseEntity):
    id_: UUID
    gender_id: int
    date_of_birth: date
    description: str = ""
    segment_id: int = 0
    address_id: int = 0


@dataclass
class TicketAnalysisEntity(BaseEntity):
    ticket_id: UUID

    request_type: str = ""
    sentiment: str = ""
    urgency_score: int = 1
    language: str = ""
    summary: str = ""
    image_enriched: bool = False

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: str = ""

    @property
    def primary_key(self) -> Union[Any, Dict[str, Any]]:
        return self.ticket_id


@dataclass
class TicketAttachmentEntity(BaseEntity):
    ticket_id: UUID
    attachment_id: int

    @property
    def primary_key(self) -> Union[Any, Dict[str, Any]]:
        return {
            "ticket_id": self.ticket_id,
            "attachment_id": self.attachment_id,
        }


@dataclass
class TicketAssignmentEntity(BaseEntity):
    ticket_id: UUID
    manager_id: int

    @property
    def primary_key(self) -> Union[Any, Dict[str, Any]]:
        return {
            "ticket_id": self.ticket_id,
            "manager_id": self.manager_id,
        }
