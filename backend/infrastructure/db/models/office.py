from sqlalchemy import Column, Integer, ForeignKey, String

from backend.infrastructure.db.base import Base


class Office(Base):
    __tablename__ = "offices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city_id = Column(Integer, ForeignKey("cities.id"))
    address = Column(String, nullable=False)
