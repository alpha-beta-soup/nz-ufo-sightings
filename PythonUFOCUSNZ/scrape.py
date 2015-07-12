#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Handy: https://www.airpair.com/python/posts/using-python-and-qgis-for-geospatial-visualization

import dateutil.parser
from urllib import urlopen
import re
import string
import os
import itertools

from BeautifulSoup import BeautifulSoup
import pandas as pd
from geopy.geocoders import Nominatim

def handle_special_date_exception(date_string, exception):
    # There are several special cases
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
    'Exact date unknown; between 1957 and 1968': None}
    if date_string.strip() in exceptions.keys():
        return exceptions[date_string.strip()]
    else:
        err = 'dateutil could not parse "{}"'.format(date_string)
        print '\n{}\n'.format(err)
        raise Exception(err)

def parse_date(date_string):
    if date_string is not None:
        date_string = date_string.replace('NEW','').strip()
        date_string = filter(lambda x: x in string.printable, date_string)
        try:
            date_string = dateutil.parser.parse(date_string)
        except Exception, e:
            date_string = handle_special_date_exception(date_string, e)
            date_string = parse_date(date_string)
    return date_string

def find_next_td_of_sighting_property(soup, sighting_property, to_find='td', pattern='{}:'):
    assert sighting_property in ['Date',
        'Time',
        'Location',
        'Features/characteristics','Special features/characteristics',
        'Description'
    ]
    assert soup is not None

    pattern_re = re.compile(pattern.format(sighting_property))
    results = soup.find(to_find, text=pattern_re)

    if results is None:

        #print soup, sighting_property

        # Try a variety of corner cases
        # TODO Make this cleaner

        # Sometimes it's "special"
        if sighting_property == 'Features/characteristics':
            return find_next_td_of_sighting_property(soup, 'Special features/characteristics')

        # Sometimes the colon is left off
        if ':' in pattern:
            pattern = '{}'
            return find_next_td_of_sighting_property(soup, sighting_property, to_find=to_find, pattern=pattern)

        # Try with a strong tag
        if to_find != 'strong' and to_find != 'span':
            return find_next_td_of_sighting_property(soup, sighting_property, to_find='strong')

        # Try with a span tag
        if to_find != 'span':
            return find_next_td_of_sighting_property(soup, sighting_property, to_find='span')

        # Sometimes the html is mangled with <br> tags
        if '<br/>' not in pattern and soup.get_text is not None and soup.find('br'):
            text = filter(None,soup.get_text().strip().split("\n"))
            if pattern.format(sighting_property) not in text:
                return None # Simply doesn't exist
            return ''.join(text[text.index('Description')+1:])

        # If all else fails
        # TODO log so can be corrected if possible
        return None

    # Once the identifier is found, grab the next table row, which is the *data*
    try:
        r = results.findNext('td').text
    except Exception, e:
        # TODO log
        raise e

    # Remove &nbsp;
    r = r.replace('&nbsp;','')

    # Some final encoding issues
    if isinstance(r,basestring):
        r = r.encode('utf8')
    else:
        r = unicode(r).encode('utf8')


    return r

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class UFOSighting(object):
    def __init__(self, source, date, time, location, features, description):
        self.source = source # Link to page
        self.date = parse_date(date) # Python date
        self.time = time # String time
        self.location = location # String location (will be used in geocode)
        self.features = features
        self.description = description
        # These can be updated by calling geocode(); but don't do that in __init__
        # as nominatim needs to query a REST API
        self.latitude = None
        self.longitude = None
        self.geocoded_to = ""
        self.geocode_attempts = 1

    def __str__(self):
        text = '<0> UFOSighting <0>'
        for k, v in self.__dict__.items():
            text += '\n{k}: {v}'.format(k=k.title(),v=v)
        text += '\n\nCopyright UFOCUS NZ\nUsed without permission'
        return text

    def __tuple__(self):
        return (self.date, self.time, self.location, self.geocoded_to, self.geocode_attempts, self.latitude, self.longitude, self.features, self.description)

    def isValid(self):
        for prop in self.__tuple__():
            if prop is not None:
                return True
        return False

    def geocode(self,bias='New Zealand',timeout=6,exactly_one=True):
        '''
        Updates self.latitude and self.longitude if a geocode is successsful;
        otherwise leaves them as the default (None_.
        Uses Nominatim.
        Returns False if the location could not be geocoded, returns True when
        the geocode is sucessful.
        '''
        def substitutions_for_known_issues(locations):
            corrections = {'Coromandel Peninsula': 'Coromandel', # Nominatim doesn't like this
                           'Whangaparoa': 'Whangaparaoa' # Pakeha-ism
                           }
            for loc in locations:
                for k in corrections.keys():
                    if k in loc:
                        yield loc.replace(k,corrections[k])

        def strip_nonalpha_at_end(location):
            # Remove non-letter characters at the end of the string
            loc = location
            if not loc[-1].isalpha():
                for i, c in enumerate(reversed(location)):
                    if not c.isalpha():
                        loc = loc[:-1]
                    else:
                        return loc
            return loc

        def attempt_geocode(location):
            location = location.strip()
            if location in self.already_attempted:
                return None
            self.already_attempted.add(location)

            if location == '':
                self.latitude, self.longitude = None, None
                return False # Failure

            location = strip_nonalpha_at_end(location)
            print repr(location),
            try:
                geocoded = geolocator.geocode(location,exactly_one=exactly_one)
            except GeocoderTimedOut:
                # Just try again
                geocoded = attempt_geocode(location)

            if geocoded is not None:
                self.latitude = geocoded.latitude
                self.longitude = geocoded.longitude
                self.geocoded_to = location
                print self.latitude, self.longitude,
                print bcolors.OKBLUE + '← success' + bcolors.ENDC
                return True # Success

            print bcolors.FAIL + '← fail' + bcolors.ENDC
            return None # No result, but there are more options to try

        # Main loop
        if self.location is None:
            return False
        geolocator = Nominatim(country_bias=bias,timeout=timeout)
        location = self.location
        self.already_attempted = set([])
        while True:

            attempts = set([strip_nonalpha_at_end(location)])

            # Very often helps to add "New Zealand" even though a country bias
            # is already being used
            if 'Antarctica' not in location and 'New Zealand' not in location:
                loc = strip_nonalpha_at_end(location)
                loc += ', New Zealand'
                attempts.add(loc)

            # Simply try the location description, with and without NZ at end
            for loc in attempts:
                gc = attempt_geocode(location)
                if gc is not None:
                    return gc

            # Try without "North Island" or "South Island"
            attempts_copy = attempts.copy()
            for loc in attempts_copy:
                if 'North Island' in loc.title() or 'South Island' in loc.title():
                    for rep in ['North Island','South Island']:
                        loc = loc.replace(rep+', ','')
                        loc = loc.replace(rep,'')
                    loc = strip_nonalpha_at_end(loc)
                    attempts.add(loc)
                    gc = attempt_geocode(loc)
                    if gc is not None:
                        return gc

            # Try with some common substitutions or known errors:
            attempts_copy = attempts.copy()
            for loc in substitutions_for_known_issues(attempts_copy):
                loc = strip_nonalpha_at_end(loc)
                attempts.add(loc)
                gc = attempt_geocode(loc)
                if gc is not None:
                    return gc

            # Try again without non-title-case words, and without one-letter words
            attempts_copy = attempts.copy()
            non_title_case = ' '.join([s for s in location.split(' ') if s.istitle()])
            shortwords = re.compile(r'\W*\b\w{1}\b')
            non_title_case = shortwords.sub('', non_title_case)
            non_title_case = strip_nonalpha_at_end(non_title_case)
            attempts.add(non_title_case)
            gc = attempt_geocode(non_title_case)
            if gc is not None:
                return gc

            self.geocode_attempts += 1

            # Remove the first word of the location for next attempt
            location = ' '.join(location.split(' ')[1:])

            # While loop repeats

def get_all_sightings_as_list_of_UFOSighting_objects(link, geocode=True):
    '''
    Returns a list of UFOSighting objects, scraped from one link to a page of
    sighting reports.

    <link> is a URL (string) that leads to a page of sighting reports on
    UFOCUS NZ's website. Must be in HTML format (<a href="the/url/path">)

    <geocode> defaults to false as it isn't compulsory and takes ages to compute
    (it needs to query a REST API).
    '''

    sightings = []

    year_of_sightings = BeautifulSoup(urlopen(link))

    for table in year_of_sightings.findAll('table', {'cellpadding': '3'}):
        source = link
        date = find_next_td_of_sighting_property(table, 'Date')
        time = find_next_td_of_sighting_property(table, 'Time')
        location = find_next_td_of_sighting_property(table, 'Location')
        features = find_next_td_of_sighting_property(table, 'Features/characteristics')
        description = find_next_td_of_sighting_property(table, 'Description')

        ufo = UFOSighting(source, date, time, location, features, description)

        if not ufo.isValid():
            # Ignore UFO sightings that have been misidentified
            # (Emtpy HTML tables)
            continue

        if geocode:
            if not ufo.geocode():
                # Ignore UFO sightings that cannot be goecoded
                continue

        sightings.append(ufo)

    return sightings

def export_ufos_to_csv(list_of_UFOSighting_objects):

    # Convert UFO objects to tuples
    all_sightings_as_tuples = [ufo.__tuple__() for ufo in list_of_UFOSighting_objects]

    # Create a pandas DataFrame from the list of tuples
    ufos_df = pd.DataFrame(all_sightings_as_tuples, columns=['Date','Time','Location','Geocoded As','Geocode Attempts','Latitude','Longitude','Features','Description'])

    # Export the pandas DF to CSV
    ufos_df.to_csv(os.path.join(os.path.dirname(__file__),'ufos_data.csv'), index=False, encoding='utf-8')

    return None

def main():

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
    years = sorted(set(filter(lambda x: valid(x), [li for li in home_page.findAll(href=True)])))
    # print years
    # print years[0]
    # print type(years[0])
    # There are some other links scattered around the website that have reports in the same format
    additional_links = ['http://www.ufocusnz.org.nz/content/Police/101.aspx',
                        'http://www.ufocusnz.org.nz/content/Selection-of-Historic-Sighting-Reports/109.aspx',
                        'http://www.ufocusnz.org.nz/content/1965---Unidentified-Submerged-Object-%28USO%29-spotted-by-DC-3-Pilot/82.aspx',
                        'http://www.ufocusnz.org.nz/content/1968---Yellow-Disc-Descends-into-Island-Bay,-Wellington/104.aspx',
                        'http://www.ufocusnz.org.nz/content/1974---Large-Object-Emerges-from-Sea-off-Aranga-Beach,-Northland/105.aspx',
                        'http://www.ufocusnz.org.nz/content/1957-1968---Silver-Bullet-Bursts-Through-Antarctic-Ice/106.aspx']
    additional_links = [BeautifulSoup(str('<a href="{}">Link</a>'.format(li))).findAll(href=True)[0] for li in additional_links]
    # TODO see here for more, although they conform less to the expected structure
    # http://www.ufocusnz.org.nz/content/Aviation/80.aspx

    #years += additional_links
    years = [years[-1]] + additional_links

    # Flatten lists of UFOs for each year
    all_sightings = reduce(lambda x,y: x+y, [get_all_sightings_as_list_of_UFOSighting_objects(year['href'],geocode=True) for year in years])

    export_ufos_to_csv(all_sightings)

if __name__ == '__main__':
    main()
    exit(0)
