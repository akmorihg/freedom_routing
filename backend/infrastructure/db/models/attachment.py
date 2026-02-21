from sqlalchemy import Column, Integer, String, ForeignKey

from backend.infrastructure.db.base import Base


class AttachmentType(Base):
    __tablename__ = 'attachment_types'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)


class Attachment(Base):
    __tablename__ = 'attachments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(Integer, ForeignKey('attachment_types.id'), nullable=False)
    key = Column(String, nullable=False)
