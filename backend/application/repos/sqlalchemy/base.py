import logging
from typing import TypeVar, Type, Any, List, Tuple, Optional, Dict, Union

from sqlalchemy import select, func, delete, and_, or_, asc, desc
from sqlalchemy.engine import Result
from sqlalchemy.sql import Executable, Select
from sqlalchemy.inspection import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql

from backend.core.enums import OrderModes
from backend.core.abstract.repository import IDBRepository
from backend.core.base.entity import BaseEntity
from backend.core.base.mapper import BaseMapper
from backend.core.caching.enums import CacheDomains, DBOperations
from backend.core.caching.manager import CacheManager
from backend.infrastructure.db.base import Base

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=Base)
EntityT = TypeVar("EntityT", bound=BaseEntity)
MapperT = TypeVar("MapperT", bound=BaseMapper)


class BaseSQLAlchemyRepo(IDBRepository[ModelT, EntityT, MapperT]):
    model: Type[ModelT] = Base
    entity: Type[EntityT] = BaseEntity
    mapper: Type[MapperT] = MapperT

    def __init__(
        self,
        session: AsyncSession,
        is_transactional: bool,
        use_cache: bool = False,
        cache_manager: Optional[CacheManager] = None,
    ) -> None:
        self._session = session
        self._is_transactional = is_transactional

        self._use_cache = use_cache
        self._cache_manager = cache_manager

        self._dialect = postgresql.dialect()

        primary_key_names = [key.name for key in inspect(self.model).primary_key]
        self.primary_keys: Dict[str, Any] = {
            primary_key_name: getattr(self.model, primary_key_name)
            for primary_key_name in primary_key_names
        }

    def _primary_key_to_prefix(self, pk: Union[Any, Dict[str, Any]]) -> str:
        if isinstance(pk, dict) and pk:
            key_names: List[str] = sorted(pk.keys())
            result: str = f"{pk[key_names[0]]}"
            for key_name in key_names[1:]:
                result += f",{pk[key_name]}"

        return str(pk)

    def _get_cache_key(
        self,
        str_statement: Optional[str] = None,
        db_operation: Optional[DBOperations] = None,
        prefix: Optional[str] = None,
        to_invalidate: bool = False,
    ) -> str:
        if to_invalidate:
            return f"{self.model.__name__}:{db_operation.value if db_operation else '*'}:{prefix or '*'}:{str_statement or '*'}"

        return f"{self.model.__name__}:{db_operation.value if db_operation else None}:{prefix}:{str_statement}"

    def _stmt_to_str(self, stmt: Select) -> Optional[str]:
        str_statement: Optional[str] = None
        try:
            str_statement = str(
                stmt.compile(
                    dialect=self._dialect,
                    compile_kwargs={"literal_binds": True}
                )
            )
        except Exception as e:
            logger.warning(f"Error during statement compiling: {e}")

        return str_statement

    async def _get_from_cache(
        self,
        stmt: Optional[Select] = None,
        db_operation: Optional[DBOperations] = None,
        prefix: Optional[str] = None,
    ) -> Optional[Any]:
        if not self._use_cache or self._cache_manager is None:
            return None

        if stmt is None and db_operation is None and prefix is None:
            return None

        str_statement: Optional[str] = None
        if stmt is not None:
            str_statement = self._stmt_to_str(stmt)

        cached_value: Optional[Any] = None
        try:
            cached_value = await self._cache_manager.get(
                domain=CacheDomains.REPOSITORY,
                key=self._get_cache_key(
                    str_statement=str_statement,
                    db_operation=db_operation,
                    prefix=prefix,
                ),
            )
        except Exception as e:
            logger.warning(f"Error to get from cache: {e}")

        return cached_value

    async def _get_from_prefixes(self, cached_prefixes: List[str]) -> Optional[List[Any]]:
        result: List[Any] = []
        for cached_prefix in cached_prefixes:
            cached_keys: List[str] = await self._cache_manager.get_keys_by_pattern(
                domain=CacheDomains.REPOSITORY,
                pattern=self._get_cache_key(
                    prefix=cached_prefix,
                    to_invalidate=True
                )
            )
            if len(cached_keys) == 0:
                return None

            cached_value: Any = await self._cache_manager.get(
                domain=CacheDomains.REPOSITORY,
                key=cached_keys[0]
            )

            result.append(cached_value)

        return result

    async def _set_to_cache(
        self,
        stmt: Select,
        value: Any,
        db_operation: Optional[DBOperations] = None,
        prefix: Optional[str] = None,
    ) -> None:
        if not self._use_cache or self._cache_manager is None:
            return

        str_statement: Optional[str] = self._stmt_to_str(stmt)
        if str_statement is None:
            return

        try:
            await self._cache_manager.set(
                domain=CacheDomains.REPOSITORY,
                key=self._get_cache_key(
                    str_statement=str_statement,
                    db_operation=db_operation,
                    prefix=prefix
                ),
                value=value
            )
        except Exception as e:
            logger.warning(f"Error to set to cache: {e}")

    async def _invalidate_cache(
        self,
        db_operation: Optional[DBOperations] = None,
        prefix: Optional[str] = None,
    ) -> List[str]:
        if not self._use_cache or self._cache_manager is None:
            return []

        try:
            return await self._cache_manager.invalidate_by_pattern(
                domain=CacheDomains.REPOSITORY,
                pattern=self._get_cache_key(
                    db_operation=db_operation,
                    prefix=prefix,
                    to_invalidate=True
                ),
            )
        except Exception as e:
            logger.warning(f"Error to invalidate cache: {e}")
            return []

    async def _commit(self) -> None:
        if self._is_transactional:
            await self._session.flush()
        else:
            await self._session.commit()

    def _one_or_none(self, entities: List[EntityT]) -> Optional[EntityT]:
        if len(entities) == 0:
            return None

        return entities[0]

    def _get_pk_filter(self, pk: Union[Any, Dict[str, Any]]) -> Any:
        filters: List = []
        if len(self.primary_keys) == 1:
            return list(self.primary_keys.values())[0] == pk
        else:
            for key_name, key_attr in self.primary_keys.items():
                filters.append(
                    key_attr == pk.get(key_name)
                )

        return and_(*filters)

    def _get_pks_filter(self, pks: List[Union[Any, Dict[str, Any]]]) -> Any:
        filters: List = []
        for pk in pks:
            filters.append(
                self._get_pk_filter(pk)
            )

        return or_(*filters)

    def _apply_order_by(
        self,
        stmt: Select,
        order_by: Union[Any, List[Any]],
        order_mode: Union[OrderModes, List[OrderModes]]
    ) -> Select:
        clauses: List = []

        column_counter: int = 0
        if not isinstance(order_by, list):
            order_columns = [order_by]
        else:
            order_columns = order_by

        mode_counter: int = 0
        if not isinstance(order_mode, list):
            order_modes = [order_mode]
        else:
            order_modes = order_mode

        for _ in range(len(order_columns)):
            clauses.append(
                asc(order_columns[column_counter]) if order_modes[mode_counter] == OrderModes.ASC else desc(order_columns[column_counter])
            )

            if column_counter < len(order_columns):
                column_counter += 1

            if mode_counter < len(order_modes):
                mode_counter += 1

        stmt = (
            stmt
            .order_by(*clauses)
        )

        return stmt

    async def get(self, pk: Union[Any, Dict[str, Any]]) -> Optional[EntityT]:
        stmt: Select = (
            select(self.model)
            .where(
                self._get_pk_filter(pk)
            )
        )

        cached_value: Optional[Any] = await self._get_from_cache(
            stmt=stmt,
            db_operation=DBOperations.GET,
            prefix=self._primary_key_to_prefix(pk)
        )
        if cached_value is not None:
            return cached_value

        result: Result = await self._session.execute(stmt)
        instance: Optional[ModelT] = result.scalar_one_or_none()
        if not instance:
            return None

        entity: EntityT = self.mapper.to_entity(instance)
        await self._set_to_cache(
            stmt=stmt,
            value=entity,
            db_operation=DBOperations.GET,
            prefix=self._primary_key_to_prefix(pk)
        )

        return entity

    async def get_all(
        self,
        pks: Optional[List[Union[Any, Dict[str, Any]]]] = None,
        order_by: Optional[Union[Any, List[Any]]] = None,
        order_mode: Union[OrderModes, List[OrderModes]] = OrderModes.ASC,
    ) -> List[EntityT]:
        stmt: Select = select(self.model)

        if pks is not None:
            stmt: Select = (
                stmt
                .where(
                    self._get_pks_filter(pks)
                )
            )

        if order_by is not None:
            stmt = self._apply_order_by(stmt, order_by, order_mode)

        cached_prefixes: Optional[List[str]] = await self._get_from_cache(
            stmt=stmt,
            db_operation=DBOperations.GET,
        )
        if cached_prefixes is not None:
            cached_entities: Optional[List[EntityT]] = await self._get_from_prefixes(
                cached_prefixes=cached_prefixes,
            )
            if cached_entities is not None:
                return cached_entities

        result: Result = await self._session.execute(stmt)
        instances: List[ModelT] = list(result.scalars().all())
        entities: List[EntityT] = []
        prefixes: List[str] = []
        for instance in instances:
            entity: EntityT = self.mapper.to_entity(instance)
            entity_prefix: str = self._primary_key_to_prefix(entity.primary_key)
            await self._set_to_cache(
                stmt=stmt,
                value=entity,
                db_operation=DBOperations.GET,
                prefix=entity_prefix
            )

            entities.append(entity)
            prefixes.append(entity_prefix)

        await self._set_to_cache(
            stmt=stmt,
            value=prefixes,
            db_operation=DBOperations.GET_MANY,
        )

        return entities

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        filters: Optional[List] = None,
        order_by: Optional[Union[Any, List[Any]]] = None,
        order_mode: Union[OrderModes, List[OrderModes]] = OrderModes.ASC,
    ) -> Tuple[int, List[EntityT]]:
        offset: int = (page - 1) * page_size
        stmt: Select = (
            select(self.model)
            .limit(page_size)
            .offset(offset)
        )

        if filters:
            stmt = stmt.where(*filters)  # type: ignore

        if order_by is not None:
            stmt = self._apply_order_by(stmt, order_by, order_mode)

        cached_prefixes: Optional[Any] = await self._get_from_cache(
            stmt=stmt,
            db_operation=DBOperations.GET_MANY,
        )

        entities: List[EntityT] = []
        found_cached_entities: bool = False
        if cached_prefixes is not None:
            cached_entities: Optional[List[EntityT]] = await self._get_from_prefixes(
                cached_prefixes=cached_prefixes,
            )
            if cached_entities is not None:
                found_cached_entities = True
                entities = cached_entities

        if not found_cached_entities:
            result: Result = await self._session.execute(stmt)
            instances: List[ModelT] = list(result.scalars().all())
            entities = []
            prefixes: List[str] = []
            for instance in instances:
                entity: EntityT = self.mapper.to_entity(instance)
                entity_prefix: str = self._primary_key_to_prefix(entity.primary_key)
                await self._set_to_cache(
                    stmt=stmt,
                    value=entity,
                    db_operation=DBOperations.GET,
                    prefix=entity_prefix
                )
                prefixes.append(entity_prefix)
                entities.append(entity)

            await self._set_to_cache(
                stmt=stmt,
                value=prefixes,
                db_operation=DBOperations.GET_MANY,
            )

        total_count: int = await self.count(filters)

        return total_count, entities

    async def search(
        self,
        filters: List,
        order_by: Optional[Union[Any, List[Any]]] = None,
        order_mode: Union[OrderModes, List[OrderModes]] = OrderModes.ASC,
    ) -> List[EntityT]:
        stmt: Select = (
            select(self.model)
            .where(*filters)
        )

        if order_by is not None:
            stmt = self._apply_order_by(stmt, order_by, order_mode)

        cached_prefixes: Optional[Any] = await self._get_from_cache(
            stmt=stmt,
            db_operation=DBOperations.GET_MANY,
        )
        if cached_prefixes is not None:
            cached_entities: Optional[List[EntityT]] = await self._get_from_prefixes(
                cached_prefixes=cached_prefixes,
            )
            if cached_entities is not None:
                return cached_entities

        result: Result = await self._session.execute(stmt)
        instances: List[ModelT] = list(result.scalars().all())
        entities: List[EntityT] = []
        prefixes: List[str] = []
        for instance in instances:
            entity: EntityT = self.mapper.to_entity(instance)
            entity_prefix: str = self._primary_key_to_prefix(entity.primary_key)
            await self._set_to_cache(
                stmt=stmt,
                value=entity,
                db_operation=DBOperations.GET,
                prefix=entity_prefix
            )
            prefixes.append(entity_prefix)
            entities.append(entity)

        await self._set_to_cache(
            stmt=stmt,
            value=prefixes,
            db_operation=DBOperations.GET_MANY,
        )

        return entities

    async def search_one_or_none(self, filters: List) -> Optional[EntityT]:
        entities: List[EntityT] = await self.search(filters)
        return self._one_or_none(entities)

    async def count(self, filters: Optional[List] = None) -> int:
        stmt: Select = (
            select(func.count())
            .select_from(self.model)
        )
        if filters is not None:
            stmt = stmt.where(*filters)  # type: ignore

        cached_value: Optional[Any] = await self._get_from_cache(
            stmt=stmt,
            db_operation=DBOperations.GET_MANY,
        )
        if cached_value is not None:
            return cached_value

        result: Result = await self._session.execute(stmt)
        count: int = result.scalar()

        await self._set_to_cache(
            stmt=stmt,
            value=count,
            db_operation=DBOperations.GET_MANY,
        )

        return count

    async def create(self, entity: EntityT) -> EntityT:
        instance: ModelT = self.mapper.to_model(entity)

        self._session.add(instance)

        try:
            await self._commit()
        except Exception as e:
            logger.error(f"Failed 'create' in BaseSQLAlchemyRepo: {e}")

        await self._session.refresh(instance)
        entity: EntityT = self.mapper.to_entity(instance)

        await self._invalidate_cache(
            db_operation=DBOperations.GET_MANY,
        )

        return entity

    async def batch_create(self, entities: List[EntityT]) -> List[EntityT]:
        instances: List[ModelT] = []
        for entity in entities:
            instance: ModelT = self.mapper.to_model(entity)
            instances.append(instance)

        self._session.add_all(instances)

        try:
            await self._commit()
        except Exception as e:
            logger.error(f"Failed 'batch_create' in BaseSQLAlchemyRepo: {e}")

        result: List[EntityT] = []
        for instance in instances:
            await self._session.refresh(instance)
            entity: EntityT = self.mapper.to_entity(instance)
            result.append(entity)

        await self._invalidate_cache(
            db_operation=DBOperations.GET_MANY,
        )

        return result

    async def update(self, entity: EntityT) -> Optional[EntityT]:
        instance: ModelT = self.mapper.to_model(entity)
        merged_instance: ModelT = await self._session.merge(instance)

        try:
            await self._commit()
        except Exception as e:
            logger.error(f"Failed 'update' in BaseSQLAlchemyRepo: {e}")

        await self._session.refresh(merged_instance)
        entity: EntityT = self.mapper.to_entity(merged_instance)

        await self._invalidate_cache(
            db_operation=DBOperations.GET_MANY,
        )

        pattern: str = self._get_cache_key(
            db_operation=DBOperations.GET,
            prefix=self._primary_key_to_prefix(entity.primary_key),
            to_invalidate=True
        )
        if self._use_cache and self._cache_manager:
            keys: List[str] = await self._cache_manager.get_keys_by_pattern(
                domain=CacheDomains.REPOSITORY,
                pattern=pattern,
            )
            for key in keys:
                await self._cache_manager.set(
                    domain=CacheDomains.REPOSITORY,
                    key=key,
                    value=entity,
                )

        return entity

    async def batch_update(self, entities: List[EntityT]) -> List[EntityT]:
        instances: List[ModelT] = []
        for entity in entities:
            instance: ModelT = self.mapper.to_model(entity)
            merged_instance: ModelT = await self._session.merge(instance)
            instances.append(merged_instance)

        try:
            await self._commit()
        except Exception as e:
            logger.error(f"Failed 'batch_update' in BaseSQLAlchemyRepo: {e}")

        result: List[EntityT] = []
        for instance in instances:
            await self._session.refresh(instance)
            entity: EntityT = self.mapper.to_entity(instance)
            result.append(entity)

        await self._invalidate_cache(
            db_operation=DBOperations.GET_MANY,
        )
        if self._use_cache and self._cache_manager:
            for entity in entities:
                pattern: str = self._get_cache_key(
                    db_operation=DBOperations.GET,
                    prefix=self._primary_key_to_prefix(entity.primary_key),
                    to_invalidate=True
                )
                keys: List[str] = await self._cache_manager.get_keys_by_pattern(
                    domain=CacheDomains.REPOSITORY,
                    pattern=pattern,
                )
                for key in keys:
                    await self._cache_manager.set(
                        domain=CacheDomains.REPOSITORY,
                        key=key,
                        value=entity,
                    )

        return result

    async def delete(self, pk: Union[Any, Dict[str, Any]]) -> bool:
        stmt: Executable = (
            delete(self.model)
            .where(
                self._get_pk_filter(pk)
            )
        )

        try:
            await self._session.execute(stmt)
            await self._commit()
            await self._invalidate_cache(
                db_operation=DBOperations.GET_MANY,
            )
            await self._invalidate_cache(
                db_operation=DBOperations.GET,
                prefix=self._primary_key_to_prefix(pk),
            )

            return True
        except Exception as e:
            logger.error(f"Failed 'delete' in BaseSQLAlchemyRepo: {e}")
            return False

    async def batch_delete(self, pks: List[Union[Any, Dict[str, Any]]]) -> bool:
        stmt: Executable = (
            delete(self.model)
            .where(
                self._get_pks_filter(pks)
            )
        )

        try:
            await self._session.execute(stmt)
            await self._commit()
            await self._invalidate_cache(
                db_operation=DBOperations.GET_MANY,
            )
            for pk in pks:
                await self._invalidate_cache(
                    db_operation=DBOperations.GET,
                    prefix=self._primary_key_to_prefix(pk),
                )

            return True
        except Exception as e:
            logger.error(f"Failed 'batch_delete' in BaseSQLAlchemyRepo: {e}")
            return False

    async def exists(self, filters: List) -> bool:
        return await self.count(filters) > 0

    async def get_db_name(self) -> str:
        return self._session.bind.url.database
