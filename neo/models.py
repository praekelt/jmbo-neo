from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.contrib.contenttypes.models import ContentType
from django.db.models import signals, Q
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.conf import settings

from jmbo.models import ModelBase

from foundry.models import Member, Country
from foundry.forms import PasswordResetForm

'''try:
    from competition.models import CompetitionEntry
    COMPETITION_IS_ACTIVE = True
except:
    COMPETITION_IS_ACTIVE = False'''

from neo import api
from neo.utils import ConsumerWrapper
from neo.constants import modify_flag, country_option_id


class NeoProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    # the Neo consumer id used in API requests
    consumer_id = models.PositiveIntegerField(primary_key=True)


'''
A model that associates a Neo promo code with some interactive content.
If a user interacts with this object, the promo code is added to their consumer profile
on Neo. Only supports competitions for now.
'''
'''class NeoPromo(models.Model):
    promo_code = models.CharField(
        max_length=50,
    )
    promo_object = models.ForeignKey(
        ModelBase,
        limit_choices_to=(Q(content_type__model='competition')),
    )


def add_promo_code_to_consumer(sender, **kwargs):
    promo_object = None
    user = None
    sender_id = "%s.%s" % (sender._meta.app_label, sender._meta.module_name)
    if sender_id == 'competition.competitionentry':
        promo_object = kwargs['instance'].competition
        user = kwargs['instance']
    if promo_object and user:    
        try:
            promo_code = NeoPromo.objects.get(promo_object=promo_object).promo_code
            try:
                consumer_id = NeoProfile.objects.get(user=user).consumer_id
                api.add_promo_code(consumer_id, promo_code)
            except NeoProfile.DoesNotExist:
                pass
        except NeoPromo.DoesNotExist:
            pass


if COMPETITION_IS_ACTIVE:
    signals.post_save.connect(add_promo_code_to_consumer, sender=CompetitionEntry)'''


'''
The member attributes that are stored on Neo and in memcached
NB. These attributes must be required during registration for any Neo app
NB. Password is a special case and is handled separately
NB. Address, city and province are also special cases
'''
NEO_ATTR = frozenset(('username', 'first_name', \
    'last_name', 'dob', 'email', 'mobile_number', \
    'receive_sms', 'receive_email', 'country', \
    'gender'))

# These fields are used together to create an address and don't exist as individual neo attributes
ADDRESS_FIELDS = frozenset(('city', 'country', 'province', 'zipcode', 'address'))

# These fields correspond to the available login fields in jmbo-foundry
JMBO_REQUIRED_FIELDS = frozenset(('username', 'mobile_number', 'email'))

USE_AUTH = ('neo.backends.NeoBackend' in getattr(settings, 'AUTHENTICATION_BACKENDS', []))
USE_MCAL = settings.NEO.get('USE_MCAL', False)
                    

def notify_logout(sender, **kwargs):
    try:
        neo_profile = NeoProfile.objects.get(user=kwargs['user'])
        api.logout(neo_profile.consumer_id)
    except NeoProfile.DoesNotExist:
        pass # figure out something to do here
if USE_AUTH:
    user_logged_out.connect(notify_logout)


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
if not USE_MCAL:
    signals.pre_save.connect(stash_neo_fields, sender=Member)


@receiver(signals.post_save, sender=Member)
def create_consumer(sender, **kwargs):
    member = kwargs['instance']
    if hasattr(member, 'cleared_fields'):
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
        wrapper.set_password(member.raw_password)
        del member.raw_password

        # assign address
        has_address = False
        for k in ADDRESS_FIELDS:
            if getattr(member, k, None):
                has_address = True
                break
        if has_address:
            wrapper.set_address(member.address, member.city,
                member.province, member.zipcode, member.country)

        consumer_id, uri = api.create_consumer(wrapper.consumer)
        neo_profile = NeoProfile.objects.get_or_create(user=member, consumer_id=consumer_id)
        api.complete_registration(consumer_id)  # activates the account

    else:
        if not USE_MCAL:
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

            # check if address needs to change
            has_address = False
            had_address = False
            address_changed = False
            for k in ADDRESS_FIELDS:
                current = getattr(member, k, None)
                old = old_member.get(k, None)
                if current:
                    has_address = True
                if old:
                    had_address = True
                if current != old:
                    address_changed = True
            # update address accordingly
            if address_changed:
                if not has_address:
                    wrapper.set_address(old_member.address, old_member.city,
                        old_member.province, old_member.zipcode, old_member.country,
                        modify_flag['DELETE'])
                elif not had_address:
                    wrapper.set_address(member.address, member.city,
                        member.province, member.zipcode, member.country)
                else:
                    wrapper.set_address(member.address, member.city,
                        member.province, member.zipcode, member.country,
                        mod_flag=modify_flag['UPDATE'])

            if not wrapper.is_empty:
	        consumer_id = NeoProfile.objects.get(user=member).consumer_id
                if not wrapper.profile_is_empty:
                    wrapper.set_ids_for_profile(api.get_consumer_profile(consumer_id))
                api.update_consumer(consumer_id, wrapper.consumer)
        
        # check if password needs to be changed
        raw_password = getattr(member, 'raw_password', None)
        if raw_password:
            old_password = getattr(member, 'old_password', None)
            if old_password:
                api.change_password(member.username, raw_password, old_password=old_password)
            else:
                api.change_password(member.username, raw_password, token=member.forgot_password_token)
            

    if not USE_MCAL:
        # cache this member after it is saved (thus created/updated successfully)
        cache.set(cache_key, dict((k, getattr(member, k, None)) \
            for k in NEO_ATTR.union(ADDRESS_FIELDS)), 1200)


@receiver(signals.post_save, sender=User)
def update_user_password(sender, *args, **kwargs):
    instance = kwargs['instance']
    if not isinstance(instance, Member) and NeoProfile.objects.filter(user=instance).exists():
	# check if password needs to be changed
        raw_password = getattr(instance, 'raw_password', None)
        if raw_password:
            old_password = getattr(instance, 'old_password', None)
            if old_password:
                api.change_password(instance.username, raw_password, old_password=old_password)
            else:
                api.change_password(instance.username, raw_password, token=instance.forgot_password_token)
	    delattr(instance, 'raw_password')


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
            member.update(wrapper.address) # special case
            # cache the neo member dictionary
            cache.set(cache_key, member, 1200)

        # update instance with Neo attributes
        for key, val in member.iteritems():
            setattr(instance, key, val)
if not USE_MCAL:
    signals.post_init.connect(load_consumer, sender=Member)


'''
Patch the user class so that the clear text
password is stored on the object, thus making
it accessible by Neo.
'''
def set_password(user, raw_password, old_password=None):
    try:
        NeoProfile.objects.get(user=user)
        if old_password:
            user.old_password = old_password
    except NeoProfile.DoesNotExist:
        pass
    user.raw_password = raw_password
    user.password = make_password(raw_password)
# use on class prepared instead
User.set_password = set_password
