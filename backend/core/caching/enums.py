from enum import Enum


class CacheDomains(str, Enum):
    REPOSITORY = "repository"
    SERVICE = "service"
    AI = "ai"


class DBOperations(str, Enum):
    GET = "get"
    GET_MANY = "get_many"
