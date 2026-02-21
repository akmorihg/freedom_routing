from typing import Dict, Any

from backend.core.dependency_injection.db_container import DBContainer
from backend.core.dependency_injection.repository_container import RepositoryContainer


class ServiceContainer:
    def __init__(
        self,
        repository_container: RepositoryContainer,
        db_container: DBContainer,
        global_vars_map: Dict[str, Any],
    ):
        self.repository_container = repository_container
        self.db_container = db_container
        self.global_vars_map = global_vars_map
