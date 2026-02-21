from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Union, Any, Dict


@dataclass
class BaseEntity(ABC):
    def to_dict(self) -> dict:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: dict) -> 'BaseEntity':
        return cls(**data)

    @property
    def primary_key(self) -> Union[Any, Dict[str, Any]]:
        return getattr(self, "id_")
