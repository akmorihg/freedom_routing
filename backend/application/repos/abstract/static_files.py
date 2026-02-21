from abc import ABC

from backend.core.abstract.repository import IRepository


class AbstractStaticFileRepository(
    IRepository,
    ABC
):
    pass
