from datetime import date
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from backend.application.dtos.location import AddressDTO


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

    # relations (optional)
    type: Optional[AttachmentTypeDTO] = None

    # optional: if you already have S3/MinIO presigned URL generation
    url: Optional[str] = None


class TicketDTO(BaseModel):
    id_: UUID
    gender_id: int
    date_of_birth: date
    description: str = ""
    segment_id: int = 0
    address_id: int = 0

    # relations (optional)
    gender: Optional[GenderDTO] = None
    segment: Optional[ClientSegmentDTO] = None
    # reuse your AddressDTO from previous answer
    address: Optional[AddressDTO] = None

    # attachments (like MessageDTO.media)
    attachments: List[AttachmentDTO] = Field(default_factory=list)
