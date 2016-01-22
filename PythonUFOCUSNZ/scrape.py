#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Script to parse UFO reports from UFOcusNZ

Author: Richard Law
Contact: richard.m.law@gmail.com

Handy:
https://www.airpair.com/python/posts/
using-python-and-qgis-for-geospatial-visualization
'''

import dateutil.parser
from urllib import urlopen
import re
import string
import os
import HTMLParser

# pylint: disable=import-error
from BeautifulSoup import BeautifulSoup
import pandas as pd
from geopy.geocoders import (
    Nominatim
    # OpenMapQuest
)
from geopy.exc import GeocoderTimedOut
import json
from geojson import (
    Point,
    Feature,
    FeatureCollection
)

def handle_special_date_exception(date_string, exc):
    '''
    There are several special cases of weird, human-entered dates in the
    source information. Some of this is just formatted in a way that
    dateutil.parse cannot interpret. Others are date ranges for observations.
    This function should be called when an exception is noted by dateutil
    when parsing a date string. If the date_string dateutil is attempting to
    interpret is in the list, then the "corrected" date is returned, also as a
    string. Otherwise the Exception `exc` is raised.

    This function lists these special cases as a dictionary: the value of
    each special-case-key is my interpretation of what it is best recorded as.
    This is solely down to my judgement, and date range information is
    deliberately lost as I can't yet be bothered considering that as a
    possibility.
    '''
    exceptions = {'Monday 17 or Tuesday 18 May 2010': '17 May 2010',
    'Sunday 26 Sept 2010': '26 September 2010',
    'late October 2010': '27 October 2010',
    'first week of November': '1 November 2010',
    'between 1-8 June 2013': '1 June 2013',
    'week of 12-14 May 2014': '12 May 2014',
    '21 Octover 2014': '21 October 2014',
    'early May 2015': '3 May 2015',
    'Late August or early September, 1971': '31 august 1971',
    'Last quarter of 1999': '15 November 1999',
    'Exact date unknown; between 1957 and 1968': '1 January 1957'}
    if date_string.strip() in exceptions.keys():
        return exceptions[date_string.strip()]
    else:
        err = 'dateutil could not parse "{}"'.format(date_string)
        print '\n{error}\n'.format(error=err)
        raise exc

def parse_date(date_string):
    '''
    Attempts to parse a string represening a datetime into a datetime object
    '''
    if date_string is not None:
        date_string = date_string.replace('NEW', '').strip()
        # date_string = filter(lambda x: x in string.printable, date_string)
        date_string = ''.join(
            [item for item in date_string if item in string.printable]
        )
        try:
            date_string = dateutil.parser.parse(date_string)
        # pylint: disable=broad-except
        except Exception, exc:
            date_string = handle_special_date_exception(date_string, exc)
            date_string = parse_date(date_string)
    return date_string

# pylint: disable=too-many-return-statements
def return_next_html_elem(soup, sighting_property, to_find='td', pattern='{}:'):
    '''
    Returns the subsequent HTML `to_find` element after <sighting_property>
    '''
    assert sighting_property in [
        'Date',
        'Time',
        'Location',
        'Features/characteristics',
        'Special features/characteristics',
        'Description'
    ]
    assert soup is not None

    pattern_re = re.compile(pattern.format(sighting_property))
    results = soup.find(to_find, text=pattern_re)

    if results is None:

        # Try a variety of corner cases

        # Sometimes it's "special"
        if sighting_property == 'Features/characteristics':
            return return_next_html_elem(
                soup, 'Special features/characteristics'
            )

        # Sometimes the colon is left off
        if ':' in pattern:
            pattern = '{}'
            return return_next_html_elem(
                soup, sighting_property, to_find=to_find, pattern=pattern
            )

        # Try with a strong tag
        if to_find != 'strong' and to_find != 'span':
            return return_next_html_elem(
            soup, sighting_property, to_find='strong'
        )

        # Try with a span tag
        if to_find != 'span':
            return return_next_html_elem(
            soup, sighting_property, to_find='span'
        )

        # Sometimes the html is mangled with <br> tags
        if '<br/>' not in pattern and \
        soup.get_text is not None and soup.find('br'):
            # text = filter(None, soup.get_text().strip().split("\n"))
            text = [
                item for item in soup.get_text().strip().split("\n") if item
            ]
            if pattern.format(sighting_property) not in text:
                return None # Simply doesn't exist
            return '<br>'.join(text[text.index('Description')+1:])

        # If all else fails
        return None

    # Once the identifier is found, grab the next table row, which is the *data*
    try:
        result = results.findNext('td').text
    except Exception, exc:
        raise exc

    # Remove &nbsp;
    result = result.replace('&nbsp;', '')

    # Some final encoding issues
    if isinstance(result, basestring):
        result = result.encode('utf8')
    else:
        result = unicode(result).encode('utf8')

    return result

def substitutions_for_known_issues(locations):
    '''
    Substitutes bad strings for better ones. Hard earned through some trial
    and error.
    '''
    corrections = {
        # Nominatim doesn't like this
        'Coromandel Peninsula': 'Coromandel',
        # Pakeha-ism
        'Whangaparoa': 'Whangaparaoa',
        # There is no Pukekohe, Frankton
        'Pukekohe, Frankton': 'Pukekohe, Franklin',
        # Nominatim doesn't understand "West Auckland"
        'west Auckland': 'Henderson, Auckland',
        'Waitakere City': 'Waitakere',
        'Taumaranui': 'Taumarunui',
        'Taumaranui, King Country': 'Taumarunui',
        'Otematata, Waitati Valley, North Otago': 'Otematata',
        'Takapuna Beach': 'Takapuna',
        'Golden Springs, Reporoa, Bay of Plenty': 'Reporoa',
        'Puketona Junction, south of Kerikeri, New Zealand':
            'Te Ahu Ahu Road, New Zealand', # Manually checked
        # Ohinepaka not in OSM; this is nearest landmark
        'Ohinepaka, Wairoa': 'Kiwi Valley Road, Wairoa',
        'Gluepot Road, Oropi': 'Gluepot Road',
        'Rimutaka Ranges, Wairarapa': 'Rimutaka, Wairarapa',
        # Ashburton is not in Otago
        'Ashburton, Otago': 'Ashburton, Ashburton District',
        'National Park village, Central': 'National Park',
        'Mareawa, Napier': 'Marewa, Napier',
        'Clarence River mouth, Lower Marlborough,': 'Clarence',
        'Oputama, Mahia Peninsula': 'Opoutama, Mahia',
        'Taupo, Central': 'Taupo',
        'The Ureweras': 'Sister Annie Road, Whakatane',
        'Spray River': 'Waihopai Valley Road',
        'Viewed from Cambridge, but activity over Hamilton': 'Hamilton',
        'Cashmere Hills, Christchurch': 'Cashmere, Christchurch',
        # NOTE: Nominatim does not understand 'Wairarapa',
        'Wairarapa': 'Wellington',
        'Whangapoua Beach': 'Whangapoua',
        'Marychurch Rd, Cambridge, Waikato': 'Marychurch Rd, Waikato',
        'Waihi, Coromandel/Hauraki': 'Waihi, Hauraki',
        'Waihi, Coromandel': 'Waihi, Hauraki',
        'Eastern BOP': 'Bay of Plenty',
        'BOP': 'Bay of Plenty',
        'Kaweka Ranges, Hawkes Bay': 'Kaweka',
        'Waikawa Beach, Levin': 'Waikawa Beach, Horowhenua',
        'Waikawa Beach, Otaki': 'Waikawa Beach, Horowhenua',
        # The King Country is not an actual district
        'King Country': '',
        'Waimate, between Timaru and Oamaru': 'Waimate',
        'Alderman Islands, some 20km east of Tairua &amp; Pauanui, \
            Coromandel': 'Ruamahuaiti Island',
        'Tapeka Point: Bay of Islands': 'Tapeka',
        'Raglan Beach': 'Raglan',
        'Waitemata Harbour': '',
        'North Shore City': 'North Shore',
        'Waitarere Beach, Levin': 'Waitarere Beach',
        'Snells Beach, Warkworth': 'Snells Beach',
        "Snell's Beach": 'Snells Beach',
        'Birds ferry Road, Westport': 'Birds Ferry Road',
        'Waiheke Island': 'Waiheke',
        'Forrest Hill, Sunnynook': 'Forrest Hill',
        'South Auckland': 'Auckland',
        'Otara, East Tamaki': 'Otara'
    }
    for loc in locations:
        for k in corrections.keys():
            if k in loc:
                yield loc.replace(k, corrections[k])

def strip_nonalpha_at_end(location):
    '''
    Remove non-letter characters at the end of the string
    '''
    valid = ['(', ')']
    loc = location
    if not loc[-1].isalpha():
        for char in reversed(location):
            if not char.isalpha() and char not in valid:
                loc = loc[:-1]
            else:
                return loc
    return loc

# pylint: disable=dangerous-default-value
def strip_conjunctions_at_start(
    location, conjunctions=['of', 'to', 'and', 'from', 'between']):
    '''
    Removes conjunctions at the start of a string.
    '''
    for conjunction in conjunctions:
        if location.strip().startswith(conjunction):
            yield location.strip()[len(conjunction):].strip()
        else:
            yield location

# pylint: disable=anomalous-backslash-in-string
# pylint: disable=invalid-name
def return_location_without_non_title_case_and_short_words(
    location, short=1, pattern='\W*\b\w{{short}}\b'):
    '''
    Does what it says, useful to remove guff from a string representing a
    location, which frequently improves poor geocoding.
    '''
    location = ' '.join([s for s in location.split(' ') if s.istitle()])
    pattern = re.compile(pattern.format(short=short))
    match = pattern.findall(location)
    for sub in match:
        location = location.replace(sub, '')
    return location

# pylint: disable=anomalous-backslash-in-string
def yield_locations_without_symbol(location, pattern, symbol):
    '''
    Generator function; best illustrated with the following:
    >>> location = 'Takanini/Papakura, Auckland, New Zealand'
    >>> for loc in get_locations_with_slash(location):
    >>>    print loc
    'Takanini, Auckland, New Zealand'
    'Papakura, Auckland, New Zealand'
    '''
    if symbol not in location:
        return
    pattern = re.compile(pattern)
    for m in pattern.finditer(location):
        m = m.group()
        for sub in m.split(symbol):
            yield location.replace(m, sub)

# pylint: disable=anomalous-backslash-in-string
def return_location_without_bracketed_clause(
    location, pattern='\s\([\w\s]+\)'):
    '''
    Returns location without a bracketed clause:
    >>> loc = 'Manukau (near Auckland airport), Auckland, New Zealand'
    >>> return_location_without_bracketed_clause(loc)
    Manukau, Auckland, New Zealand
    '''
    if '(' not in location or ')' not in location:
        return location
    pattern = re.compile(pattern)
    return pattern.sub('', location)

# pylint: disable=no-init
# pylint: disable=too-few-public-methods
class Bcolors(object):
    '''
    Print colours to the terminal! Pretty rainbows...
    '''
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# pylint: disable=too-many-instance-attributes
class UFOSighting(object):
    '''
    Object representing a UFO sightning, with a URL, date, time, location, some
    features, a text description, and geocoding metadata.
    '''
    # pylint: disable=too-many-arguments
    def __init__(self, source, date, time, location, features, description):
        self.source = source # Link to page
        self.date = parse_date(date) # Python date
        self.time = time # String time
        self.location = location # String location (will be used in geocode)
        self.features = features
        self.description = description
        # These can be updated by calling geocode(); but don't do that in
        # __init__ as nominatim needs to query a REST API
        self.latitude = None
        self.longitude = None
        self.geocoded_to = ""
        self.geocode_attempts = 1
        self.already_attempted = set([])

    def __str__(self):
        text = '<0> UFOSighting <0>'
        for k, val in self.__dict__.items():
            text += '\n{k}: {v}'.format(k=k.title(), v=val)
        text += '\n\nCopyright UFOCUS NZ\nUsed without permission'
        return text

    def __tuple__(self):
        return (
            self.date, self.time, self.location, self.geocoded_to,
            self.geocode_attempts, self.latitude, self.longitude,
            self.features, self.description
        )

    def __geojson__(
        self, exclude=['longitude', 'latitude', 'already_attempted']):
        h = HTMLParser.HTMLParser()
        if not (self.longitude and self.latitude):
            return None
        return Feature(
            geometry=Point((self.longitude, self.latitude)),
            properties={
                key: h.unescape(str(value)) for key, value in \
                self.__dict__.items() if key not in exclude
            }
        )

    def is_valid(self):
        '''
        Retutns boolean indicating whether or not an HTML actually has content
        '''
        for prop in self.__tuple__():
            if prop is not None:
                return True
        return False

    def attempt_geocode(self, location,
        bias='New Zealand', timeout=6, exactly_one=True, debug=True
        ):
        '''
        Attempts a geocode, returning None, False, or True acccording
        to whether or not the operation is successful, or not, or somehow
        invalid (None). If successful, has side effect of setting self.latitude,
        self.longitude, and self.geocoded_to
        '''
        geolocator = Nominatim(country_bias=bias, timeout=timeout)
        # geolocator = OpenMapQuest(timeout=timeout)
        location = location.strip()
        # Remove repeat white space
        location = ' '.join([segment for segment in location.split()])
        if location in self.already_attempted:
            return None
        self.already_attempted.add(location)
        if location == '':
            self.latitude, self.longitude = None, None
            return False # Failure
        # Strip non-alpha characters at end of location
        location = strip_nonalpha_at_end(location)
        if debug:
            print repr(location),
        try:
            geocoded = geolocator.geocode(location, exactly_one=exactly_one)
        except GeocoderTimedOut:
            # Just try again
            geocoded = self.attempt_geocode(location)

        if geocoded is not None:
            self.latitude = geocoded.latitude
            self.longitude = geocoded.longitude
            self.geocoded_to = location
            if debug:
                print self.latitude, self.longitude,
                print Bcolors.OKBLUE + '← success' + Bcolors.ENDC
            return True # Success

        if debug:
            print Bcolors.FAIL + '← fail' + Bcolors.ENDC
        return None # No result, but there are more options to try

    def geocode(self, debug=False):
        '''
        Updates self.latitude and self.longitude if a geocode is successsful;
        otherwise leaves them as the default (None).
        Uses Nominatim.
        Returns False if the location could not be geocoded, returns True when
        the geocode is sucessful.

        Tip: use geocode=False when instantiating, and then do a batch geocode
        using multiple threads with multiprocessing!
        '''
        if not self.location:
            return False

        location = self.location

        # TODO:
        # '12:00 am, New Zealand' -37.7894134 175.2850399
        if location == '12:00 am':
            return None

        if debug:
            print repr(self.location) + ' ← original'

        # Remove HTML entities
        location = location.encode("utf8")
        for char in ['&rsquo;', '\r', '\n']:
            location = location.replace(char, '')

        # Remove repeat white space
        location = ' '.join([segment for segment in location.split()])

        location = strip_nonalpha_at_end(location)

        # North Island and South Island are not useful to the geocoder
        for island in [
            'North Island', 'South Island',
            'NI', 'SI',
            'Nth Island', 'Sth Island',
            'North Is', 'South Is'
        ]:
            if not strip_nonalpha_at_end(location).endswith(island) and not \
            strip_nonalpha_at_end(location).endswith(island + ', New Zealand'):
                continue
            location = location.replace(island, '')

        # It helps to add "New Zealand" even though a country bias is used
        # NOTE that there are (for some reason) some non-NZ observations
        non_nz_places = ['Antarctica', 'Timor Sea', 'South Pacific Ocean']
        append_nz = True
        for place in non_nz_places:
            if place in location:
                append_nz = False

        if append_nz:
            location.replace(' NZ', ' New Zealand')
            if not location.strip().endswith(','):
                location = location.strip() + ','
            if 'New Zealand' not in location:
                location = location.strip() + ' New Zealand'

        while True:

            # Try the location description, without leading conjunctions
            for loc in strip_conjunctions_at_start(location):
                gc = self.attempt_geocode(loc)
                if gc is not None:
                    return gc

            # If there's a slash in the name, split it into two attempts
            attempts_copy = self.already_attempted.copy()
            for loc in attempts_copy:
                for loc in yield_locations_without_symbol(
                    loc, '(\w*/[\w\s]*)', '/'
                ):
                    gc = self.attempt_geocode(loc)
                    if gc is not None:
                        return gc

            # If there's an ampersand in the name, split it into two attempts
            attempts_copy = self.already_attempted.copy()
            for loc in attempts_copy:
                for loc in yield_locations_without_symbol(
                    loc, '(\w*\s&amp;\s\w*)', '*'
                ):
                    gc = self.attempt_geocode(loc)
                    if gc is not None:
                        return gc


            # Try without a bracketed clause
            attempts_copy = self.already_attempted.copy()
            for loc in attempts_copy:
                gc = self.attempt_geocode(
                    return_location_without_bracketed_clause(loc)
                )
                if gc is not None:
                    return gc

            # Try with some common substitutions or known errors:
            attempts_copy = self.already_attempted.copy()
            for loc in substitutions_for_known_issues(attempts_copy):
                gc = self.attempt_geocode(loc)
                if gc is not None:
                    return gc

            # Try again without non-title-case words,
            # and without one-letter words
            attempts_copy = self.already_attempted.copy()
            for loc in attempts_copy:
                loc = return_location_without_non_title_case_and_short_words(
                    loc)
                gc = self.attempt_geocode(loc)
                if gc is not None:
                    return gc

            self.geocode_attempts += 1

            # Remove the first word of the location for next attempt
            location = ' '.join(location.split(' ')[1:])

            # While loop repeats

def get_all_sightings_as_list_of_UFOSighting_objects(
    link, geocode=True, debug=True):
    '''
    Returns a list of UFOSighting objects, scraped from one link to a page of
    sighting reports.

    <link> is a URL (string) that leads to a page of sighting reports on
    UFOCUS NZ's website. Must be in HTML format (<a href="the/url/path">)

    <geocode> defaults to false as it isn't compulsory and takes ages to compute
    (it needs to query a REST API).
    '''

    sightings = []

    for table in BeautifulSoup(urlopen(link)).findAll(
            'table',
            {'cellpadding': '3'}
        ):
        date = return_next_html_elem(table, 'Date')
        time = return_next_html_elem(table, 'Time')
        location = return_next_html_elem(table, 'Location')
        features = return_next_html_elem(
            table, 'Features/characteristics'
        )
        description = return_next_html_elem(table, 'Description')

        # Work-around to re-build paragraph breaks, which get lost because
        # they are <br> tags.
        if description is not None and description.strip():
            description_with_breaks = ''
            split_description = [d for d in description.split('.') if d is not \
            None and d.strip()]
            for i, d in enumerate(split_description[:-1]):
                if split_description[i+1][0].isalpha():
                    d += '.<br><br>'
                description_with_breaks += d
                description = description_with_breaks
                description += split_description[-1] + '.'

        ufo = UFOSighting(link, date, time, location, features, description)

        if not ufo.is_valid():
            # Ignore UFO sightings that have been misidentified
            # (Emtpy HTML tables)
            continue

        if geocode:
            if not ufo.geocode(debug=debug):
                # Ignore UFO sightings that cannot be geocoded
                continue

        sightings.append(ufo)

    return sightings

def export_ufos_to_csv(list_of_UFOSighting_objects):
    '''
    Given a list of all the UFO sightings found on the website as UFOSighting
    objects, exports them to a CSV.
    '''
    # Convert UFO objects to tuples
    all_sightings_as_tuples = [
        ufo.__tuple__() for ufo in list_of_UFOSighting_objects]

    # Create a pandas DataFrame from the list of tuples
    ufos_df = pd.DataFrame(all_sightings_as_tuples, columns=[
        'Date', 'Time', 'Location', 'Geocoded As', 'Geocode Attempts',
        'Latitude', 'Longitude', 'Features', 'Description'
    ])

    # Export the pandas DF to CSV
    ufos_df.to_csv(
        os.path.join(
            os.path.dirname(__file__),
            'ufos_data.csv'
        ), index=False, encoding='utf-8'
    )

    return None

def export_ufos_to_geojson(list_of_UFOSighting_objects):
    '''
    Given a list of all the UFO sightings found on the website as UFOSighting
    objects, exports them to GeoJSON. The list is sorted by date, because the
    leaflet timeslider doesn't sort on a key, and I can't work out how to do it
    in JavaScript. Therefore it also removes observations that don't have a date
    '''
    list_of_UFOSighting_objects = [
        l for l in list_of_UFOSighting_objects if (
            l is not None and l.date and l.latitude and l.longitude
        )
    ]
    list_of_UFOSighting_objects.sort(
        key=lambda x: x.date, reverse=False
    )
    fc = FeatureCollection(
        [ufo.__geojson__() for ufo in list_of_UFOSighting_objects]
    )
    with open(os.path.join(os.path.dirname(__file__), 'ufos_data.geojson'),
        'w') as outfile:
        json.dump(fc, outfile)

def geocode_worker(sighting):
    '''
    A single geocoding worker, to be run in its own wee process... and probably
    rate-limited
    '''
    sighting.geocode(debug=True)
    return sighting

def main(debug=False):
    '''Main loop'''
    def valid(tag):
        '''
        <tag> = an html tag that has an href

        Defines what an interesting hyperlink looks like, and returns True
        if the tag meets this criteria, False otherwise
        '''
        return 'New-Zealand-UFO-Sightings-' in tag['href']

    # Sightings page
    base_url = "http://www.ufocusnz.org.nz/content/Sightings/24.aspx"
    home_page = BeautifulSoup(urlopen(base_url))

    # Get list of valid links from home page
    # There is one for each year
    links = sorted(
        set([li for li in home_page.findAll(href=True) if valid(li)])
    )

    # There are some other links scattered around the website that have
    # reports in the same format
    # pylint: disable=line-too-long
    additional_links = [
        'http://www.ufocusnz.org.nz/content/Police/101.aspx',
        'http://www.ufocusnz.org.nz/content/Selection-of-Historic-Sighting-Reports/109.aspx',
        'http://www.ufocusnz.org.nz/content/1965---Unidentified-Submerged-Object-%28USO%29-spotted-by-DC-3-Pilot/82.aspx',
        'http://www.ufocusnz.org.nz/content/1968---Yellow-Disc-Descends-into-Island-Bay,-Wellington/104.aspx',
        'http://www.ufocusnz.org.nz/content/1974---Large-Object-Emerges-from-Sea-off-Aranga-Beach,-Northland/105.aspx',
        'http://www.ufocusnz.org.nz/content/1957-1968---Silver-Bullet-Bursts-Through-Antarctic-Ice/106.aspx'
    ]
    additional_links = [BeautifulSoup(str('<a href="{}">Link</a>'.format(li))).findAll(href=True)[0] for li in additional_links]
    # NOTE see here for more, although they conform less to the expected structure
    # http://www.ufocusnz.org.nz/content/Aviation/80.aspx

    links += additional_links

    links = set([l['href'] for l in links])

    # TODO caching

    # Flatten lists of UFOs for each link
    all_sightings = reduce(
        lambda x, y: x+y, [
            get_all_sightings_as_list_of_UFOSighting_objects(
                link, geocode=False, debug=debug
            ) for link in links
        ]
    )

    import multiprocessing

    pool = multiprocessing.Pool(
        processes=max(multiprocessing.cpu_count() - 2, 1)
    )
    pool.map(geocode_worker, all_sightings)

    # export_ufos_to_csv(all_sightings)
    export_ufos_to_geojson(all_sightings)

if __name__ == '__main__':
    main(debug=True)
    exit(0)
