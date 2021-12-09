"""A program that searches flght data from Google Flights"""

import re
import threading
import datetime
import itertools
import logging

from db import commit_data, flights_table, get_existing_airport_combos, get_number_of_days_for_combo
from playwright.sync_api import sync_playwright, TimeoutError
from trips import Trips


AIRPORTS = ('ATL', 'LAX', 'ORD', 'DFW', 'DEN', 'JFK', 'SFO', 'LAS', 'PHX', 'IAH', 'DEN', 'CLT', 'LAS', 'MCO', 'SEA', 'MIA', 'FLL', 'SFO', 'EWR', 'MSP', 'FLL', 'BOS', 'DTW', 'PHL', 'LGA', 'BWI', 'SLC', 'SAN', 'DCA', 'TPA', 'IAD', 'MDW', 'HNL', 'PDX', 'SJC', 'DAL', 'MSY', 'STL', 'OAK', 'SMF', 'BNA')

START_DATE = datetime.datetime(2022, 1, 11)
TRIP_TYPE = Trips.ONE_WAY
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
    for combination in combinations:
        # check if combination identical or incomplete
        if get_number_of_days_for_combo(*combination) == NUM_DAYS:
            continue
        yield combination

def search_flights(page, airport_combo: tuple[str, str]) -> None:
    """
    Searches for flights from airport_from to airport_to
    """

    page.goto('https://www.google.com/travel/flights')
    
    airport_from, airport_to = airport_combo

    # select trip type
    page.click('//span[text()="Round trip"]')
    page.click('//li[@role="option" and text()="{}"]'.format(TRIP_TYPE.value))

    # enter departure airport in search
    page.click('//div[@aria-placeholder="Where from?"]')
    page.wait_for_timeout(500)
    page.keyboard.type(airport_from)
    page.press('//div[@aria-placeholder="Where from?"]', 'Enter')
    page.wait_for_timeout(1000)

    # enter destination airport in search
    page.click('//div[@aria-placeholder="Where to?"]')
    page.wait_for_timeout(500)
    page.keyboard.type(airport_to)
    page.press('//div[@aria-placeholder="Where to?"]', 'Enter', delay=100)
    page.wait_for_timeout(1000)

    # enter departure date
    start_date_str = START_DATE.strftime('%b %d')
    page.click('//input[@placeholder="Departure date"]')
    page.wait_for_timeout(2000)
    page.keyboard.type(start_date_str)

    # set return date if round trip
    # TODO: change return date to be specific date rather than n days after departure date
    if TRIP_TYPE == Trips.ROUND_TRIP:
        page.click('(//input[@placeholder="Return date"])[2]')
        page.keyboard.press('Control+A')
        page.wait_for_timeout(2000)
        return_date_str = START_DATE + datetime.timedelta(days=NUM_DAYS)
        page.keyboard.type(return_date_str.strftime('%b %d'))
        
    # click search button
    for _ in range(5):
        page.wait_for_timeout(300)
        page.keyboard.press('Enter')


    #TODO: Add validation that date accurately matches what was entered
    # incorrect search params, try again
    if 'search' not in page.url or 'explore' in page.url:
        search_flights(page, airport_combo)

    
def increment_date_on_page(page, increment=1):
    """
    Increments depart date on page by n days
    Default is 1 day
    """

    for _ in range(increment):
        try:
            page.click('//input[@type="text" and @value and @placeholder="Departure date"]/../div[3]')
        except TimeoutError:
            print('Something went wrong. Reloading page...')
            page.reload()
            increment_date_on_page(page)


def get_flight_data(page, current_day:str, flights_combo:tuple[str, str]) -> list[dict]:
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
    flights_selector = page.query_selector_all('//div[contains(text(), "kg CO")]/ancestor::node()[5]/div[2]/div[2]/div/span[contains(@aria-label, "Leaves")]/ancestor::node()[7]')
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

        departure_airport, arrival_airport = flights_combo


        flights.append({'price': price, 'depart_time': depart_time, 'arrival_time': arrival_time, 'departure_airport': departure_airport, 'arrival_airport': arrival_airport, 'airlines': ','.join(airlines), 'num_stops': num_stops})
    
    # all flights have same date
    date = START_DATE + datetime.timedelta(days = current_day)
    date_str = date.strftime('%m/%d/%Y')

    for flight in flights:
        flight['depart_date'] = date_str

    return flights

def main(combination, start_page=0):
    
    try:
        sema.acquire()
        current_day = start_page or 0
        with sync_playwright() as p:
                browser = p.firefox.launch(headless=False, slow_mo=50)
                page = browser.new_page()
                page.set_default_timeout(50000)
                # search for flights
                search_flights(page, combination)
                page.wait_for_timeout(5000)
                for _ in range(NUM_DAYS):
                    flights = get_flight_data(page, current_day, combination)
                    if flights:
                        global lock
                        with lock:
                            commit_data(flights_table, flights)
                            
                    increment_date_on_page(page)
                    current_day += 1
        sema.release()
    except:
        sema.release()

if __name__ == '__main__':
    threads = []
    lock = threading.Lock()
    sema = threading.Semaphore(value=4)
    for combination in get_airport_combination(AIRPORTS):
        t = threading.Thread(target=main, args=(combination,))
        threads.append(t)
    for t in threads:
        t.start()  
    
    for t in threads:
        t.join()
    
    print('Job done!')
    