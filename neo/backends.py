from django.contrib.auth.models import User

from foundry.backends import MultiBackend
from foundry.models import Member

from neo.models import NeoProfile, NEO_ATTR, ADDRESS_FIELDS
from neo import api
from neo.api import authenticate as authenticate_neo
from neo.utils import ConsumerWrapper


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
            # try to log in via Neo
            consumer_id = authenticate_neo(username, password)
            if consumer_id:
                # create the member using data from Neo
                consumer = api.get_consumer(consumer_id, username, password)
                wrapper = ConsumerWrapper(consumer=consumer)
                attrs = dict((k, getattr(wrapper, k)) for k in NEO_ATTR)
                attrs.update(wrapper.address)
                member = Member(**attrs)
                # don't want save method to attempt to create a consumer
                member.need_to_clean_member = False
                member.consumer_id = consumer_id
                member.save()
                return member
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
