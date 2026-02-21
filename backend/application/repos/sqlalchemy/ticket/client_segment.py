from backend.application.repos.abstract.ticket.client_segment import AbstractClientSegmentRepository
from backend.application.repos.sqlalchemy.base import BaseSQLAlchemyRepo
from backend.domain.ticket.entities import ClientSegmentEntity
from backend.domain.ticket.mappers import ClientSegmentMapper
from backend.infrastructure.db.models import ClientSegment


class SqlAlchemyClientSegmentRepository(
    BaseSQLAlchemyRepo[ClientSegment, ClientSegmentEntity, ClientSegmentMapper],
    AbstractClientSegmentRepository,
):
    model = ClientSegment
    entity_type = ClientSegmentEntity
    mapper = ClientSegmentMapper
