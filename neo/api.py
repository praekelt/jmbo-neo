import base64
import re
import requests
from requests.auth import HTTPBasicAuth
from datetime import date
from StringIO import StringIO
import copy

from django.conf import settings

from neo.xml import parseString, GDSParseError


# get Neo config from Django settings module or use test defaults
CONFIG = getattr(settings, 'NEO')
# the base url for Neo services
BASE_URL = '/'.join((CONFIG['URL'], CONFIG['APP_ID'], CONFIG['VERSION_ID']))
# make the request module catch all exceptions
requests.defaults.safe_mode = True
# use basic http authentication
HEADERS = {'content-type': 'application/xml'}
if CONFIG.get('USE_MCAL', False):
    HEADERS['Proxy-Authorization'] = 'Basic %s' % base64.b64encode(':'.join((CONFIG['APP_ID'], CONFIG['PASSWORD'])))
# keyword args used in all requests
r_kwargs = {
    'verify': CONFIG.get('VERIFY_CERT', True),
    'headers': HEADERS,
}

# the Neo exception that should be raised if a Neo communication fails
class NeoError(Exception):
    pass


# authenticates using either username/password or a remember me token
def authenticate(username=None, password=None, token=None, promo_code=None, acq_src=None):
    params = {'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']}
    if not token:
        params['loginname'] = username
        params['password'] = password
    else:
        params['authtoken'] = token
    if acq_src:
        params['acquisitionsource'] = acq_src
        
    response = requests.get("%s/consumers/useraccount" % (BASE_URL, ), \
        params=params, **r_kwargs)
    if response.status_code == 200:
        return response.content  # response body contains consumer_id
    elif response.status_code == 400:  # bad request
        raise NeoError("In authenticate: %s %s" % (response.status_code, response.content))
    return None


# logs the consumer out on Neo server
def logout(consumer_id, promo_code=None, acq_src=None):
    params = {'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']}
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s/useraccount/notifylogout" % (BASE_URL, consumer_id),
        params=params, **r_kwargs)
    if response.status_code != 200:
        raise NeoError("In logout: %s %s" % (response.status_code, response.content))


# stores a remember me token on Neo server
def remember_me(consumer_id, token):
    response = requests.put("%s/consumers/%s/useraccount" % (BASE_URL, consumer_id),
        params={'authtoken': token}, **r_kwargs)
    if response.status_code != 200:
        raise NeoError("In remember_me: %s %s" % (response.status_code, response.content))


# creates a consumer and returns the consumer id and validation uri
def create_consumer(consumer):
    data_stream = StringIO()
    # write the consumer data in xml to a string stream
    consumer.export(data_stream, 0)
    response = requests.post("%s/consumers" % (BASE_URL, ), \
        data=data_stream.getvalue(), **r_kwargs)
    data_stream.close()
    if response.status_code == 201:
        # parse the consumer_id in location header
        uri = response.headers["Location"]
        match = re.search(r"/consumers/(?P<id>\d+)/", uri)
        if match:
            return match.group('id'), uri
    else:
        raise NeoError("In create_consumer: %s %s" % (response.status_code, response.content))


# activates the newly created consumer account, optionally using a validation uri
def complete_registration(consumer_id, uri=None):
    if not uri:
	new_r_kwargs = copy.deepcopy(r_kwargs)
        del new_r_kwargs['headers']['content-type']
        new_r_kwargs['headers']['content-length'] = '0'
        response = requests.post("%s/consumers/%s/registration" % (BASE_URL, consumer_id), \
            **new_r_kwargs)
    else:
        response = requests.get(uri)
    if response.status_code != 200:
        raise NeoError("In complete_registration: %s %s" % (response.status_code, response.content))


# retrieves a list of consumers' identified by email/mobile id and DOB
# returns a list of dicts like [{'ConsumerID': val, 'LoginName': val, 'ApplicationName': val}, ...]
def get_consumers(email_id, dob):
    dob_str = dob.strftime("%Y%m%d")
    response = requests.get("%s/consumers/" % (BASE_URL, ),
        params = {'dateofbirth': dob_str, 'emailid': email_id}, **r_kwargs)
    if response.status_code == 200:
        try:
            consumers = parseString(response.content).Consumer
            return [o.__dict__ for o in consumers]
        except GDSParseError:
            pass
    
    raise NeoError("In get_consumers: %s %s" % (response.status_code, response.content))


# links a consumer account from another app with this app
def link_consumer(consumer_id, username, password, promo_code=None, acq_src=None):
    if CONFIG.get('USE_MCAL', False):
        raise NotImplementedError("Consumer requests not supported via MCAL")
    params = {
        'loginname': username,
        'password': password,
        'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']
    }
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s/registration/" % (BASE_URL, consumer_id), \
        params=params, **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass

    raise NeoError("In link_consumer: %s %s" % (response.status_code, response.content))


# get a consumer object containing all the consumer data
def get_consumer(consumer_id):
    if CONFIG.get('USE_MCAL', False):
        raise NotImplementedError("Consumer requests not supported via MCAL")
    response = requests.get("%s/consumers/%s/all" % (BASE_URL, consumer_id), \
        **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass
    
    raise NeoError("In get_consumer: %s %s" % (response.status_code, response.content))


# get a consumer's profile
def get_consumer_profile(consumer_id):
    if CONFIG.get('USE_MCAL', False):
        raise NotImplementedError("Consumer requests not supported via MCAL")
    response = requests.get("%s/consumers/%s/profile" % (BASE_URL, consumer_id), \
        **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass
    
    raise NeoError("In get_consumer_profile: %s %s" % (response.status_code, response.content))


# get a consumer's preferences
# specify category_id to get preferences for a category, otherwise all preferences are returned
def get_consumer_preferences(consumer_id, category_id=None):
    uri = "%s/consumers/%s/preferences" % (BASE_URL, consumer_id)
    if category_id:
        uri += "/category/%s" % category_id
    response = requests.get(uri, **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass

    raise NeoError("In get_consumer_preferences: %s %s" % (response.status_code, response.content))


# update a consumer's data on the Neo server
def update_consumer(consumer_id, consumer):
    if CONFIG.get('USE_MCAL', False):
        raise NotImplementedError("Consumer requests not supported via MCAL")
    data_stream = StringIO()
    # write the consumer data in xml to a string stream
    consumer.export(data_stream, 0)
    response = requests.put("%s/consumers/%s" % (BASE_URL, consumer_id),
        data=data_stream.getvalue(), **r_kwargs)
    data_stream.close()
    if response.status_code != 200:
        raise NeoError("In update_consumer: %s %s" % (response.status_code, response.content))


# create consumer preferences
# specify category_id to update preferences for a category, otherwise all preferences are updated
def update_consumer_preferences(consumer_id, preferences, category_id=None, create=False):
    data_stream = StringIO()
    # write the consumer data in xml to a string stream
    preferences.export(data_stream, 0)
    uri = "%s/consumers/%s/preferences" % (BASE_URL, consumer_id)
    if category_id:
        uri += "/category/%s" % category_id
    if create:
        response = requests.post(uri, data=data_stream.getvalue(), **r_kwargs)
    else:
        response = requests.put(uri, data=data_stream.getvalue(), **r_kwargs)
    data_stream.close()
    if response.status_code != 200:
        raise NeoError("In update_consumer_preferences: %s %s" % (response.status_code, response.content))


# deletes the consumer account
def remove_consumer(consumer_id):
    raise NotImplementedError()


# gets an ID token to change a forgotten password
def get_forgot_password_token(username):
    params = {
        'loginname': username,
        'temptoken': 0
    }
    response = requests.get("%s/consumers/useraccount" % (BASE_URL, ), \
        params=params, **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass

    raise NeoError("In get_forgot_password_token: %s %s" % (response.status_code, response.content))


# changes user's password, possibly using the token generated by get_forgot_password_token
# returns the consumer_id
def change_password(username, new_password, old_password=None, token=None):
    params = {'loginname': username}
    if old_password:
        params['newpassword'] = new_password
        params['oldpassword'] = old_password
    elif token:
        params['password'] = new_password
        params['temptoken'] = token
    else:
        raise ValueError("Either the old password or the forgot password token needs to be specified.")
    new_r_kwargs = copy.deepcopy(r_kwargs)
    del new_r_kwargs['headers']['content-type']
    new_r_kwargs['headers']['content-length'] = '0'
    response = requests.put("%s/consumers/useraccount" % (BASE_URL, ), \
        params=params, **new_r_kwargs)

    if response.status_code == 200:
        return response.content
    
    raise NeoError("In change_password: %s %s" % (response.status_code, response.content))


# unsubscribe from some brand or communication channel
# the user must be logged in
def unsubscribe(consumer_id, unsubscribe_obj):
    data_stream = StringIO()
    # write the unsubscribe data in xml to a string stream
    unsubscribe_obj.export(data_stream, 0)
    response = requests.put("%s/consumers/%s/preferences/unsubscribe" % (BASE_URL, consumer_id),
        data=data_stream.getvalue(), **r_kwargs)
    data_stream.close()
    if response.status_code != 200:
        raise NeoError("In unsubscribe: %s %s" % (response.status_code, response.content))


# add a promo code to a consumer (from master promo code list)
def add_promo_code(consumer_id, promo_code, acq_src=None):
    if CONFIG.get('USE_MCAL', False):
        raise NotImplementedError("Consumer requests not supported via MCAL")
    params = {'promocode': promo_code}
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s" % (BASE_URL, consumer_id), \
        params=params, **r_kwargs)
    if response.status_code != 200:
        raise NeoError("In add_promo_code: %s %s" % (response.status_code, response.content))


# check if the user is of allowable age
def do_age_check(dob, country_code, gateway_id, language_code=None):
    dob_str = dob.strftime("%Y%m%d")
    params = {
        'dateofbirth': dob_str,
        'countrycode': country_code,
        'gatewayid': gateway_id
    }
    if language_code:
        params['language_code'] = language_code
    response = requests.get("%s/consumers/affirmage" % (BASE_URL, ), \
        params=params, **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass
        
    raise NeoError("In do_age_check: %s %s" % (response.status_code, response.content))


# get country details
def get_country(country_code=None, ip_address=None):
    if country_code:
        params = {'countrycode': country_code}
    elif ip_address:
        params = {'ipaddress': ip_address}
    else:
        raise ValueError("Either the country code or ip address needs to be specified.")
    response = requests.get("%s/country/" % (BASE_URL, ), \
        params=params, **r_kwargs)
    if response.status_code == 200:
        try:
            return parseString(response.content)
        except GDSParseError:
            pass

    raise NeoError("In get_country: %s %s" % (response.status_code, response.content))

