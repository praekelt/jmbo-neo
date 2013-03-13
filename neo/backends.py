from django.contrib.auth.models import User

from foundry.backends import MultiBackend
from foundry.models import Member
from social_auth.backends.facebook import FacebookBackend

from neo.models import NeoProfile, NEO_ATTR, ADDRESS_FIELDS
from neo import api
from neo.api import authenticate as authenticate_neo
from neo.utils import ConsumerWrapper


class NeoBackendBase(object):
    
    def authenticate(self, username=None, password=None):
        user = super(NeoBackendBase, self).authenticate(username=username, password=password)
        if user is None:
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
                member.raw_password = password
                return member
        else:
            user.raw_password = password
        return user


class NeoMultiBackend(NeoBackendBase, MultiBackend):
    pass
