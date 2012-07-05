import urllib2, urllib
from urllib2 import URLError, HTTPError, Request

from django.conf import settings


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

def _send_request(url, data=None):
    try:
        response = urllib2.urlopen(BASE_URL + url, data)
    except HTTPError, e:
        return e.code, None
    except URLError:
        pass
    else:
        return response.getcode(), response.read()   
    
    return None
    
    
def authenticate(username, password):
     code, consumer_id = _send_request("/consumers/useraccount?%s" \
        % urllib.urlencode({'loginname': username, 'password': password}))
     if code == 200:
         return consumer_id
         
     return None


def logout(consumer_id):
    _send_request("/consumers/%s/useraccount/notifylogout" % consumer_id)
