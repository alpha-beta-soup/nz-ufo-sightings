try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

# docs.python.org/distutils/setupscript.html
config = {
    'description': 'A Python scraper for UFOCUS NZ UFO sightings. Parses with BeautifulSoup4, tentatively uses pandas, and geocodes pretty poorly with geopy (Neonatim). If you use this tool to extract the information into a friendly format, bear in mind that you must not redistribute that content without the express permission of UFOCUS NZ.',
    'author': 'Richard Law',
    'url': 'https://github.com/alpha-beta-soup/nz-ufo-sightings',
    'download_url': 'https://github.com/alpha-beta-soup/nz-ufo-sightings/archive/master.zip',
    'author_email': 'richard.m.law@gmail.com',
    'version': '0.1',
    'install_requires': ['nose','BeautifulSoup','pandas','geopy'],
    'packages': ['PythonUFOCUSNZ'],
    'scripts': [],
    'name': 'PythonUFOCUSNZ'
}

setup(**config)
