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
})
# the base url for Neo services
BASE_URL = "http://%s:%s/neowebservices/%s/%s" % (
    CONFIG['HOST'],
    CONFIG['PORT'],
    CONFIG['APP_ID'],
    CONFIG['VERSION_ID']
)
    
    
def authenticate(username, password):
     response = requests.get("/consumers/useraccount",
        params={'loginname': username, 'password': password})
     if response.status_code == 200:
         return response.text  # response body contains consumer_id
         
     return None


def logout(consumer_id):
    response = requests.get("/consumers/%s/useraccount/notifylogout" % consumer_id)
    return response.status_code == 200


# creates a consumer and returns its id and account activation uri
def create_consumer(user):
    data = serializers.serialize("xml", user)
    response = requests.post("/consumers", data=data)
    if response.status_code == 201:
        # parse the consumer_id in location header
        uri = response.headers["Location"]
        match = re.search(r"/consumers/(?P<id>\d+)/", uri)
        if match:
            return match.group('id') 
    
    return None


# activates the consumer account using the uri provided by create_consumer
def complete_registration(consumer_id):
    response = requests.post("/consumers/%s/registration" % consumer_id)
    return response.status_code == 200


def remove_consumer(consumer_id):
    
    