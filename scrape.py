#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Handy: https://www.airpair.com/python/posts/using-python-and-qgis-for-geospatial-visualization

import dateutil.parser
from urllib import urlopen
import re
import string

from bs4 import BeautifulSoup
import pandas as pd
from geopy.geocoders import Nominatim

# Inspect sightings page
base_url = "http://www.ufocusnz.org.nz/content/Sightings/24.aspx"
source = BeautifulSoup(urlopen(base_url))

# Define what an interesting hyperlink looks like
def valid(tag):
    # <tag> = an html tag that has an href
    return 'New-Zealand-UFO-Sightings-' in tag['href']

# Get list of links, one for each year
years = sorted(set(filter(lambda x: valid(x), [li for li in source.findAll(href=True)])))

def handle_special_date_exception(date_string, exception):
    # There are several special cases
    exceptions = {'Monday 17 or Tuesday 18 May 2010': '17 May 2010',
    'Sunday 26 Sept 2010': '26 September 2010',
    'late October 2010': '27 October 2010',
    'first week of November': '1 November 2010',
    'between 1-8 June 2013': '1 June 2013',
    'week of 12-14 May 2014': '12 May 2014',
    '21 Octover 2014': '21 October 2014',
    'early May 2015': '3 May 2015'}
    if date_string.strip() in exceptions.keys():
        return exceptions[date_string.strip()]
    else:
        err = 'dateutil could not parse "{}"'.format(date_string)
        print '\n{}\n'.format(err)
        raise exception(err)

def parse_date(date_string):
    if date_string is not None:
        date_string = filter(lambda x: x in string.printable, date_string)
        date_string = date_string.replace(' NEW','').strip()
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
    pattern_re = re.compile(pattern.format(sighting_property))
    results = soup.find(to_find, text=pattern_re)
    if results is None:

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

        # Sometimes the html was mangled with <br> tags
        if '<br/>' not in pattern:
            if soup.find('br'):
                text = filter(None,soup.get_text().strip().split("\n"))
                if pattern.format(sighting_property) not in text:
                    return None # Simply doesn't exist
                print ''.join(text[text.index('Description')+1:])
                exit(0)
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

    # Some final encoding issues
    if isinstance(r,basestring):
        r = r.encode('utf8')
    else:
        r = unicode(r).encode('utf8')

    return r

class UFOSighting(object):
    def __init__(self, date, time, location, features, descruption):
        self.date = parse_date(date)
        self.time = time
        self.location = location
        self.features = features
        self.description = description
        # These can be updated by calling geocode(); but don't do that in __init__
        # as nominatim needs to qeury a REST API
        self.latitude = None
        self.longitude = None

    def __str__(self):
        text = '<0> UFOSighting <0>'
        for k, v in self.__dict__.items():
            text += '\n{k}: {v}'.format(k=k.title(),v=v)
        text += '\n\nCopyright UFOCUS NZ\nUsed without permission'
        return text

    def __tuple__(self):
        return (self.date, self.time, self.location, self.features, self.description, self.latitude, self.longitude)

    def isValid(self):
        for prop in self.__tuple__():
            if prop is not None:
                return True
        return False

    def geocode(self,bias='New Zealand',timeout=4,exactly_one=True):
        '''
        Updates self.latitude and self.longitude if a geocode is successsful;
        otherwise leaves them as the default (None_.
        Uses Nominatim.
        Returns False if the location could not be geocoded, returns True when
        the geocode is sucessful.
        '''
        if self.location is  None:
            return False
        geolocator = Nominatim(country_bias=bias,timeout=timeout)
        location = self.location.strip()
        while True:
            geocoded = geolocator.geocode(location,exactly_one=exactly_one)
            if geocoded is not None:
                self.latitude = geocoded.latitude
                self.longitude = geocoded.longitude
                return True # Success
            location = ', '.join(location.split(', ')[1:])
            if location == '':
                self.latitude = None
                self.longitude = None
                return False # Failure

sightings = []

for year in years:

    year = BeautifulSoup(urlopen(year['href']))

    for table in year.findAll('table', {'cellpadding': '3'}):
        date = find_next_td_of_sighting_property(table, 'Date')
        time = find_next_td_of_sighting_property(table, 'Time')
        location = find_next_td_of_sighting_property(table, 'Location')
        features = find_next_td_of_sighting_property(table, 'Features/characteristics')
        description = find_next_td_of_sighting_property(table, 'Description')

        ufo = UFOSighting(date, time, location, features, description)

        if not ufo.isValid():
            # Ignore UFO sightings that have been misidentified
            # (Emtpy HTML tables)
            continue
        if not ufo.geocode():
            # Ignore UFO sightings that cannot be goecoded
            continue

        print ufo.features
        sightings.append(ufo.__tuple__())

# Create a pandas DataFrame with the list of tuples
ufos_df = pd.DataFrame(sightings, columns=['Date','Time','Location','Features','Description','Latitude','Longitude'])

# Export to CSV
ufos_df.to_csv('ufos_data.csv',index=False, encoding='utf-8')
