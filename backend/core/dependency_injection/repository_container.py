from backend.application.repos.abstract.location.address import AbstractAddressRepository
from backend.application.repos.abstract.location.city import AbstractCityRepository
from backend.application.repos.abstract.location.country import AbstractCountryRepository
from backend.application.repos.abstract.location.office import AbstractOfficeRepository
from backend.application.repos.abstract.location.region import AbstractRegionRepository
from backend.application.repos.abstract.manager.manager import AbstractManagerRepository
from backend.application.repos.abstract.manager.manager_position import AbstractManagerPositionRepository
from backend.application.repos.abstract.manager.manager_skills import AbstractManagerSkillRepository
from backend.application.repos.abstract.manager.skill import AbstractSkillRepository
from backend.application.repos.abstract.static_files import AbstractStaticFileRepository
from backend.application.repos.abstract.ticket.attachment import AbstractAttachmentRepository
from backend.application.repos.abstract.ticket.attachment_type import AbstractAttachmentTypeRepository
from backend.application.repos.abstract.ticket.client_segment import AbstractClientSegmentRepository
from backend.application.repos.abstract.ticket.gender import AbstractGenderRepository
from backend.application.repos.abstract.ticket.ticket import AbstractTicketRepository
from backend.application.repos.abstract.ticket.ticket_analysis import AbstractTicketAnalysisRepository
from backend.application.repos.abstract.ticket.ticket_attachment import AbstractTicketAttachmentRepository
from backend.application.repos.abstract.ticket.ticket_assignment import AbstractTicketAssignmentRepository
from backend.application.repos.sqlalchemy.location.address import SqlAlchemyAddressRepository
from backend.application.repos.sqlalchemy.location.city import SqlAlchemyCityRepository
from backend.application.repos.sqlalchemy.location.country import SqlAlchemyCountryRepository
from backend.application.repos.sqlalchemy.location.office import SqlAlchemyOfficeRepository
from backend.application.repos.sqlalchemy.location.region import SqlAlchemyRegionRepository
from backend.application.repos.sqlalchemy.manager.manager import SqlAlchemyManagerRepository
from backend.application.repos.sqlalchemy.manager.manager_position import SqlAlchemyManagerPositionRepository
from backend.application.repos.sqlalchemy.manager.manager_skills import SqlAlchemyManagerSkillRepository
from backend.application.repos.sqlalchemy.manager.skill import SqlAlchemySkillRepository
from backend.application.repos.sqlalchemy.static_files import MiniIORepository
from backend.application.repos.sqlalchemy.ticket.attachment import SqlAlchemyAttachmentRepository
from backend.application.repos.sqlalchemy.ticket.attachment_type import SqlAlchemyAttachmentTypeRepository
from backend.application.repos.sqlalchemy.ticket.client_segment import SqlAlchemyClientSegmentRepository
from backend.application.repos.sqlalchemy.ticket.gender import SqlAlchemyGenderRepository
from backend.application.repos.sqlalchemy.ticket.ticket import SqlAlchemyTicketRepository
from backend.application.repos.sqlalchemy.ticket.ticket_analysis import SqlAlchemyTicketAnalysisRepository
from backend.application.repos.sqlalchemy.ticket.ticket_attachment import SqlAlchemyTicketAttachmentRepository
from backend.application.repos.sqlalchemy.ticket.ticket_assignment import SqlAlchemyTicketAssignmentRepository
from backend.core.dependency_injection.db_container import DBContainer
from typing import Dict, Any, List

from backend.settings import Settings


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
        self._cached_internal_session = None

    def _internal_session(self):
        if self._cached_internal_session is None:
            self._cached_internal_session = self.db_container.internal_session()
            self.closeable_instances.append(self._cached_internal_session)
        return self._cached_internal_session

    @property
    def attachment_type_repo_(self) -> AbstractAttachmentTypeRepository:
        return SqlAlchemyAttachmentTypeRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def attachment_repo_(self) -> AbstractAttachmentRepository:
        return SqlAlchemyAttachmentRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def country_repo_(self) -> AbstractCountryRepository:
        return SqlAlchemyCountryRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def region_repo_(self) -> AbstractRegionRepository:
        return SqlAlchemyRegionRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def city_repo_(self) -> AbstractCityRepository:
        return SqlAlchemyCityRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def address_repo_(self) -> AbstractAddressRepository:
        return SqlAlchemyAddressRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def manager_position_repo_(self) -> AbstractManagerPositionRepository:
        return SqlAlchemyManagerPositionRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def manager_repo_(self) -> AbstractManagerRepository:
        return SqlAlchemyManagerRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def skill_repo_(self) -> AbstractSkillRepository:
        return SqlAlchemySkillRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def manager_skill_repo_(self) -> AbstractManagerSkillRepository:
        return SqlAlchemyManagerSkillRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def ticket_repo_(self) -> AbstractTicketRepository:
        return SqlAlchemyTicketRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def ticket_attachment_repo_(self) -> AbstractTicketAttachmentRepository:
        return SqlAlchemyTicketAttachmentRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def ticket_assignment_repo_(self) -> AbstractTicketAssignmentRepository:
        return SqlAlchemyTicketAssignmentRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def ticket_analysis_repo_(self) -> AbstractTicketAnalysisRepository:
        return SqlAlchemyTicketAnalysisRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def gender_repo_(self) -> AbstractGenderRepository:
        return SqlAlchemyGenderRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def office_repo_(self) -> AbstractOfficeRepository:
        return SqlAlchemyOfficeRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def client_segment_repo_(self) -> AbstractClientSegmentRepository:
        return SqlAlchemyClientSegmentRepository(
            session=self._internal_session(),
            is_transactional=self.is_transactional,
            use_cache=True,
            cache_manager=self.global_vars_map["cache_manager"],
        )

    @property
    def static_file_repo_(self) -> AbstractStaticFileRepository:
        settings: Settings = self.global_vars_map["settings"]

        return MiniIORepository(
            settings=settings,
        )
