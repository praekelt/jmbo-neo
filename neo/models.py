from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models import signals
from django.dispatch import receiver
from django.core.cache import cache

from foundry.models import Member, Country

from neo import api
from neo.utils import ConsumerWrapper
from neo.constants import modify_flag


class NeoProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    # the Neo consumer id used in API requests
    consumer_id = models.PositiveIntegerField(primary_key=True)

'''
The member attributes that are stored on Neo and in memcached
NB. These attributes must be required during registration for any Neo app
'''
NEO_ATTR = frozenset(('username', 'password', 'first_name', \
    'last_name', 'dob', 'email', 'mobile_number', \
    'receive_sms', 'receive_email', 'country'))
JMBO_REQUIRED_FIELDS = frozenset(('username', 'password', \
    'mobile_number', 'receive_sms', 'receive_email'))

                    
@receiver(user_logged_out)
def notify_logout(sender, **kwargs):
    try:
        neo_profile = NeoProfile.objects.get(user=kwargs['user'])
        api.logout(neo_profile.consumer_id)
    except NeoProfile.DoesNotExist:
        pass # figure out something to do here


@receiver(signals.pre_save, sender=Member)
def stash_neo_fields(sender, **kwargs):
    cleared_fields = {}
    member = kwargs['instance']
    '''
    Stash the neo fields that aren't required and clear
    them on the instance so that they aren't saved to db
    '''
    for key in NEO_ATTR.difference(JMBO_REQUIRED_FIELDS):
        cleared_fields[key] = getattr(member, key)
        '''
        If field can be null, set to None. Otherwise assign
        a default value. If a default value has not been
        specified, assign the default of the python type
        '''
        field = Member._meta.get_field_by_name(key)[0]
        if field.null:
            setattr(member, key, None)
        elif field.default != models.fields.NOT_PROVIDED:
            setattr(member, key, field.default)
        else:
            setattr(member, key, type(cleared_fields[key])())
    member.cleared_fields = cleared_fields


@receiver(signals.post_save, sender=Member)
def create_consumer(sender, **kwargs):
    member = kwargs['instance']
    '''
    Reassign the stashed neo fields and delete
    the stash
    '''
    for key, val in member.cleared_fields.iteritems():
        setattr(member, key, val)
    del member.cleared_fields

    cache_key = 'neo_consumer_%s' % member.pk
    if kwargs['created']:
        # create consumer
        wrapper = ConsumerWrapper()
        for a in NEO_ATTR:
            getattr(wrapper, "set_%s" % a)(getattr(member, a))
        try:
            consumer_id, uri = api.create_consumer(wrapper.consumer)
            neo_profile = NeoProfile.objects.get_or_create(user=member, consumer_id=consumer_id)
        except api.NeoError:
            pass

    else:
        # update changed attributes
        old_member = cache.get(cache_key, None)
        wrapper = ConsumerWrapper()
        if old_member is not None:  # it should never be None
            for k in NEO_ATTR:
                # check where cached version and current version of member differ
                current = getattr(member, k, None)
                old = old_member.get(k, None)
                if current != old:
                    # update attribute on Neo
                    if old is None:
                        getattr(wrapper, "set_%s" % k)(current, mod_flag=modify_flag['INSERT'])
                    elif current is None:
                        getattr(wrapper, "set_%s" % k)(old, mod_flag=modify_flag['DELETE'])
                    else:
                        getattr(wrapper, "set_%s" % k)(current, mod_flag=modify_flag['UPDATE'])
        try:
            consumer_id = NeoProfile.objects.get(user=member)
            api.update_consumer(consumer_id, wrapper.consumer)
        except api.NeoError:
            pass

    # cache this member after it is saved (thus created/updated successfully)
    cache.set(cache_key, dict((k, getattr(member, k, None)) \
        for k in NEO_ATTR), 1200)


@receiver(signals.post_init, sender=Member)
def load_consumer(sender, *args, **kwargs):
    instance = kwargs['instance']
    # if the object being instantiated has a pk, i.e. has been saved to the db
    if instance.id:
        pk = instance.id
        cache_key = 'neo_consumer_%s' % pk
        member = cache.get(cache_key, None)
        if member is None:
            consumer_id = NeoProfile.objects.get(user=pk).consumer_id
            # retrieve consumer from Neo
            consumer = api.get_consumer(consumer_id)
            wrapper = ConsumerWrapper(consumer=consumer)
            member=dict((k, getattr(wrapper, k)) for k in NEO_ATTR)
            # cache the neo member dictionary
            cache.set(cache_key, member, 1200)

        # update instance with Neo attributes
        for key, val in member.iteritems():
            # don't override the hashed django password
            if key != 'password':
                setattr(instance, key, val)