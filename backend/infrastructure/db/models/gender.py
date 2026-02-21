from sqlalchemy import Column, Integer, String

from backend.infrastructure.db.base import Base


class Gender(Base):
    __tablename__ = "genders"

    id = Column(Integer, primary_key=True)
    name = Column(String)
