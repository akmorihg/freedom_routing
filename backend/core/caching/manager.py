import logging
import inspect
import pickle
from typing import Any, Optional, List, Dict
from functools import wraps

from redis.asyncio import Redis

from backend.settings import settings
from backend.core.caching.enums import CacheDomains

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _form_cache_key(
            self,
            domain: CacheDomains,
            key: str
    ) -> str:
        return f"{domain.value}:{key}"

    def _remove_domain_from_key(self, key: str) -> str:
        return ":".join(key.split(":")[1:])

    async def set(
            self,
            domain: CacheDomains,
            key: str,
            value: Any,
            ttl: int = 3600
    ) -> str:
        cache_key: str = self._form_cache_key(domain, key)
        encoded_value: bytes = pickle.dumps(value)
        await self.redis.set(
            name=cache_key,
            value=encoded_value,
            ex=ttl,
        )

        return key

    async def get(
            self,
            domain: CacheDomains,
            key: str
    ) -> Optional[Any]:
        cache_key: str = self._form_cache_key(domain, key)
        encoded_value: Optional[bytes] = await self.redis.get(name=cache_key)
        if encoded_value is None:
            return None

        try:
            decoded: Any = pickle.loads(encoded_value)
        except:
            await self.invalidate(
                domain=domain,
                key=key
            )
            return None

        return decoded

    async def get_keys_by_pattern(
            self,
            domain: CacheDomains,
            pattern: str
    ) -> List[str]:
        cache_pattern: str = self._form_cache_key(domain, pattern)
        keys: List[str] = await self.redis.keys(cache_pattern)
        keys = [
            key.decode("utf-8")
            for key in keys
        ]

        return [
            self._remove_domain_from_key(key)
            for key in keys
        ]

    async def invalidate(
            self,
            domain: CacheDomains,
            key: str
    ) -> str:
        cache_key: str = self._form_cache_key(domain, key)
        await self.redis.delete(cache_key)

        return key

    async def invalidate_by_pattern(
            self,
            domain: CacheDomains,
            pattern: str,
    ) -> List[str]:
        keys: List[str] = await self.get_keys_by_pattern(
            domain=domain,
            pattern=pattern
        )
        keys = [
            self._form_cache_key(domain, key)
            for key in keys
        ]
        if len(keys) > 0:
            await self.redis.delete(*keys)

        return [
            self._remove_domain_from_key(key)
            for key in keys
        ]


cache_manager = CacheManager(
    redis=Redis.from_url(settings.REDIS_URL)
)


def cache(
        domain: CacheDomains,
        key: Optional[str] = None,
        ttl: int = 3600,
):
    def decorator(func):

        def map_args_kwargs_to_dict(*args, **kwargs) -> Dict[str, Any]:
            signature = inspect.signature(func)
            param_names: List[str] = list(signature.parameters.keys())

            result: Dict[str, Any] = {}
            for i, arg in enumerate(args):
                param_name: str = param_names[i]
                result[param_name] = arg

            for name, value in kwargs.items():
                result[name] = value

            return result

        @wraps(func)
        async def wrapper(*args, **kwargs):
            _key: str = func.__name__ or key
            args_mapping: Dict[str, Any] = map_args_kwargs_to_dict(*args, **kwargs)

            for arg_name in sorted(args_mapping.keys()):
                arg_value: Any = args_mapping[arg_name]

                value_address: str = hex(id(arg_value))
                value_str: str = str(arg_value)
                if value_address not in value_str:
                    _key += f":{arg_name}={value_str}"

            cached_value: Optional[Any] = await cache_manager.get(
                domain=domain,
                key=_key
            )
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)
            await cache_manager.set(
                domain=domain,
                key=_key,
                value=result,
                ttl=ttl
            )

            return result

        return wrapper

    return decorator
