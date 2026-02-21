from abc import ABC, abstractmethod
from typing import Any, TypeVar, Generic, Optional, List, Tuple, Union, Dict

from backend.core.enums import OrderModes
from backend.core.base.entity import BaseEntity
from backend.core.base.mapper import BaseMapper


class IRepository(ABC):
    @abstractmethod
    async def get(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Implement 'get' method")

    @abstractmethod
    async def create(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Implement 'create' method")

    @abstractmethod
    async def update(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Implement 'update' method")

    @abstractmethod
    async def delete(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Implement 'delete' method")


ModelT = TypeVar("ModelT")
EntityT = TypeVar("EntityT", bound=BaseEntity)
MapperT = TypeVar("MapperT", bound=BaseMapper)


class IDBRepository(
    IRepository,
    ABC,
    Generic[ModelT, EntityT, MapperT],
):
    @abstractmethod
    async def get(self, pk: Union[Any, Dict[str, Any]]) -> Optional[EntityT]:
        raise NotImplementedError("Implement 'get' method")

    @abstractmethod
    async def get_all(
        self,
        pks: Optional[Union[Any, Dict[str, Any]]] = None,
        order_by: Optional[Union[Any, List[Any]]] = None,
        order_mode: Union[OrderModes, List[OrderModes]] = OrderModes.ASC,
    ) -> List[EntityT]:
        raise NotImplementedError("Implement 'get_all' method")

    @abstractmethod
    async def get_paginated(
        self,
        page: int,
        page_size: int,
        filters: Optional[List] = None,
        order_by: Optional[Union[Any, List[Any]]] = None,
        order_mode: Union[OrderModes, List[OrderModes]] = OrderModes.ASC,
    ) -> Tuple[int, List[EntityT]]:
        raise NotImplementedError("Implement 'get_paginated' method")

    @abstractmethod
    async def search(
        self,
        filters: List,
        order_by: Optional[Union[Any, List[Any]]] = None,
        order_mode: Union[OrderModes, List[OrderModes]] = OrderModes.ASC,
    ) -> List[EntityT]:
        raise NotImplementedError("Implement 'search' method")

    @abstractmethod
    async def search_one_or_none(self, filters: List) -> Optional[EntityT]:
        raise NotImplementedError("Implement 'search_one_or_none' method")

    @abstractmethod
    async def count(self, filters: Optional[List] = None) -> int:
        raise NotImplementedError("Implement 'count' method")

    @abstractmethod
    async def create(self, entity: EntityT) -> EntityT:
        raise NotImplementedError("Implement 'create' method")

    @abstractmethod
    async def batch_create(self, entities: List[EntityT]) -> List[EntityT]:
        raise NotImplementedError("Implement 'batch_create' method")

    @abstractmethod
    async def update(self, entity: EntityT) -> Optional[EntityT]:
        raise NotImplementedError("Implement 'update' method")

    @abstractmethod
    async def batch_update(self, entities: List[EntityT]) -> List[EntityT]:
        raise NotImplementedError("Implement 'batch_update' method")

    @abstractmethod
    async def delete(self, pk: Union[Any, Dict[str, Any]]) -> bool:
        raise NotImplementedError("Implement 'delete' method")

    @abstractmethod
    async def batch_delete(self, pks: List[Union[Any, Dict[str, Any]]]) -> bool:
        raise NotImplementedError("Implement 'batch_delete' method")

    @abstractmethod
    async def exists(self, filters: List) -> bool:
        raise NotImplementedError("Implement 'exists' method")

    @abstractmethod
    async def get_db_name(self) -> str:
        raise NotImplementedError("Implement 'get_db_name' method")

