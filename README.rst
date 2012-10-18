jmbo-neo
========

jmbo-neo provides integration with Neo Web Services for jmbo and jmbo-foundry. It syncs jmbo-foundry's Member objects with consumers
in the Neo data hubs. Syncing refers to the creation, modification and deactivation of Neo consumers as Member objects are created, modified
and deactivated.

Authentication-related actions are also performed via Neo Web Services. These include logging in and out and changing passwords. jmbo-neo also
supports a number of other Neo API calls. These, in addition to the above mentioned, can be invoked as necessary in other jmbo apps.

Requirements
------------

System libraries
****************
- libxml2-dev
- libxslt-dev

Python packages
***************
- python-lxml
- requests

*jmbo-neo uses generateDS.py (http://cutter.rexx.com/~dkuhlman/generateDS.html) to generate Python classes from Neo XML schemas.*

Usage
-----

`neo.api` contains functions for all the supported Neo API calls. Consumer calls require either a consumer ID or consumer object (or both).
If a consumer has been created for a particular Member, a corresponding NeoProfile object will be stored in the database. So to obtain the
consumer ID, use `neo.models.NeoProfile(user=member.id).consumer_id`.

A consumer object is an instance of `neo.xml.Consumer`. Consumer should not be instantiated directly. Internally, jmbo-neo uses `neo.xml.parseString(response.content)`
to create a consumer object from the XML return by Neo Web Services. This object will be returned when calling, for instance, `neo.api.get_consumer`.
To access this consumer object, you should use the wrapper class `neo.utils.ConsumerWrapper`. It has all the necessary getter and setter methods to correctly
manipulate the consumer object, ensuring the resulting XML is valid.

**When using jmbo-neo, all non-required Member fields will be null, or set to their default values. Queries on Member objects
will return incorrect results.**

Settings
********
The following settings must be added to settings.py:
::
    NEO = {
        'URL': 'neowebservices.com/service/'
        'APP_ID': '1',
        'VERSION_ID': '1.3',
        'PROMO_CODE': 'testPromo',  # if there is a single promo code for the website
        'BRAND_ID': 35,  # if there is a single brand for the website
        'PASSWORD': 'password',  # http basic auth password
    }

    AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend',)