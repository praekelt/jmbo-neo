from django.contrib.auth.hashers import make_password

from foundry.backends import MultiBackend

from neo.models import NeoProfile
from neo.api import authenticate as authenticate_neo, \
    NeoError


class NeoBackend(MultiBackend):
    
    def authenticate(self, username=None, password=None):
        neo_pw = make_password(password).split('$')[-1]
        consumer_id = authenticate_neo(username, neo_pw)
        if consumer_id:
            try:
                return NeoProfile.objects.get(consumer_id=consumer_id).user
            except NeoProfile.DoesNotExist:
                pass
            
        return None
