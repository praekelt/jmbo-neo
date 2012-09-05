jmbo-neo
========

Provides integration with Neo Web Services

This module used generateDS.py (http://cutter.rexx.com/~dkuhlman/generateDS.html) to generate Python classes from Neo XML schemas.

Requirements
------------
- libxml2-dev
- libxslt-dev
- python-lxml

Settings
--------
The following settings must be added to settings.py:
::
    NEO = {
        'HOST': '209.207.228.37',
        'PORT': '8180',
        'APP_ID': '1',
        'VERSION_ID': '1.3',
        'PROMO_CODE': 'testPromo',  # if there is a single promo code for the website
        'BRAND_ID': 35,  # if there is a single brand for the website
        'USER': 'user',  # http basic auth user
        'PASSWORD': 'password',  # http basic auth password
    }