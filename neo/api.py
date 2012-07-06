import re
import requests

from django.conf import settings
from django.core import serializers


# get Neo config from Django settings module or use test defaults
CONFIG = getattr(settings, 'NEO', {
    'HOST': '209.207.228.37',
    'PORT': '8180',
    'APP_ID': '1',
    'VERSION_ID': '1.3',
    'PROMO_CODE': 'testPromo',
})
# the base url for Neo services
BASE_URL = "http://%s:%s/neowebservices/%s/%s" % (
    CONFIG['HOST'],
    CONFIG['PORT'],
    CONFIG['APP_ID'],
    CONFIG['VERSION_ID']
)
# make the request module catch all exceptions
requests.defaults.safe_mode = True
    

# authenticates using either username/password or a remember me token
def authenticate(username=None, password=None, token=None, acq_src=None):
    params = {'promocode': CONFIG['PROMO_CODE']}
    if not token:
        params['loginname'] = username
        params['password'] = password
    else:
        params['authtoken'] = token
    if acq_src:
        params['acquisitionsource'] = acq_src
        
    response = requests.get("/consumers/useraccount", params=params)
    if response.status_code == 200:
        return response.text  # response body contains consumer_id
        
    return None


# logs the consumer out on Neo server
def logout(consumer_id, acq_src=None):
    params = {'promocode': CONFIG['PROMO_CODE']}
    if acq_src:
        params['acquisitionsource'] = acq_src
    response = requests.put("/consumers/%s/useraccount/notifylogout" % consumer_id,
        params=params)
    return response.status_code == 200


# stores a remember me token on Neo server
def remember_me(consumer_id, token):
    response = requests.put("/consumers/%s/useraccount" % consumer_id,
        params={'authtoken': token})
    return response.status_code == 200


# creates a consumer and returns the consumer id and validation uri
def create_consumer(user):
    data = serializers.serialize("xml", user)
    response = requests.post("/consumers", data=data)
    if response.status_code == 201:
        # parse the consumer_id in location header
        uri = response.headers["Location"]
        match = re.search(r"/consumers/(?P<id>\d+)/", uri)
        if match:
            return match.group('id'), uri 
    
    return None


# activates the newly created consumer account, optionally using a validation uri
def complete_registration(consumer_id, uri=None):
    if not uri:
        response = requests.post("/consumers/%s/registration" % consumer_id)
    else
        response = requests.get(uri)
    return response.status_code == 200


# deletes the consumer account
def remove_consumer(consumer_id):
    
    