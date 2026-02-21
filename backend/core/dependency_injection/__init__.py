from backend.core.caching.manager import cache_manager
from backend.core.dependency_injection.app_container import AppContainer
from backend.core.dependency_injection.db_container import DBContainer
from backend.core.dependency_injection.repository_container import RepositoryContainer
from backend.core.dependency_injection.service_container import ServiceContainer
from backend.settings import Settings

app_container = AppContainer()

def register_dependency_injection():
    settings = Settings()
    app_container.register_global_var("settings", settings)

    app_container.register_global_var("cache_manager", cache_manager)

    db_container = DBContainer(
        settings=settings,
    )
    app_container.register_global_var("db_container", db_container)

    app_container.register_type_var(RepositoryContainer, RepositoryContainer)
    app_container.register_type_var(ServiceContainer, ServiceContainer)

register_dependency_injection()
