from typing import Dict, Any, List

from backend.core.dependency_injection.db_container import DBContainer


class RepositoryContainer:
    def __init__(
        self,
        db_container: DBContainer,
        global_vars_map: Dict[str, Any],
        closeable_instances: List,
        is_transactional: bool,
    ):
        self.db_container = db_container

        self.global_vars_map = global_vars_map

        self.closeable_instances = closeable_instances
        self.is_transactional = is_transactional
