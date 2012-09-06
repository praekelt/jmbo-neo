from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models import signals
from django.dispatch import receiver
from django.core.cache import cache

from foundry.models import Member, Country

from neo import api
from neo.utils import ConsumerWrapper


class NeoProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    # the Neo consumer id used in API requests
    consumer_id = models.PositiveIntegerField(primary_key=True)


# the member attributes that are stored on Neo and in memcached
NEO_ATTR = ('username', 'password', 'first_name', \
    'last_name', 'dob', 'email', 'mobile_number', \
    'receive_sms', 'receive_email', 'country')

                    
@receiver(user_logged_out)
def notify_logout(sender, **kwargs):
    try:
        neo_profile = NeoProfile.objects.get(user=kwargs['user'])
        api.logout(neo_profile.consumer_id)
    except NeoProfile.DoesNotExist:
        pass # figure out something to do here


@receiver(signals.post_save, sender=Member)
def create_consumer(sender, **kwargs):
    member = kwargs['instance']
    cache_key = 'neo_consumer_%s' % member.pk
    if kwargs['created']:
        # create consumer
        # NB. These attributes must be required during registration for any Neo app
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
                        getattr(wrapper, "set_%s" % k)(current, mod_flag='I')  # insert
                    elif current is None:
                        getattr(wrapper, "set_%s" % k)(old, mod_flag='D')  # delete
                    else:
                        getattr(wrapper, "set_%s" % k)(current, mod_flag='U')  # update
        try:
            consumer_id = NeoProfile.objects.get(user=member)
            api.update_consumer(consumer_id, wrapper.consumer)
        except api.NeoError:
            pass
                    
    # cache this member after it is saved (thus created/updated successfully)
    cache.set(cache_key, dict((k, getattr(member, k, None)) \
        for k in NEO_ATTR), 1200)


'''@receiver(signals.pre_init, sender=Member)
def load_consumer(sender, **kwargs):
    init_args = kwargs['args']
    # if the object being instantiated has a pk, i.e. has been saved to the db
    if len(init_args) > 0 and init_args[0]:
        pk = init_args[0]
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
        
        # update init_args
        i = 0
        for field in Member._meta.fields:
            val = member.get(field.name, None)
            if val is not None:
                init_args[i] = val 
            i += 1
'''           