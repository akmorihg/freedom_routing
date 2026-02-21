from sqlalchemy import Column, Integer, String, ForeignKey

from backend.infrastructure.db.base import Base


class Country(Base):
    __tablename__ = 'countries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)


class Region(Base):
    __tablename__ = 'regions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=False)


class City(Base):
    __tablename__ = 'cities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)


class Address(Base):
    __tablename__ = 'addresses'

    id = Column(Integer, primary_key=True, autoincrement=True)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=False)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=False)
    city_id = Column(Integer, ForeignKey('cities.id'), nullable=False)
    street = Column(String, nullable=False)
    home_number = Column(String, nullable=False)
