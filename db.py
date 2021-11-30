"""Airline database management"""

import time

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, UniqueConstraint, insert, select
from sqlalchemy.exc import IntegrityError


engine = create_engine('sqlite:///airline.db', echo=True, future=True)
metadata = MetaData()

flights_table = Table(
    'flights', 
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('price', String(30)),
    Column('depart_time', String(30)),
    Column('arrival_time', String(30)),
    Column('depart_date', String(64)),
    Column('arrival_airport', String(64)),
    Column('departure_airport', String(64)),
    Column('airlines', String(128)),
    Column('num_stops', Integer()),
    Column('is_round_trip', Boolean()),

    # UniqueConstraint('depart_time', 'arrival_time', 'price', 'depart_date', 'airlines')
)

metadata.create_all(engine)

def commit_data(table, data):
    """
    Inserts data into specified table
    """
    with engine.begin() as conn:
        try:
            conn.execute(insert(table), data)
        except IntegrityError as e:
            print(e)

def get_existing_airport_combos() -> set:
    """
    Returns all distinct combinations of airports
    """
    with engine.begin() as conn:
        query = select([flights_table.c.departure_airport, flights_table.c.arrival_airport]).distinct().where(flights_table.c.departure_airport != '')
        return set(conn.execute(query).fetchall())

def get_number_of_days_for_combo(depart_airport, arrive_airport):
    """
    Returns number of days for a given combination of airports
    Used to determine whether a given airport combo is complete
    """
    with engine.begin() as conn:
        query = select([flights_table.c.depart_date]).distinct().where(flights_table.c.departure_airport == depart_airport, flights_table.c.arrival_airport == arrive_airport).group_by(flights_table.c.depart_date, flights_table.c.departure_airport, flights_table.c.arrival_airport)
        return len(set(conn.execute(query).fetchall()))