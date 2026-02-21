from sqlalchemy import Column, UUID, Integer, ForeignKey, Date, String

from backend.infrastructure.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True)
    gender_id = Column(Integer, ForeignKey("genders.id"), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    description = Column(String, nullable=False, default="")
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=False)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=False)


class TickerAttachments(Base):
    __tablename__ = "ticket_attachments"

    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), primary_key=True)
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachments.id"), primary_key=True)
