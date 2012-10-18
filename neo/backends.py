from django.contrib.auth.models import User

from foundry.backends import MultiBackend

from neo.models import NeoProfile
from neo.api import authenticate as authenticate_neo


class NeoBackend(MultiBackend):
    
    def authenticate(self, username=None, password=None):
        obj = None

        for klass, fieldnames in self._authentication_chain:
            for fieldname in fieldnames:
                try:
                    obj = klass.objects.get(**{fieldname:username})
                except klass.DoesNotExist:
                    pass
                else:
                    break
            if obj is not None:
                break
        
        if obj is None:
            return None

        # Obj is an instance of either user or a subclass of user, or else a
        # profile. 
        if isinstance(obj, User):
            user = obj
        else:
            user = obj.user

        # Authenticate via Neo instead of Django
        consumer_id = authenticate_neo(user.username, password)
        if consumer_id:
            assert NeoProfile.objects.get(consumer_id=
                consumer_id).user.id == user.id
            return user
            
        return None
