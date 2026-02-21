from sqlalchemy import Column, Integer, String, ForeignKey

from backend.infrastructure.db.base import Base


class ManagerPosition(Base):
    __tablename__ = "manager_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    hierarchy_level = Column(Integer, nullable=False, index=True, default=0)


class Manager(Base):
    __tablename__ = "managers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("manager_positions.id"))
    city_id = Column(Integer, ForeignKey("cities.id"))
    in_progress_requests = Column(Integer, nullable=False, index=True, default=0)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)


class ManagerSkills(Base):
    __tablename__ = "manager_skills"

    manager_id = Column(Integer, ForeignKey("managers.id"), primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), primary_key=True)
