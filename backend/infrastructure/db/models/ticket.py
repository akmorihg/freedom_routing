from sqlalchemy import Column, UUID, Integer, ForeignKey, Date, String, Text, Boolean, Float

from backend.infrastructure.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True)
    gender_id = Column(Integer, ForeignKey("genders.id"), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    description = Column(String, nullable=False, default="")
    segment_id = Column(Integer, ForeignKey("client_segments.id"), nullable=False)
    address_id = Column(Integer, ForeignKey("addresses.id"), nullable=False)


class TickerAttachments(Base):
    __tablename__ = "ticket_attachments"

    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), primary_key=True)
    attachment_id = Column(Integer, ForeignKey("attachments.id"), primary_key=True)


class TicketAnalysis(Base):
    __tablename__ = "ticket_analysis"

    # Ticket identity
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), primary_key=True)

    # AI analysis output
    request_type = Column(String, nullable=False)
    sentiment = Column(String, nullable=False)
    urgency_score = Column(Integer, nullable=False)
    language = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    image_enriched = Column(Boolean, nullable=False, default=False)

    # Geo data
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    formatted_address = Column(String, nullable=False, default="")


class TicketAssignment(Base):
    __tablename__ = "ticket_assignments"

    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), primary_key=True)
    manager_id = Column(Integer, ForeignKey("managers.id"), primary_key=True)
