from backend.core.base.mapper import BaseMapper
from backend.domain.manager.entities import ManagerPositionEntity, ManagerEntity, SkillEntity, ManagerSkillEntity

from backend.infrastructure.db.models.manager import (
    ManagerPosition,
    Manager,
    Skill,
    ManagerSkills,
)


class ManagerPositionMapper(BaseMapper[ManagerPosition, ManagerPositionEntity]):
    model = ManagerPosition
    entity = ManagerPositionEntity

    @classmethod
    def to_entity(cls, model: ManagerPosition, lazy: bool = False) -> ManagerPositionEntity:
        return ManagerPositionEntity(
            id_=model.id,
            name=model.name,
            hierarchy_level=model.hierarchy_level,
        )

    @classmethod
    def to_model(cls, entity: ManagerPositionEntity, lazy: bool = False) -> ManagerPosition:
        return ManagerPosition(
            id=entity.id_,
            name=entity.name,
            hierarchy_level=entity.hierarchy_level,
        )


class ManagerMapper(BaseMapper[Manager, ManagerEntity]):
    model = Manager
    entity = ManagerEntity

    @classmethod
    def to_entity(cls, model: Manager, lazy: bool = False) -> ManagerEntity:
        return ManagerEntity(
            id_=model.id,
            position_id=model.position_id,
            city_id=model.city_id,
            in_progress_requests=model.in_progress_requests,
        )

    @classmethod
    def to_model(cls, entity: ManagerEntity, lazy: bool = False) -> Manager:
        return Manager(
            id=entity.id_,
            position_id=entity.position_id,
            city_id=entity.city_id,
            in_progress_requests=entity.in_progress_requests,
        )


class SkillMapper(BaseMapper[Skill, SkillEntity]):
    model = Skill
    entity = SkillEntity

    @classmethod
    def to_entity(cls, model: Skill, lazy: bool = False) -> SkillEntity:
        return SkillEntity(
            id_=model.id,
            name=model.name,
        )

    @classmethod
    def to_model(cls, entity: SkillEntity, lazy: bool = False) -> Skill:
        return Skill(
            id=entity.id_,
            name=entity.name,
        )


class ManagerSkillMapper(BaseMapper[ManagerSkills, ManagerSkillEntity]):
    model = ManagerSkills
    entity = ManagerSkillEntity

    @classmethod
    def to_entity(cls, model: ManagerSkills, lazy: bool = False) -> ManagerSkillEntity:
        return ManagerSkillEntity(
            manager_id=model.manager_id,
            skill_id=model.skill_id,
        )

    @classmethod
    def to_model(cls, entity: ManagerSkillEntity, lazy: bool = False) -> ManagerSkills:
        return ManagerSkills(
            manager_id=entity.manager_id,
            skill_id=entity.skill_id,
        )
