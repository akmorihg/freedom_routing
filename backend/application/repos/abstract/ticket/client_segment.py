from abc import ABC

from backend.core.abstract.repository import IDBRepository
from backend.domain.ticket.entities import ClientSegmentEntity
from backend.domain.ticket.mappers import ClientSegmentMapper
from backend.infrastructure.db.models import ClientSegment


class AbstractClientSegmentRepository(
    IDBRepository[ClientSegment, ClientSegmentEntity, ClientSegmentMapper],
    ABC,
):
    pass
