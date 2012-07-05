from foundry.backends import MultiBackend

from neo.models import NeoProfile
from neo.api import authenticate as authenticate_neo


class NeoBackend(MultiBackend):
    
    def authenticate(self, username=None, password=None):
        consumer_id = authenticate_neo(username, password)
        if consumer_id:
            try:
                return NeoProfile.objects.get(consumer_id=consumer_id).user
            except NeoProfile.DoesNotExist:
                pass
            
        return None
