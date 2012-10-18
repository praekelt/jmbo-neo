from datetime import date, datetime

from django.conf import settings

from foundry.models import Country

from neo.constants import country_option_id, address_type, gender, marital_status, \
    modify_flag, phone_type, email_category, comm_channel, question_category
from neo.xml import Consumer, ConsumerProfileType, PreferencesType, UserAccountType, \
    EmailDetailsType, PhoneDetailsType, AnswerType, CategoryType, LoginCredentialsType, \
    QuestionAnswerType, AddressDetailsType
from neo import api


# retrieve the brand id and promo code for the website
BRAND_ID = getattr(settings, 'NEO')['BRAND_ID']
PROMO_CODE = getattr(settings, 'NEO')['PROMO_CODE']


'''
A wrapper class that makes it easier to manage a consumer object
'''
class ConsumerWrapper(object):
    
    def __init__(self, consumer=None):
        if consumer is None:
            self._consumer = Consumer()
        else:
            self._consumer = consumer
    
    def _get_or_create_profile(self):
        if self._consumer.ConsumerProfile is None:
            # Neo requires a title but Jmbo members don't have titles
            self._consumer.ConsumerProfile = ConsumerProfileType(Title='', PromoCode=PROMO_CODE)
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
    
    @property
    def is_empty(self):
        return not (self._consumer.ConsumerProfile or self._consumer.UserAccount or self._consumer.Preferences)
    
    @property
    def profile_is_empty(self):
        return not self._consumer.ConsumerProfile

    def _get_preference(self, category_id, question_id):
        if self._consumer.Preferences is not None:
            for cat in self._consumer.Preferences.QuestionCategory:
                if cat.CategoryID == category_id:
                    for q in cat.QuestionAnswers:
                        if q.QuestionID == question_id:
                            return q.Answer
        return None
        
    def _get_opt_in(self, question_id, brand_id, comm_channel):
        answers = self._get_preference(question_category['OPTIN'], question_id)
        if answers:
            for a in answers:
                if a.CommunicationChannel == comm_channel:
                    return a.OptionID == 1
        return None
    
    def _set_preference(self, answer, category_id, question_id, mod_flag):
        prefs = self._get_or_create_preferences()
	if mod_flag == modify_flag['UPDATE']:
	    mod_flag = modify_flag['MODIFY']  # preferences use the modify flag instead
        answer.ModifyFlag = mod_flag
        q_category = None
        has_question = False
        for cat in prefs.QuestionCategory:
            if cat.CategoryID == category_id:
                q_category = cat
                for q in cat.QuestionAnswers:
                    if q.QuestionID == question_id:
                        q.add_Answer(answer)
                        has_question = True
                        break
            if q_category:
                break
        # if the question category or question does not exist
        if not has_question:
            if not q_category:
                q_category = CategoryType(CategoryID=category_id)
                prefs.add_QuestionCategory(q_category)
            q_answer = QuestionAnswerType(QuestionID=question_id)
            q_category.add_QuestionAnswers(q_answer)
            q_answer.add_Answer(answer)
                      

    def _set_opt_in(self, value, question_id, brand_id, comm_channel, mod_flag):
        answers = self._get_preference(question_category['OPTIN'], question_id)
        updated = False
        if answers:
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
            self._set_preference(answer, question_category['OPTIN'], question_id, mod_flag)
    
    def set_ids_for_profile(self, consumer):
	profile = consumer.ConsumerProfile
        if self.address and self._consumer.ConsumerProfile.Address[0].ModifyFlag != 'I':
            self._consumer.ConsumerProfile.Address[0].AddressID = profile.Address[0].AddressID
        if self.email:
            for email in self._consumer.ConsumerProfile.Email:
                if email.EmailCategory == email_category['PERSONAL'] and email.ModifyFlag != 'I':
                    for em in profile.Email:
                        if em.EmailCategory == email_category['PERSONAL']:
                            email.Id = em.Id
                            break
        if self.mobile_number:
            for email in self._consumer.ConsumerProfile.Email:
                if email.EmailCategory == email_category['MOBILE_NO'] and email.ModifyFlag != 'I':
                    for em in profile.Email:
                        if em.EmailCategory == email_category['MOBILE_NO']:
                            email.Id = em.Id
                            break
            if self._consumer.ConsumerProfile.Phone[0].ModifyFlag != 'I':
                self._consumer.ConsumerProfile.Phone[0].PhoneID = profile.Phone[0].PhoneID

    @property
    def consumer(self):
        return self._consumer
    
    @property
    def receive_sms(self):
        # 64 - receive communication from brand via communication channel?
        return self._get_opt_in(64, BRAND_ID, comm_channel['SMS'])
    
    @property
    def receive_email(self):
        # 64 - receive communication from brand via communication channel?
        return self._get_opt_in(64, BRAND_ID, comm_channel['EMAIL'])
    
    @property
    def country(self):
        # 92 - country of residence?
        answers = self._get_preference(question_category['GENERAL'], 92)
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
            return datetime.strptime(self._consumer.ConsumerProfile.DOB, "%Y-%m-%d").date()
        return None
    
    @property
    def email(self):
        if self._consumer.ConsumerProfile is not None:
            for email in self._consumer.ConsumerProfile.Email:
                if email.EmailCategory == email_category['PERSONAL']:
                    return email.EmailId
        return None
    
    @property
    def mobile_number(self):
        if self._consumer.ConsumerProfile is not None:
            for phone in self._consumer.ConsumerProfile.Phone:
                if phone.PhoneType == phone_type['MOBILE']:
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
    def address(self):
        if self._consumer.ConsumerProfile is not None:
            if self._consumer.ConsumerProfile.Address:
                a = self._consumer.ConsumerProfile.Address[0]
                return {
                    'city': a.City,
                    'province': a.StateOther,
                    'zipcode': a.ZipCode,
                    'country': Country.objects.get(country_code=a.Country),
                    'address': a.Address1,
                }
        return {}

    @property
    def gender(self):
        if self._consumer.ConsumerProfile is not None:
            return ('M' if self._consumer.ConsumerProfile.Gender == gender['MALE'] else 'F')
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
    
    def set_receive_sms(self, value, mod_flag=modify_flag['INSERT']):
        if value is not None:
            self._set_opt_in(value, 64, BRAND_ID, comm_channel['SMS'], mod_flag)
    
    def set_receive_email(self, value, mod_flag=modify_flag['INSERT']):
        if value is not None:
            self._set_opt_in(value, 64, BRAND_ID, comm_channel['EMAIL'], mod_flag)

    def set_country(self, country, mod_flag=modify_flag['INSERT']):
        if country:
            answers = self._get_preference(question_category['GENERAL'], 92)
            if answers is not None:
                answers[0].OptionID = country_option_id[country.country_code]
                answers[0].ModifyFlag = mod_flag
            else:
                answer = AnswerType(OptionID=country_option_id[country.country_code])
                self._set_preference(answer, question_category['GENERAL'], 92, mod_flag)
    
    def set_dob(self, dob, mod_flag=modify_flag['INSERT']):
        if dob:
            self._get_or_create_profile().DOB = dob.strftime("%Y-%m-%d")
    
    def set_first_name(self, first_name, mod_flag=modify_flag['INSERT']):
        self._get_or_create_profile().FirstName = first_name
    
    def set_last_name(self, last_name, mod_flag=modify_flag['INSERT']):
        self._get_or_create_profile().LastName = last_name
    
    def set_username(self, username, mod_flag=modify_flag['INSERT']):
        self._get_or_create_account().LoginCredentials.LoginName = username
        
    def set_password(self, password, mod_flag=modify_flag['INSERT']):
        self._get_or_create_account().LoginCredentials.Password = password
    
    def set_address(self, address_line, city, state, zipcode, country, mod_flag=modify_flag['INSERT']):
        profile = self._get_or_create_profile()
        updated = False
        for a in profile.Address:
            if a.AddressType == address_type['HOME']:
                a.Address1 = address_line
                a.City = city
                a.StateOther = state
                a.ZipCode = zipcode
                a.Country = country.country_code
                a.ModifyFlag = mod_flag
                updated = True
                break
        if not updated:
            profile.add_Address(AddressDetailsType(
                AddressType = address_type['HOME'],
                Address1 = address_line,
                City = city,
                StateOther = state,
                ZipCode = zipcode,
                Country = country.country_code,
                ModifyFlag = mod_flag,
            ))
    
    def set_gender(self, gendr, mod_flag=modify_flag['INSERT']):
        self._get_or_create_profile().Gender = gender['MALE'] if gendr == 'M' else gender['FEMALE']

    def set_email(self, email, mod_flag=modify_flag['INSERT']):
        if email:
            prof = self._get_or_create_profile()
            updated = False
            for em in prof.Email:
                if em.EmailCategory == email_category['PERSONAL']:
                    em.EmailId = email
                    em.ModifyFlag = mod_flag
                    updated = True
                    break
            if not updated:
                prof.add_Email(EmailDetailsType(
                    EmailId=email,
                    EmailCategory=email_category['PERSONAL'],
                    IsDefaultFlag=(0 if len(prof.Email) > 0 else 1),
                    ModifyFlag=mod_flag
                ))

    def set_mobile_number(self, mobile_number, mod_flag=modify_flag['INSERT']):
        if mobile_number:
            prof = self._get_or_create_profile()
            if len(prof.Phone) == 0:
                prof.add_Phone(PhoneDetailsType(
                    PhoneNumber=mobile_number,
                    PhoneType=phone_type['MOBILE'],
                    ModifyFlag=mod_flag
                ))
                prof.add_Email(EmailDetailsType(
                    EmailId=mobile_number,
                    EmailCategory=email_category['MOBILE_NO'],
                    IsDefaultFlag=(0 if len(prof.Email) > 0 else 1),
                    ModifyFlag=mod_flag
                ))
            else:
                prof.Phone[0].PhoneNumber = mobile_number
                prof.Phone[0].ModifyFlag = mod_flag
                for email in prof.Email:
                    if email.EmailCategory == email_category['MOBILE_NO']:
                        email.EmailId = email
                        email.ModifyFlag = mod_flag
                        break
