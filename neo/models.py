from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models import signals
from django.dispatch import receiver
from django.conf import settings

from foundry.models import Member

from neo import api
from neo.constants import country_option_id
from neo.xml import Consumer, ConsumerProfileType, PreferencesType, UserAccountType, \
    EmailDetailsType, PhoneDetailsType, AnswerType, CategoryType, LoginCredentialsType, \
    QuestionAnswerType


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
        inst = kwargs['instance']
        brand_id = getattr(settings, 'NEO', {'BRAND_ID': 35})['BRAND_ID']
        promo_code = getattr(settings, 'NEO', {'PROMO_CODE': 'testPromo'})['PROMO_CODE']
        # for registration ConsumerProfile, Preferences and UserAccount are mandatory
        
        # create consumer profile
        # NB. These ConsumerProfileType attributes must be required during registration for any Neo app
        profile = ConsumerProfileType(
            Title='',
            FirstName=inst.first_name,
            LastName=inst.last_name,
            DOB=inst.dob.strftime("%Y-%m-%d"),
            PromoCode=promo_code,
        )
        if getattr(inst, 'mobile_number', False):
            profile.add_Email(EmailDetailsType(
                EmailId=inst.mobile_number,
                EmailCategory=3,
                IsDefaultFlag=1,
                ModifyFlag='I'
            ))
            profile.add_Phone(PhoneDetailsType(
                PhoneNumber=inst.mobile_number,
                PhoneType=3,
                ModifyFlag='I'
            ))
        if getattr(inst, 'email', False):
            profile.add_Email(EmailDetailsType(
                EmailId=inst.email,
                EmailCategory=1,
                IsDefaultFlag=(0 if len(profile.Email) > 0 else 1),
                ModifyFlag='I'
            ))
            
        # create consumer preferences
        preferences = PreferencesType()
        q_general = CategoryType(CategoryID=4)  # 4 - general
        q_general.add_QuestionAnswers(QuestionAnswerType(
            QuestionID=92,  # which country?
            Answer=[AnswerType(
                ModifyFlag='I',
                OptionID=country_option_id[inst.country.country_code] \
                    if inst.country.country_code in country_option_id else 253,  # 253 - unknown country
            ), ]
        ))
        q_optin = CategoryType(CategoryID=1)  # 1 - opt in
        q_optin.add_QuestionAnswers(QuestionAnswerType(
            QuestionID=64,  # receive communication from brand via communication channel?
            Answer=[AnswerType(
                ModifyFlag='I',
                OptionID=1 if inst.receive_sms else 2,
                BrandID=brand_id,
                CommunicationChannel=4,  # 4 - sms channel
            ),
            AnswerType(
                ModifyFlag='I',
                OptionID=1 if inst.receive_email else 2,
                BrandID=brand_id,
                CommunicationChannel=1,  # 1 - email channel
            )]
        ))
        
        preferences.add_QuestionCategory(q_general)
        preferences.add_QuestionCategory(q_optin)
        
        # create consumer account details
        account = UserAccountType(
            LoginCredentialsType(
                LoginName=inst.username,
                Password=inst.password
            )
        )
        
        # create the consumer
        consumer = Consumer(
            ConsumerProfile=profile,
            Preferences=preferences,
            UserAccount=account
        )
        try:
            consumer_id = api.create_consumer(consumer)
            neo_profile = NeoProfile(user=inst, consumer_id=consumer_id)
            neo_profile.save()
        except api.NeoError:
            pass
        
            