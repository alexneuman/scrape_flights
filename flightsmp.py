"""A multiprocess program that searches flght data from Google Flights"""

import re
import multiprocessing
import datetime
import itertools
from queue import Queue

from db import commit_data, flights_table, get_existing_airport_combos, get_number_of_days_for_combo
from playwright.sync_api import sync_playwright


AIRPORTS = ('ATL', 'LAX', 'ORD', 'DFW', 'DEN', 'JFK', 'SFO', 'LAS', 'PHX', 'IAH', 'DEN', 'CLT', 'LAS', 'MCO', 'SEA', 'MIA', 'FLL', 'SFO', 'EWR', 'MSP', 'FLL', 'BOS', 'DTW', 'PHL', 'LGA', 'BWI', 'SLC', 'SAN', 'DCA', 'TPA', 'IAD', 'MDW', 'HNL', 'PDX', 'SJC', 'DAL', 'MSY', 'STL', 'OAK', 'SMF', 'BNA')
START_DATE = datetime.datetime(2021, 12, 14)
NUM_DAYS = 7


def get_airport_combination(airports):
    """
    Returns all possible combinations of airports
    """

    possible_combinations = set(itertools.permutations(airports, 2))
    existing_combos = get_existing_airport_combos()

    # filter out existing combinations
    combinations = possible_combinations - existing_combos
    
    # all possible combinations of airports
    for combination in itertools.chain(combinations, (tuple(reversed(c)) for c in combinations)):
        # check if combination not identical, incomplete
        if combination[0] == combination[1] or get_number_of_days_for_combo(*combination) == NUM_DAYS:
            continue
        yield combination

def search_flights(page, airport_from: str, airport_to: str) -> None:
    """
    Searches for flights from airport_from to airport_to
    """

    # enter departure airport in search
    page.click('//div[@aria-placeholder="Where from?"]')
    page.keyboard.type(airport_from)
    page.press('//div[@aria-placeholder="Where from?"]', 'Enter')

    # enter destination airport in search
    page.click('//div[@aria-placeholder="Where to?"]')
    page.keyboard.type(airport_to)
    page.press('//div[@aria-placeholder="Where to?"]', 'Enter')
    
    #execute search
    page.wait_for_timeout(2000)
    try:
        page.click('//button[@jslog and @jscontroller]/..[contains(@jsaction, "click")]')
    except:
        page.reload()
        search_flights(page, airport_from, airport_to)


def increment_date_on_page(page, increment=1):
    """
    Increments depart date on page by n days
    Default is 1 day
    """

    for _ in range(increment):
        page.wait_for_timeout(1000)
        try:
            page.click('//input[@type="text" and @value and @placeholder="Departure date"]/../div[3]')
        except Exception:
            print('Something went wrong. Reloading page...')
            page.reload()
            increment_date_on_page(page)


def get_flight_data(page, current_day) -> list[dict[str, str]]:
    """Gets flight data"""

    # page.wait_for_timeout(1500)
    # # trigger event to show more flights
    try:
        page.click('//span[contains(text(), "more flights")]')
    except:
        pass
    page.wait_for_timeout(500)
    #top level flight info
    flights = []
    flights_selector = page.query_selector_all('//div[contains(text(), "kg CO")]/../../../../../div[2]/div[2]/div/span[contains(@aria-label, "Leaves")]/ancestor::node()[7]')
    for flight in flights_selector:
        try:
            price = flight.query_selector('//span[contains(text(), "$")]').text_content().replace('$', '').replace(',', '')
        except:
            # no flight info
            continue
        depart_time = flight.query_selector('//span[contains(@aria-label, "Depart")]').text_content()
        arrival_time = flight.query_selector('//span[contains(@aria-label, "Arrival")]').text_content().replace('+1', '')
        # remove any timezone info from arrival time
        arrival_time = re.search('.+M', arrival_time).group(0)

        airlines_selector = flight.query_selector('//div/div/div/div/div[2]/div[2]')
        airlines = []
        for span in airlines_selector.query_selector_all('span'):
            text = span.text_content()
            #filter out junk
            if len(text) > 5 and len(text) < 50 and 'Separate' not in text and 'Operated' not in text:
                airlines.append(text)

        # number of stops
        num_stops = flight.query_selector('//span[contains(text(), "stop")]').text_content()
        if num_stops == 'Nonstop':
            num_stops = 0 
        else:
            num_stops = re.search('.*\d', num_stops).group(0)

        try:
            departure_airport = flight.query_selector('//div[contains(text(), " hr") and contains(text(), " min")]/../span/g-bubble/span').text_content()
            arrival_airport = flight.query_selector('//div[contains(text(), " hr") and contains(text(), " min")]/../span/g-bubble[2]/span').text_content()
        except:
            # TODO: correct the xpath when the element is not found
            departure_airport = ''
            arrival_airport = ''

        is_round_trip = 1 if flight.query_selector('//div[contains(text(), "round")]').text_content() == 'round trip' else 0

        flights.append({'price': price, 'depart_time': depart_time, 'arrival_time': arrival_time, 'departure_airport': departure_airport, 'arrival_airport': arrival_airport, 'airlines': ','.join(airlines), 'num_stops': num_stops, 'is_round_trip': is_round_trip})
    
    # all flights have same date
    date = START_DATE + datetime.timedelta(days = current_day)
    date_str = date.strftime('%m/%d/%Y')
    for flight in flights:
        flight['depart_date'] = date_str

    return flights

def main(combination, start_page=0):
    current_day = start_page or 0
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False, slow_mo=50)
            page = browser.new_page()
            page.goto('https://www.google.com/travel/flights')

            airport_from, airport_to = combination
            # search for flights
            search_flights(page, airport_from, airport_to)
            page.wait_for_timeout(5000)
            for _ in range(NUM_DAYS):
                flights = get_flight_data(page, current_day)
                commit_data(flights_table, flights)
                increment_date_on_page(page)
                current_day += 1

    except:
        print('FDIFJIDFJIJF')
        main(combination, start_page=current_day)


if __name__ == '__main__':
    pool = multiprocessing.Pool(processes=16)
    # pool multiprocessing for all combinations
    pool.map(main, get_airport_combination(AIRPORTS))