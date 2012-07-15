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
NEO_ATTR = ('username', 'password', 'first_name', \
    'last_name', 'dob', 'email', 'mobile_number', \
    'receive_sms', 'receive_email', 'country')

# retrieve the brand id and promo code for the website
BRAND_ID = getattr(settings, 'NEO', {'BRAND_ID': 35})['BRAND_ID']
PROMO_CODE = getattr(settings, 'NEO', {'PROMO_CODE': 'testPromo'})['PROMO_CODE']


# a wrapper class that makes it easier to manage a consumer object
class ConsumerWrapper(object):
    
    def __init__(self, consumer=None):
        if consumer is None:
            self._consumer = Consumer(PromoCode=PROMO_CODE)
        else:
            self._consumer = consumer
    
    def _get_or_create_profile(self):
        if self._consumer.ConsumerProfile is None:
            # Neo requires a title but Jmbo members don't have titles
            self._consumer.ConsumerProfile = ConsumerProfileType(Title='')
        return self._consumer.ConsumerProfile

    def _get_or_create_account(self):
        if self._consumer.UserAccount is None:
            self._consumer.UserAccount = UserAccountType()
            self._consumer.UserAccount.LoginCredentials = LoginCredentialsType()
        return self._consumer.UserAccount

    def _get_or_create_preferences(self):
        if self._consumer.Preferences is None:
            self._consumer.Preferences = PreferencesType()
        return self._consumer.Preferences
    
    def _get_preference(self, category_id, question_id):
        if self._consumer.Preferences is not None:
            for cat in self._consumer.Preferences.QuestionCategory:
                if cat.CategoryID == category_id:
                    for q in cat.QuestionAnswers:
                        if q.QuestionID == question_id:
                            return q.Answer
        return None
        
    def _get_opt_in(self, question_id, brand_id, comm_channel):
        # 1 - opt in category
        answers = self._get_preference(1, question_id)
        if answers is not None:
            for a in answers:
                if a.CommunicationChannel == comm_channel:
                    return a.OptionID == 1
        return None
    
    def _set_preference(self, answer, category_id, question_id, mod_flag):
        prefs = self._get_or_create_preferences()
        answer.ModifyFlag = mod_flag
        for cat in prefs.QuestionCategory:
            if cat.CategoryID == category_id:
                for q in cat.QuestionAnswers:
                    if q.QuestionID == question_id:
                        q.add_Answer(answer)
        
    
    def _set_opt_in(self, value, question_id, brand_id, comm_channel, mod_flag):
        answers = self._get_preference(1, question_id)
        updated = False
        if answers is not None:
            for a in answers:
                if a.BrandID == brand_id and a.CommunicationChannel == comm_channel:
                    a.OptionID = 1 if value else 2
                    a.ModifyFlag = mod_flag
                    updated = True
                    break
        if not updated:
            answer = AnswerType(
                OptionID=(1 if value else 2),
                BrandID=brand_id,
                CommunicationChannel=comm_channel
            )
            self._set_preference(answer, 1, question_id, mod_flag)
            
    @property
    def consumer(self):
        return self._consumer
    
    @property
    def receive_sms(self):
        # 64 - receive communication from brand via communication channel?
        # 4 - sms communication channel
        return self._get_opt_in(64, BRAND_ID, 4)
    
    @property
    def receive_email(self):
        # 64 - receive communication from brand via communication channel?
        # 1 - email communication channel
        return self._get_opt_in(64, BRAND_ID, 1)
    
    @property
    def country(self):
        # 4 - general category
        # 92 - country of residence?
        answers = self._get_preference(4, 92)
        if answers is not None:
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
    def last_name(self):
        if self._consumer.ConsumerProfile is not None:
            return self._consumer.ConsumerProfile.LastName
        return None
    
    @property
    def username(self):
        if self._consumer.UserAccount is not None:
            return self._consumer.UserAccount.LoginCredentials.LoginName
        return None

    @property
    def password(self):
        if self._consumer.UserAccount is not None:
            return self._consumer.UserAccount.LoginCredentials.Password
        return None  
    
    def set_receive_sms(self, value, mod_flag='I'):
        if value is not None:
            self._set_opt_in(value, 64, BRAND_ID, 4, mod_flag)
    
    def set_receive_email(self, value, mod_flag='I'):
        if value is not None:
            self._set_opt_in(value, 64, BRAND_ID, 1, mod_flag)

    def set_country(self, country, mod_flag='I'):
        if country is not None:
            answers = self._get_preference(4, 92)
            if answers is not None:
                answers[0].OptionID = country_option_id[country.country_code]
                answers[0].ModifyFlag = mod_flag
            else:
                answer = AnswerType(OptionID=country_option_id[country.country_code])
                self._set_preference(answer, 4, 92, mod_flag)
    
    def set_dob(self, dob, mod_flag='I'):
        if dob is not None:
            self._get_or_create_profile().DOB = dob.strftime("%Y-%m-%d")
    
    def set_first_name(self, first_name, mod_flag='I'):
        self._get_or_create_profile().FirstName = first_name
    
    def set_last_name(self, last_name, mod_flag='I'):
        self._get_or_create_profile().LastName = last_name
    
    def set_username(self, username, mod_flag='I'):
        self._get_or_create_account().LoginCredentials.LoginName = username
        
    def set_password(self, password, mod_flag='I'):
        self._get_or_create_account().LoginCredentials.Password = password
        
    def set_email(self, email, mod_flag='I'):
        if email is not None:
            prof = self._get_or_create_profile()
            updated = False
            for email in prof.Email:
                if email.EmailCategory == 1:
                    email.EmailId = email
                    email.ModifyFlag = mod_flag
                    updated = True
                    break
            if not updated:
                prof.add_Email(EmailDetailsType(
                    EmailId=email,
                    EmailCategory=1,
                    IsDefaultFlag=(0 if len(prof.Email) > 0 else 1),
                    ModifyFlag=mod_flag
                ))

    def set_mobile_number(self, mobile_number, mod_flag='I'):
        if mobile_number is not None:
            prof = self._get_or_create_profile()
            if len(prof.Phone) == 0:
                prof.add_Phone(PhoneDetailsType(
                    PhoneNumber=mobile_number,
                    PhoneType=3,
                    ModifyFlag=mod_flag
                ))
                prof.add_Email(EmailDetailsType(
                    EmailId=mobile_number,
                    EmailCategory=3,
                    IsDefaultFlag=(0 if len(prof.Email) > 0 else 1),
                    ModifyFlag=mod_flag
                ))
            else:
                prof.Phone[0].PhoneNumber = mobile_number
                prof.Phone[0].ModifyFlag = mod_flag
                for email in prof.Email:
                    if email.EmailCategory == 3:
                        email.EmailId = email
                        email.ModifyFlag = mod_flag
                        break

                    
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
        wrapper.set_first_name(member.first_name)
        wrapper.set_last_name(member.last_name)
        wrapper.set_dob(member.dob)
        wrapper.set_email(member.email)
        wrapper.set_mobile_number(member.mobile_number)
        wrapper.set_receive_email(member.receive_email)
        wrapper.set_receive_sms(member.receive_sms)
        wrapper.set_country(member.country)
        wrapper.set_username(member.username)
        wrapper.set_password(member.password)
        try:
            consumer_id = api.create_consumer(wrapper.consumer)
            neo_profile = NeoProfile(user=member, consumer_id=consumer_id)
            neo_profile.save()
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
            