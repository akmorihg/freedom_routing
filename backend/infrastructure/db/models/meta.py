from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, UUID

from backend.infrastructure.db.base import Base


class TaskLatencies(Base):
    __tablename__ = "task_latencies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_type = Column(Float, nullable=False, default=0.0)
    sentiment = Column(Float, nullable=False, default=0.0)
    urgency_score = Column(Float, nullable=False, default=0.0)
    language = Column(Float, nullable=False, default=0.0)
    summary = Column(Float, nullable=False, default=0.0)
    geo = Column(Float, nullable=False, default=0.0)
    image_describe = Column(Float, nullable=False, default=0.0)


class RetriesUsed(Base):
    __tablename__ = "retries_used"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_type = Column(Integer, nullable=False, default=0)
    sentiment = Column(Integer, nullable=False, default=0)
    urgency_score = Column(Integer, nullable=False, default=0)
    language = Column(Integer, nullable=False, default=0)
    summary = Column(Integer, nullable=False, default=0)
    geo = Column(Integer, nullable=False, default=0)
    image_describe = Column(Integer, nullable=False, default=0)


class AnalysisMeta(Base):
    __tablename__ = "analysis_meta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False, unique=True)
    model = Column(String, nullable=False)
    task_latencies_id = Column(Integer, ForeignKey("task_latencies.id"), nullable=False)
    retries_used_id = Column(Integer, ForeignKey("retries_used.id"), nullable=False)
    fallbacks_used = Column(JSON, nullable=False, default=list)
    total_processing_ms = Column(Float, nullable=False, default=0.0)
