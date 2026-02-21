import inspect
import logging
from functools import wraps
from typing import Callable, Any, get_type_hints, Dict, List
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar, Token

logger = logging.getLogger(__name__)


class AppContainer:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AppContainer, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return getattr(cls, "_instance")

    def __init__(self):
        if self._initialized:
            return

        self.context_vars_map: Dict[str, ContextVar[Any]] = {
            "closeable_instances": ContextVar("closeable_instances", default=None),
            "is_transactional": ContextVar("is_transactional", default=False),
        }

        self.params_factory_map: Dict[str, Callable[[], Any]] = {}

        self.transaction_params = []

        self.types_map: dict[type, type] = {}

        self.global_vars_map: Dict[str, Any] = {
            "context_vars_map": self.context_vars_map,
            "params_factory_map": self.params_factory_map,
            "types_map": self.types_map,
        }
        self.global_vars_map["global_vars_map"] = self.global_vars_map

        self._initialized = True

    def register_global_var(self, name: str, value: Any) -> None:
        self.global_vars_map[name] = value

    def register_factory_var(self, name: str, factory: Callable[[], Any], transactional: bool = False) -> None:
        self.params_factory_map[name] = factory
        if transactional:
            self.transaction_params.append(name)

    def register_type_var(self, key: type, value: type) -> None:
        self.types_map[key] = value

    def register_context_var(self, var: ContextVar) -> None:
        self.context_vars_map[var.name] = var

    def _apply_injection(self, function: Callable, kwargs: Dict) -> Dict:
        signature = inspect.signature(function)
        type_hints = get_type_hints(function)

        init_kwargs: Dict = {}
        for name, param in signature.parameters.items():
            if name == "self":
                continue

            param_type = type_hints.get(name)
            if param_type in self.types_map:
                init_kwargs[name] = self.types_map[param_type](
                    **self._apply_injection(self.types_map[param_type].__init__, {})
                )

            if name in self.params_factory_map:
                param_value: Any = self.params_factory_map[name]()
                init_kwargs[name] = param_value

                if name in self.transaction_params:
                    closeable_instances: List = self.context_vars_map["closeable_instances"].get()
                    closeable_instances.append(param_value)

            if name in self.global_vars_map:
                init_kwargs[name] = self.global_vars_map[name]

            if name in self.context_vars_map:
                init_kwargs[name] = self.context_vars_map[name].get()

        kwargs.update(init_kwargs)

        return init_kwargs

    def set_context_value(self, var_name: str, value: Any) -> Token:
        return self.context_vars_map[var_name].set(value)

    @contextmanager
    def _context_var_set(self, var_name: str, value: Any = None):
        if value is None:
            token: Token = self.set_context_value(var_name, self.context_vars_map[var_name].get())
        else:
            token: Token = self.set_context_value(var_name, value)

        try:
            yield
        finally:
            self.context_vars_map[var_name].reset(token)

    @contextmanager
    def _init_context(self, transaction: bool):
        with ExitStack() as stack:
            for context_var_name in self.context_vars_map.keys():
                stack.enter_context(
                    self._context_var_set(context_var_name)
                )

            self.context_vars_map["closeable_instances"].set([])
            self.context_vars_map["is_transactional"].set(transaction)
            yield

    def inject(self, params: list, transaction: bool = False):
        def decorator(func):
            signature = inspect.signature(func)
            type_hints = get_type_hints(func)
            is_async_gen = inspect.isasyncgenfunction(func)

            # Keep only the parameters that are NOT injected in the outward API
            new_params = [
                param
                for name, param in signature.parameters.items()
                if type_hints.get(name) not in self.types_map
                    and name not in self.params_factory_map
                    and name not in self.context_vars_map
                    and name not in self.global_vars_map
            ]
            new_signature = inspect.Signature(new_params)

            if not is_async_gen:
                # Regular async function case
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    with self._init_context(transaction):
                        try:
                            self._apply_injection(func, kwargs)
                            result = await func(*args, **kwargs)

                            if transaction:
                                for closeable_instance in self.context_vars_map["closeable_instances"].get():
                                    await closeable_instance.commit()

                        except Exception as e:
                            # Preserve original logic: rollback only when not transactional
                            if not transaction:
                                for closeable_instance in self.context_vars_map["closeable_instances"].get():
                                    await closeable_instance.rollback()
                            raise
                        finally:
                            for closeable_instance in self.context_vars_map["closeable_instances"].get():
                                await closeable_instance.close()

                        return result
            else:
                # Async generator function case
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    with self._init_context(transaction):
                        agen = None
                        try:
                            self._apply_injection(func, kwargs)
                            agen = func(*args, **kwargs)  # async generator
                            async for item in agen:
                                yield item

                            if transaction:
                                for closeable_instance in self.context_vars_map["closeable_instances"].get():
                                    await closeable_instance.commit()

                        except Exception:
                            # On error, mirror original behavior
                            if not transaction:
                                for closeable_instance in self.context_vars_map["closeable_instances"].get():
                                    await closeable_instance.rollback()
                            raise
                        finally:
                            # Ensure generator is closed if consumer breaks early
                            if agen is not None:
                                try:
                                    await agen.aclose()
                                except Exception:
                                    # ignore close errors; resources still closed below
                                    pass

                            for closeable_instance in self.context_vars_map["closeable_instances"].get():
                                await closeable_instance.close()

            wrapper.__signature__ = new_signature
            return wrapper

        return decorator
