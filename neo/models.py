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


# the member attributes that are stored on Neo and in memcached
from_neo = ('username', 'password', 'first_name', \
    'last_name', 'dob', 'email', 'mobile_number', \
    'receive_sms', 'receive_email', 'country')


# a wrapper class that makes it easier to manage a consumer object
class ConsumerWrapper(object):
    
    def __init__(self, consumer=None):
        if consumer is None:
            self._consumer = Consumer()
        else:
            self._consumer = consumer
    
    def _get_or_create_profile(self):
        if self._consumer.ConsumerProfile is None:
            self._consumer.ConsumerProfile = ConsumerProfileType()
        return self._consumer.ConsumerProfile

    def _get_or_create_account(self):
        if self._consumer.UserAccount is None:
            self._consumer.UserAccount = UserAccountType()
        return self._consumer.UserAccount

    def _get_or_create_preferences(self):
        if self._consumer.Preferences is None:
            self._consumer.Preferences = PreferencesType()
        return self._consumer.Preferences
    
    def _check_preference(self, category_id, question_id):
        if self._consumer.Preferences is not None:
            for cat in self._consumer.Preferences.QuestionCategory:
                if cat.CategoryID == category_id:
                    for q in cat.QuestionAnswers:
                        if q.QuestionID == question_id:
                            return q.Answer
        return None
        
    def _check_opt_in(self, question_id, comm_channel):
        # 1 - opt in category
        answers = self._check_preference(1, question_id)
        if answers is not None:
            for a in answers:
                if a.CommunicationChannel == comm_channel:
                    return a.OptionID == 1
        return None
    
    @property
    def consumer(self):
        return self._consumer
    
    @property
    def receive_sms(self):
        # 64 - receive communication from brand via communication channel?
        # 4 - sms communication channel
        return self._check_opt_in(64, 4)
    
    @property
    def receive_email(self):
        # 64 - receive communication from brand via communication channel?
        # 1 - email communication channel
        return self._check_opt_in(64, 1)
    
    @property
    def country(self):
        # 4 - general category
        # 92 - country of residence?
        answers = self._check_preference(4, 92)
        if answers is not None:;
            country = answers[0].OptionID
            for code, option_id in country_option_id.iteritems():
                if option_id == country:
                    country = Country.objects.get(country_code=code)
                    return country
        return None
        
    @property
    def dob(self):
        if self._consumer.ConsumerProfile is not None and \
            self._consumer.ConsumerProfile.DOB is not None:
            return datetime.strptime(self._consumer.ConsumerProfile.DOB, "%Y-%m-%d")
        return None
    
    @property
    def email(self):
        if self._consumer.ConsumerProfile is not None:
            for email in self._consumer.ConsumerProfile.Email:
                if email.EmailCategory == 1:
                    return email.EmailId
        return None
    
    @property
    def mobile_number(self):
        if self._consumer.ConsumerProfile is not None:
            for phone in self._consumer.ConsumerProfile.Phone:
                if phone.PhoneType == 3:
                    return phone.PhoneNumber
        return None
    
    @property
    def first_name(self):
        if self._consumer.ConsumerProfile is not None:
            return self._consumer.ConsumerProfile.FirstName
        return None
    
    @property
    def last_name(self)
        if self._consumer.ConsumerProfile is not None:
            return self._consumer.ConsumerProfile.LastName
        return None
    
    @property
    def username(self):
        if self._consumer.UserAccount is not None:
            return self._consumer.UserAccount.LoginName
        return None

    @property
    def password(self):
        if self._consumer.UserAccount is not None:
            return self._consumer.UserAccount.Password
        return None
        
    def _set_property(self, obj, value, mod_flag='I'):
        pass
    
    def _set_preference(self):
        pass
    
    def set_receive_sms(self, value, mod_flag='I'):
        preferences = _get_or_create_preferences()
        val = self.receive_sms
        if val is None:
            pass
        # figure this one out


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
    cache_key = 'neo_consumer_%s' % member.pk
    # the member attributes that are stored on Neo and in memcached
    from_neo = ('username', 'password', 'first_name', \
        'last_name', 'dob', 'email', 'mobile_number', \
        'receive_sms', 'receive_email', 'country')
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
        old_member = cache.get(cache_key, None)
        if old_member is not None:  # it should never be None
            for k in from_neo:
                # check if cached version and current version of member differ
                if getattr(member, k, None) != old_member.get(k, None):
                    # update attribute on Neo
                    pass
    
    # cache this member after it is saved (thus created successfully)
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
            