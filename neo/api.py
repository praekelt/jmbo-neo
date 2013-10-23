import base64
import logging
import inspect
import re
import requests
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


logger = logging.getLogger(__name__)


def log_api_call(function_call_tup=None, log_level=logging.INFO, status_code=200,
                 exception=None):
    '''
    Inspect the call stack frame record to get the function name and
    arguments. Log this info (with blanked out password) along with
    the API call's response status code and possibly an exception
    '''
    if not function_call_tup:
        try:
            function_call_tup = inspect.stack()[1]
        except IndexError:
            function_call_tup = (None, ) * 6
    if function_call_tup[0]:
        args = inspect.getargvalues(function_call_tup[0])
        # we don't want passwords in logs
        locals_copy = args.locals.copy()
        if 'password' in locals_copy:
            locals_copy['password'] = '***'
        arg_str = inspect.formatargvalues(*(args[:-1] + (locals_copy, )))
    else:
        arg_str = ''
    kwargs = {}
    if log_level == logging.ERROR:
        kwargs['exc_info'] = exception

    logger.log(log_level, '%(function_name)s%(arg_str)s: %(status_code)s',
               {'function_name': function_call_tup[3],
                'arg_str': arg_str, 'status_code': status_code},
                **kwargs)


def _get_error(response):
    '''
    Determine the appropriate error
    '''
    exception = None
    if response.status_code == 500:
        exception = Exception("Neo Web Services not responding")
    else:
        try:
            neo_resp = parseString(response.content)
            errors = None
            if isinstance(neo_resp, ResponseListType):
                errors = neo_resp.Response
            elif isinstance(neo_resp, ResponseType):
                errors = [neo_resp]
            else:
                exception = Exception(response.content)

            if not exception:
                err_msg_list = []
                for error in errors:
                    if error.ResponseCode == 'INVALID_APPID':
                        exception = exceptions.ImproperlyConfigured(
                            "Neo App ID is invalid."
                        )
                    elif error.ResponseCode == 'INVALID_VERSION':
                        exception = exceptions.ImproperlyConfigured(
                            "Neo API version is invalid."
                        )
                    elif (error.ResponseCode == 'BAD_REQUEST' or
                          response.request.method == 'POST' or
                          response.request.method == 'PUT'):
                        err_msg_list.append(_(error.ResponseMessage))
                    else:
                        exception = Exception(response.content)
                if not exception:
                    exception = exceptions.ValidationError(err_msg_list)
        except GDSParseError:
            exception = Exception(response.content)

    log_api_call(function_call_tup=inspect.stack()[1],
                 log_level=logging.ERROR,
                 exception=exception)
    return exception


def _get_auth_header(username, password, promo_code):
    '''
    Create HTTP Authorization header
    '''
    return 'Basic %s' % base64.b64encode(':'.join((username, password, promo_code)))


def get_kwargs(username=None, password=None, promo_code=None, no_content=False):
    new_r_kwargs = copy.deepcopy(r_kwargs)
    if (username and password) and CONFIG.get('USE_MCAL', False):
        new_r_kwargs['headers']['Authorization'] = _get_auth_header(username, password,
            promo_code if promo_code else CONFIG['PROMO_CODE'])
    if no_content:
        del new_r_kwargs['headers']['content-type']
        new_r_kwargs['headers']['content-length'] = '0'
    return new_r_kwargs


def authenticate(username=None, password=None, token=None, promo_code=None, acq_src=None):
    '''
    Authenticates using either username/password or a remember me token
    '''
    params = {'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']}
    if not token:
        params['loginname'] = username
        params['password'] = password
    else:
        params['authtoken'] = token
    if acq_src:
        params['acquisitionsource'] = acq_src

    response = requests.get("%s/consumers/useraccount/" % (BASE_URL, ),
        params=params, **get_kwargs())
    log_api_call(status_code=response.status_code)
    if response.status_code == 200:
        return response.content  # response body contains consumer_id
    return None


def logout(consumer_id, promo_code=None, acq_src=None):
    '''
    Logs the consumer out on Neo server
    '''
    params = {'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']}
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s/useraccount/notifylogout" % (BASE_URL, consumer_id),
        params=params, **get_kwargs(no_content=True))
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call()


def remember_me(consumer_id, token):
    '''
    Stores a remember me token on Neo server
    '''
    response = requests.put("%s/consumers/%s/useraccount" % (BASE_URL, consumer_id),
        params={'authtoken': token}, **get_kwargs())
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call()


def create_consumer(consumer):
    '''
    Creates a consumer and returns the consumer id and validation uri
    '''
    data_stream = StringIO()
    # write the consumer data in xml to a string stream
    consumer.export(data_stream, 0)
    response = requests.post("%s/consumers" % (BASE_URL, ),
        data=data_stream.getvalue(), **get_kwargs())
    data_stream.close()
    if response.status_code == 201:
        log_api_call(status_code=201)
        # parse the consumer_id in location header
        uri = response.headers["Location"]
        match = re.search(r"/consumers/(?P<id>\d+)/", uri)
        if match:
            return match.group('id'), uri
    else:
        raise _get_error(response)


def complete_registration(consumer_id, uri=None):
    '''
    Activates the newly created consumer account, optionally using a validation uri
    '''
    if not uri:
        response = requests.post("%s/consumers/%s/registration" % (BASE_URL, consumer_id),
            **get_kwargs(no_content=True))
    else:
        response = requests.get(uri)
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call()


def get_consumers(email_id, dob):
    '''
    Retrieves a list of consumers' identified by email/mobile id and DOB
    Returns a list of dicts like
    [{'ConsumerID': val, 'LoginName': val, 'ApplicationName': val}, ...]
    '''
    dob_str = dob.strftime("%Y%m%d")
    response = requests.get("%s/consumers/" % (BASE_URL, ),
        params = {'dateofbirth': dob_str, 'emailid': email_id}, **get_kwargs())
    if response.status_code == 200:
        try:
            consumers = parseString(response.content).Consumer
            log_api_call()
            return [o.__dict__ for o in consumers]
        except GDSParseError:
            pass
    
    raise _get_error(response)


def link_consumer(consumer_id, username, password, promo_code=None, acq_src=None):
    '''
    Links a consumer account from another app with this app
    '''
    #if CONFIG.get('USE_MCAL', False):
    #    raise NotImplementedError("Consumer requests not supported via MCAL")
    params = {
        'loginname': username,
        'password': password,
        'promocode': promo_code if promo_code else CONFIG['PROMO_CODE']
    }
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s/registration/" % (BASE_URL, consumer_id),
        params=params, **get_kwargs())
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)


def get_consumer(consumer_id, username=None, password=None, promo_code=None):
    '''
    Get a consumer object containing all the consumer data
    '''
    response = requests.get("%s/consumers/%s/all" % (BASE_URL, consumer_id),
        **get_kwargs(username=username, password=password, promo_code=promo_code))
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)


def get_consumer_profile(consumer_id, username=None, password=None, promo_code=None):
    '''
    Get a consumer's profile
    '''
    response = requests.get("%s/consumers/%s/profile" % (BASE_URL, consumer_id),
        **get_kwargs(username=username, password=password, promo_code=promo_code))
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)


def get_consumer_preferences(consumer_id, category_id=None,
    username=None, password=None, promo_code=None):
    '''
    Get a consumer's preferences
    Specify category_id to get preferences for a category,
    otherwise all preferences are returned
    '''
    uri = "%s/consumers/%s/preferences" % (BASE_URL, consumer_id)
    if category_id:
        uri += "/category/%s" % category_id
    response = requests.get(uri, **get_kwargs(username=username, password=password, promo_code=promo_code))
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)


def update_consumer(consumer_id, consumer, username=None, password=None, promo_code=None):
    '''
    Update a consumer's data on the Neo server
    '''
    data_stream = StringIO()
    # write the consumer data in xml to a string stream
    consumer.export(data_stream, 0)
    response = requests.put("%s/consumers/%s" % (BASE_URL, consumer_id),
        data=data_stream.getvalue(), **get_kwargs(username=username, password=password, promo_code=promo_code))
    data_stream.close()
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call()


def _update_question_answers(consumer_id, object, category_id=None, create=False,
    username=None, password=None, promo_code=None, root_tag_name=None, uri=None):
    data_stream = StringIO()
    # write the consumer data in xml to a string stream
    if root_tag_name:
        object.export(data_stream, 0, name_=root_tag_name)
    else:
        object.export(data_stream, 0)
    if not uri:
        uri = "%s/consumers/%s/%s" % (BASE_URL, consumer_id,
            root_tag_name.lower() if root_tag_name else object.__name__.lower())
    if category_id:
        uri += "/category/%s" % category_id
    response = getattr(requests, 'post' if create else 'put')(uri, data=data_stream.getvalue(),
        **get_kwargs(username=username, password=password, promo_code=promo_code))
    data_stream.close()
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call(function_call_tup=inspect.stack()[1])


def update_consumer_preferences(consumer_id, preferences, category_id=None, create=False,
    username=None, password=None, promo_code=None):
    '''
    Create consumer preferences
    Specify category_id to update preferences for a category,
    otherwise all preferences are updated
    '''
    _update_question_answers(consumer_id, preferences, category_id, create, username,
        password, promo_code, 'Preferences')


def update_digital_interactions(consumer_id, digital_interactions, category_id=None, create=False,
    username=None, password=None, promo_code=None):
    '''
    Add digital interactions to consumer
    '''
    _update_question_answers(consumer_id, digital_interactions, category_id, create, username,
        password, promo_code, 'DigitalInteractions')


def update_conversion_locations(consumer_id, conversion_locations, category_id=None, create=False,
    username=None, password=None, promo_code=None):
    '''
    Add conversion locations to consumer
    '''
    _update_question_answers(consumer_id, conversion_locations, category_id, create, username,
        password, promo_code, 'ConversionLocations')


def remove_consumer(consumer_id):
    '''
    Deletes the consumer account
    '''
    raise NotImplementedError()


def get_forgot_password_token(username):
    '''
    Gets an ID token to change a forgotten password
    '''
    params = {
        'loginname': username,
        'temptoken': 0
    }
    response = requests.get("%s/consumers/useraccount" % (BASE_URL, ),
        params=params, **get_kwargs())
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)


def change_password(username, new_password, old_password=None, token=None):
    '''
    Changes user's password, possibly using the token
    generated by get_forgot_password_token
    Returns the consumer_id
    '''
    params = {'loginname': username}
    if old_password:
        params['newpassword'] = new_password
        params['oldpassword'] = old_password
    elif token:
        params['password'] = new_password
        params['temptoken'] = token
    else:
        raise ValueError("Either the old password or the forgot password token needs to be specified.")
    response = requests.put("%s/consumers/useraccount" % (BASE_URL, ),
        params=params, **get_kwargs(no_content=True))

    if response.status_code == 200:
        log_api_call()
        return response.content

    raise _get_error(response)


def unsubscribe(consumer_id, unsubscribe_obj):
    '''
    Unsubscribe from some brand or communication channel
    The user must be logged in
    '''
    data_stream = StringIO()
    # write the unsubscribe data in xml to a string stream
    unsubscribe_obj.export(data_stream, 0)
    response = requests.put("%s/consumers/%s/preferences/unsubscribe" % (BASE_URL, consumer_id),
        data=data_stream.getvalue(), **get_kwargs())
    data_stream.close()
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call()


def add_promo_code(consumer_id, promo_code, acq_src=None, username=None, password=None):
    '''
    Add a promo code to a consumer (from master promo code list)
    '''
    params = {'promocode': promo_code}
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("%s/consumers/%s" % (BASE_URL, consumer_id),
        params=params, **get_kwargs(username=username, password=password, no_content=True))
    if response.status_code != 200:
        raise _get_error(response)
    log_api_call()


def do_age_check(dob, country_code, gateway_id, language_code=None):
    '''
    Check if the user is of allowable age
    '''
    dob_str = dob.strftime("%Y%m%d")
    params = {
        'dateofbirth': dob_str,
        'countrycode': country_code,
        'gatewayid': gateway_id
    }
    if language_code:
        params['language_code'] = language_code
    response = requests.get("%s/consumers/affirmage" % (BASE_URL, ),
        params=params, **get_kwargs())
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)


def get_country(country_code=None, ip_address=None):
    '''
    Get country details
    '''
    if country_code:
        params = {'countrycode': country_code}
    elif ip_address:
        params = {'ipaddress': ip_address}
    else:
        raise ValueError("Either the country code or ip address needs to be specified.")
    response = requests.get("%s/country/" % (BASE_URL, ),
        params=params, **get_kwargs())
    if response.status_code == 200:
        try:
            obj_from_xml = parseString(response.content)
            log_api_call()
            return obj_from_xml
        except GDSParseError:
            pass

    raise _get_error(response)
