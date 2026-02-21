from abc import ABCMeta, abstractmethod
from typing import Dict, Generic, Type, TypeVar

from backend.core.base.entity import BaseEntity

ModelT = TypeVar("ModelT")
EntityT = TypeVar("EntityT", bound=BaseEntity)


class BaseMapper(Generic[ModelT, EntityT], metaclass=ABCMeta):
    model: Type[ModelT] = ModelT
    entity: Type[EntityT] = EntityT

    relationships: Dict[str, Type["BaseMapper"]] = {}

    @classmethod
    @abstractmethod
    def to_entity(cls, model: ModelT, lazy: bool = False) -> EntityT:
        data = {column.name: getattr(model, column.name) for column in cls.model.__table__.columns}

        if not lazy:
            for rel_name, rel_mapper in cls.relationships.items():
                related_data = getattr(model, rel_name)
                if related_data is not None:
                    if isinstance(related_data, list):
                        data[rel_name] = [rel_mapper.to_entity(rel) for rel in related_data]
                    else:
                        data[rel_name] = rel_mapper.to_entity(related_data)

        return cls.entity(**data)

    @classmethod
    @abstractmethod
    def to_model(cls, entity: EntityT, lazy: bool = False) -> ModelT:
        data = entity.__dict__.copy()

        if not lazy:
            for rel_name, rel_mapper in cls.relationships.items():
                related_entities = getattr(entity, rel_name, None)
                if related_entities:
                    if isinstance(related_entities, list):
                        data[rel_name] = [rel_mapper.to_model(rel) for rel in related_entities]
                    else:
                        data[rel_name] = rel_mapper.to_model(related_entities)

        return cls.model(**data)
