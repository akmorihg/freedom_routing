from dataclasses import dataclass, field
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


@dataclass
class TaskLatenciesEntity(BaseEntity):
    id_: Optional[int] = None
    request_type: float = 0.0
    sentiment: float = 0.0
    urgency_score: float = 0.0
    language: float = 0.0
    summary: float = 0.0
    geo: float = 0.0
    image_describe: float = 0.0


@dataclass
class RetriesUsedEntity(BaseEntity):
    id_: Optional[int] = None
    request_type: int = 0
    sentiment: int = 0
    urgency_score: int = 0
    language: int = 0
    summary: int = 0
    geo: int = 0
    image_describe: int = 0


@dataclass
class AnalysisMetaEntity(BaseEntity):
    id_: Optional[int] = None
    ticket_id: Optional[UUID] = None
    model: str = ""
    task_latencies_id: int = 0
    retries_used_id: int = 0
    fallbacks_used: list[str] = field(default_factory=list)
    total_processing_ms: float = 0.0
