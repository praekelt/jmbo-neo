from datetime import datetime

from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models import signals
from django.dispatch import receiver
from django.conf import settings
from django.core.cache import cache

from foundry.models import Member, Country

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


@receiver(signals.post_save, sender=Member)
def create_consumer(sender, **kwargs):
    member = kwargs['instance']
    if kwargs['created']:
        brand_id = getattr(settings, 'NEO', {'BRAND_ID': 35})['BRAND_ID']
        promo_code = getattr(settings, 'NEO', {'PROMO_CODE': 'testPromo'})['PROMO_CODE']
        # for registration ConsumerProfile, Preferences and UserAccount are mandatory
        
        # create consumer profile
        # NB. These ConsumerProfileType attributes must be required during registration for any Neo app
        profile = ConsumerProfileType(
            Title='',
            FirstName=member.first_name,
            LastName=member.last_name,
            DOB=member.dob.strftime("%Y-%m-%d"),
            PromoCode=promo_code,
        )
        if getattr(member, 'mobile_number', False):
            profile.add_Email(EmailDetailsType(
                EmailId=member.mobile_number,
                EmailCategory=3,
                IsDefaultFlag=1,
                ModifyFlag='I'
            ))
            profile.add_Phone(PhoneDetailsType(
                PhoneNumber=member.mobile_number,
                PhoneType=3,
                ModifyFlag='I'
            ))
        if getattr(member, 'email', False):
            profile.add_Email(EmailDetailsType(
                EmailId=member.email,
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
                OptionID=country_option_id[member.country.country_code] \
                    if member.country.country_code in country_option_id else 253,  # 253 - unknown country
            ), ]
        ))
        q_optin = CategoryType(CategoryID=1)  # 1 - opt in
        q_optin.add_QuestionAnswers(QuestionAnswerType(
            QuestionID=64,  # receive communication from brand via communication channel?
            Answer=[AnswerType(
                ModifyFlag='I',
                OptionID=1 if member.receive_sms else 2,
                BrandID=brand_id,
                CommunicationChannel=4,  # 4 - sms channel
            ),
            AnswerType(
                ModifyFlag='I',
                OptionID=1 if member.receive_email else 2,
                BrandID=brand_id,
                CommunicationChannel=1,  # 1 - email channel
            )]
        ))
        
        preferences.add_QuestionCategory(q_general)
        preferences.add_QuestionCategory(q_optin)
        
        # create consumer account details
        account = UserAccountType(
            LoginCredentialsType(
                LoginName=member.username,
                Password=member.password
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
            neo_profile = NeoProfile(user=member, consumer_id=consumer_id)
            neo_profile.save()
        except api.NeoError:
            pass

    else:
        # update changed attributes
        pass
    
    # cache this member after it is saved (thus created successfully)
    from_neo = ('username', 'password', 'first_name', \
        'last_name', 'dob', 'email', 'mobile_number', \
        'receive_sms', 'receive_email', 'country')
    cache_key = 'neo_consumer_%s' % member.pk
    cache.set(cache_key, dict((k, getattr(member, k, None)) \
        for k in from_neo), 1200)


@receiver(signals.pre_init, sender=Member)
def load_consumer(sender, **kwargs):
    init_args = kwargs['args']
    # if the object being instantiated has a pk, i.e. has been saved to the db
    if len(init_args) > 0 and init_args[0]:
        pk = init_args[0]
        cache_key = 'neo_consumer_%s' % pk
        member = cache.get(cache_key, None)
        if member is None:
            consumer_id = NeoProfile.objects.get(user=pk).consumer_id
            # retrieve member attributes from Neo
            consumer = api.get_consumer(consumer_id)
            email = None
            mobile = None
            for email in consumer.ConsumerProfile.Email:
                if email.EmailCategory == 1:
                    email = email.EmailId
                elif email.EmailCategory == 3:
                    mobile = email.EmailId
            receive_sms = None
            receive_email = None
            country = None
            for p in consumer.Preferences:
                for q in p.QuestionAnswers:
                    if q.QuestionID == 92:
                        country = q.Answer[0].OptionID
                    elif q.QuestionID == 64:
                        for a in q.Answer:
                            if a.CommunicationChannel == 1:
                                receive_email = True if a.OptionID == 1 else False
                            elif a.CommunicationChannel == 4:
                                receive_sms = True if a.OptionID == 1 else False
            for code, option_id in country_option_id.iteritems():
                if option_id == country:
                    country = Country.objects.get(country_code=code)
                    break
            
            member={
                'username': consumer.UserAccount.LoginCredentials.LoginName,
                'password': consumer.UserAccount.LoginCredentials.Password,
                'first_name': consumer.ConsumerProfile.FirstName,
                'last_name': consumer.ConsumerProfile.LastName,
                'dob': datetime.strptime(consumer.ConsumerProfile.DOB, "%Y-%m-%d"),
                'email': email,
                'mobile_number': mobile,
                'receive_sms': receive_sms,
                'receive_email': receive_email,
                'country': country,
            }
            # cache the neo member dictionary
            cache.set(cache_key, member, 1200)
        
        # update init_args
        i = 0
        for field in Member._meta.fields:
            val = member.get(field.name, None)
            if val is not None:
                init_args[i] = val 
            i += 1
            