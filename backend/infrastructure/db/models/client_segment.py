from sqlalchemy import Column, Integer, String

from backend.infrastructure.db.base import Base


class ClientSegment(Base):
    __tablename__ = "client_segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    priority = Column(Integer, nullable=False, default=0)
