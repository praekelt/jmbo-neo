from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models import signals
from django.dispatch import receiver

from foundry.models import Member

from neo import api
from neo.xml import Consumer, ConsumerProfileType, PreferencesType, UserAccountType, \
    EmailDetailsType, PhoneDetailsType, AnswerType


class NeoProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    # the Neo consumer id used in API requests
    consumer_id = models.PositiveIntegerField(primary_key=True)


@receiver(user_logged_out)
def notify_logout(sender, **kwargs):
    try:
        neo_profile = NeoProfile.objects.get(user=kwargs['user'])
        api.logout(neo_profile.consumer_id)
    except NeoProfile.DoesNotExist:
        pass # figure out something to do here


# ModifyFlag needs to be set to one of I (insert), U (update) and D (delete) for the following:
# AnswerType
# EmailDetailsType
# AddressDetailsType
# PhoneDetailsType


@receiver(signals.post_save)
def create_consumer(sender, **kwargs):
    if issubclass(sender, Member) and kwargs['created']:
        instance = kwargs['instance']
        # for registration ConsumerProfile, Preferences and UserAccount are mandatory
        
        # create consumer profile
        # NB. These ConsumerProfileType attributes must be required during registration for any Neo app
        profile = ConsumerProfileType({
            'Title': '',
            'FirstName': instance.first_name,
            'LastName': instance.last_name,
            'DOB': instance.dob.strftime("%Y-%m-%d"),
            'PromoCode': 'testPromo',
        })
        if getattr(instance, 'mobile_number', False):
            profile.add_Email(EmailDetailsType({
                'EmailId': instance.mobile_number,
                'EmailCategory': 3,
                'IsDefaultFlag': 1,
                'ModifyFlag': 'I'
            }))
            profile.add_Phone(PhoneDetailsType({
                'PhoneNumber': instance.mobile_number,
                'PhoneType': 3,
                'ModifyFlag': 'I'
            }))
        if getattr(instance, 'email', False):
            profile.add_Email(EmailDetailsType({
                'EmailId': instance.email,
                'EmailCategory': 1,
                'IsDefaultFlag': (0 if len(email) > 0 else 1),
                'ModifyFlag': 'I'
            }))
            
        # create consumer preferences
        preferences = PreferencesType({
            
        })
        # create consumer account details
        account = UserAccountType({
        })
        # create optional consumer attributes
        
        # create the consumer
        consumer = Consumer({
            'ConsumerProfile': profile,
            'Preferences': preferences,
            'UserAccount': account
        })
        consumer_id = api.create_consumer(consumer)
        
            