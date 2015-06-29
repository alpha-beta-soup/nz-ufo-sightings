from nose.tools import *
from PythonUFOCUSNZ import scrape
import datetime

def setup_module():
    pass

def teardown_module():
    pass

def test_sanity_check_first_2010_sighting():
    # Tests whether the UFOSighting object representing the first report of 2010
    # meets expectations
    # Not a robust check of all scraping, just a simple check that the object is
    # not broken
    source = 'http://www.ufocusnz.org.nz/content/New-Zealand-UFO-Sightings-2010/37.aspx'
    sightings_in_2010 = scrape.get_all_sightings_as_list_of_UFOSighting_objects(source, geocode=False)

    assert len(sightings_in_2010) > 0

    first_sighting = sightings_in_2010[0]

    assert first_sighting.isValid()
    assert first_sighting.geocode()
    assert first_sighting.date == datetime.datetime(2010,12,31)
    assert first_sighting.location.title() == "Tauranga, North Island"
    assert first_sighting.features.lower() == "red light travelling at high speed"
    assert "Three witnesses observed a red light pass over Mount Maunganui" in first_sighting.description
