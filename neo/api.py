import base64
import re
import requests
from datetime import date
from StringIO import StringIO
import copy

from django.conf import settings
from django.core import exceptions
from django.utils.translation import ugettext_lazy as _

from neo.xml import parseString, GDSParseError, ResponseListType, ResponseType


# get Neo config from Django settings module
try:
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
except AttributeError:
    raise exceptions.ImproperlyConfigured("Neo settings are missing.")
except KeyError as e:
    raise exceptions.ImproperlyConfigured("Neo setting %s is missing." % str(e))


# Determine the appropriate error 
def _get_error(response):
    if response.status_code == 500:
        return Exception("Neo Web Services not responding")
    try:
        neo_resp = parseString(response.content)
        errors = None
        if isinstance(neo_resp, ResponseListType):
            errors = neo_resp.Response
        elif isinstance(neo_resp, ResponseType):
            errors = [neo_resp]
        else:
            return Exception(response.content)
        err_msg_list = []
        for error in errors:
            if error.ResponseCode == 'INVALID_APPID':
                return exceptions.ImproperlyConfigured("Neo App ID is invalid.")
            elif error.ResponseCode == 'INVALID_VERSION':
                return exceptions.ImproperlyConfigured("Neo API version is invalid.")
            elif error.ResponseCode == 'BAD_REQUEST' or response.request.method == 'POST' or \
                response.request.method == 'PUT':
                err_msg_list.append(_(error.ResponseMessage))
            else:
                return Exception(response.content)
        return exceptions.ValidationError(err_msg_list)
    except GDSParseError:
        return Exception(response.content)
    

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
        
    response = requests.get("%s/consumers/useraccount/" % (BASE_URL, ), \
        params=params, **r_kwargs)
    if response.status_code == 200:
        return response.content  # response body contains consumer_id
    return None


# logs the consumer out on Neo server
def logout(consumer_id, promo_code=None, acq_src=None):
    params = {'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']}
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s/useraccount/notifylogout" % (BASE_URL, consumer_id),
        params=params, **r_kwargs)
    if response.status_code != 200:
        raise _get_error(response)


# stores a remember me token on Neo server
def remember_me(consumer_id, token):
    response = requests.put("%s/consumers/%s/useraccount" % (BASE_URL, consumer_id),
        params={'authtoken': token}, **r_kwargs)
    if response.status_code != 200:
        raise _get_error(response)


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
        raise _get_error(response)


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
        raise _get_error(response)


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
    
    raise _get_error(response)


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

    raise _get_error(response)


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
    
    raise _get_error(response)


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
    
    raise _get_error(response)


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

    raise _get_error(response)


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
        raise _get_error(response)


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
        raise _get_error(response)


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

    raise _get_error(response)


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
    
    raise _get_error(response)


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
        raise _get_error(response)


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
        raise _get_error(response)


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
        
    raise _get_error(response)


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

    raise _get_error(response)
