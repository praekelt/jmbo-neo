# encoding: utf-8
import os.path
import re
import time
from StringIO import StringIO
from datetime import timedelta, date, datetime

from lxml import etree, objectify

from django.test import TestCase
from django.test.client import Client
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.sessions.models import Session
from django.contrib.sites.models import Site
from django.http import HttpRequest
from django.utils.importlib import import_module
from django.contrib.auth import login, get_backends, authenticate
from django.contrib.auth.models import User
from django.db.models.fields import FieldDoesNotExist
from django.contrib.auth.hashers import make_password
from django.db import connection, transaction

from foundry.models import Member, Country, RegistrationPreferences
from competition.models import Competition

from neo.models import NeoProfile, NEO_ATTR, ADDRESS_FIELDS, dataloadtool_export
from neo.forms import NeoTokenGenerator
from neo import api, constants
from neo.utils import BRAND_ID, PROMO_CODE, ConsumerWrapper, dataloadtool_schema


class _MemberTestCase(object):
    """
    Test helper for member creation.
    """

    def setUp(self):
        country = Country.objects.create(
            title='United States of America',
            slug='united-states-of-america',
            country_code='US',
        )
        self.member_attrs = {
            'first_name': 'firstname',
            'last_name': 'lastname',
            'dob': timezone.now().date() - timedelta(days=22 * 365),
            'country': country,
            'address': 'address',
            'city': 'city',
            'province': 'province',
            'zipcode': 'zipcode',
            'gender': 'F',
        }
        settings.SESSION_ENGINE = 'django.contrib.sessions.backends.file'
        engine = import_module(settings.SESSION_ENGINE)
        store = engine.SessionStore()
        store.save()
        self.session = store
        required_fields_str = ','.join(['first_name', 'last_name', 'dob',
            'email', 'mobile_number', 'country', 'gender', 'city', 'country',
            'province', 'zipcode', 'address'])
        cursor = connection.cursor()
        cursor.execute("DELETE FROM preferences_registrationpreferences")
        cursor.execute("INSERT INTO preferences_preferences (id) VALUES (1)")
        cursor.execute("""INSERT INTO preferences_registrationpreferences (preferences_ptr_id,
            raw_required_fields, raw_display_fields, raw_unique_fields, raw_field_order) VALUES (1, %s, '', '', '{}')""",
            [required_fields_str])
        cursor.execute("INSERT INTO preferences_preferences_sites (preferences_id, site_id) VALUES (1, 1)")
        transaction.commit_unless_managed()

    def create_member_partial(self, commit=True):
        attrs = self.member_attrs.copy()
        del attrs['gender']
        # unique email and username for this test run
        id = "%f" % time.time()
        dot = id.rindex('.')
        id = id[dot - 7:dot] + id[dot+1:dot+4]
        attrs['username'] = 'user_%s' % id
        attrs['email'] = "%s@praekeltconsulting.com" % id
        attrs['mobile_number'] = id
        member = Member(**attrs)
        member.set_password('password')
        if commit:
            member.save()
        return member

    def create_member(self):
        member = self.create_member_partial(commit=False)
        member.gender = 'F'
        member.save()
        return member


class NeoTestCase(_MemberTestCase, TestCase):

    def login_basic(self, member):
        Session.objects.all().delete()
        settings.AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend', )
        return self.client.login(username=member.username, password='password')

    def test_create_member(self):
        member = self.create_member()
        self.assertEqual(NeoProfile.objects.filter(user=member.id).count(), 1)

    def test_get_member(self):
        member1 = self.create_member()
        # clear the cached attributes of the newly created member
        cache.clear()
        # retrieve the member from db + Neo
        member2 = Member.objects.all()[0]
        for key in NEO_ATTR.union(ADDRESS_FIELDS):
            self.assertEqual(getattr(member1, key), getattr(member2, key))

    def test_update_member(self):
        member = self.create_member()
        new_dob = timezone.now().date() - timedelta(days=24 * 365)
        new_country = Country.objects.create(
            title="South Africa",
            slug="south-africa",
            country_code="ZA",
        )
        new_gender = 'M'
        # change the member attributes
        for key, val in self.member_attrs.iteritems():
            if key == 'dob':
                new_val = new_dob
            elif key == 'country':
                new_val = new_country
            elif key == 'gender':
                new_val = new_gender
            else:
                new_val = "new_" + val
            setattr(member, key, new_val)
        member.save()
        if settings.NEO.get('USE_MCAL', False):
            consumer = api.get_consumer(member.neoprofile.consumer_id, username=member.username, password='password')
            wrapper = ConsumerWrapper(consumer=consumer)
            fields_to_check = self.member_attrs.copy()
            for key in ('address', 'city', 'province', 'zipcode'):
                del fields_to_check[key]
            for field, val in fields_to_check.iteritems():
                new_attr = getattr(wrapper, field)
                if isinstance(new_attr, dict):
                    for k, v in new_attr.iteritems():
                        self.assertEqual(getattr(member, k), v)
                else:
                    self.assertEqual(getattr(member, field), new_attr)

        else:
            cache.clear()
            # retrieve the member from db + Neo
            member = Member.objects.all()[0]
            # check that updated values had been stored on Neo
            for key, val in self.member_attrs.iteritems():
                if key == 'dob':
                    new_val = new_dob
                elif key == 'country':
                    new_val = new_country
                elif key == 'gender':
                    new_val = new_gender
                else:
                    new_val = "new_" + val
                self.assertEqual(getattr(member, key), new_val)

    def test_login_logout(self):
        '''
        jmbo-foundry allows user login without authentication, e.g. right after a user joins.
        This breaks functionality that relies on authentication occurring before login.
        EDIT: changed jmbo-foundry to authenticate before login
        '''
        member = self.create_member()
        request = HttpRequest()
        request.session = self.session
        request.COOKIES[settings.SESSION_COOKIE_NAME] = self.session.session_key
        member = authenticate(username=member.username, password='password')
        login(request, member)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = self.session.session_key
        self.client.logout()

    def test_authentication(self):
        member = self.create_member()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoMultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        Session.objects.all().delete()
        settings.AUTHENTICATION_BACKENDS = ('foundry.backends.MultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.assertTrue(self.login_basic(member))
        self.client.logout()

    def test_auto_create_member_from_consumer(self):
        member = self.create_member()
        Member.objects.filter(username=member.username).delete()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoMultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.assertTrue(Member.objects.filter(username=member.username).exists())

    def test_auto_create_consumer_from_member(self):
        '''
        Insert new member directly into db to avoid patched Member/User methods
        '''
        attrs = self.member_attrs.copy()
        id = "%f" % time.time()
        dot = id.rindex('.')
        id = id[dot - 7:dot] + id[dot+1:dot+4]
        attrs['username'] = 'user_%s' % id
        attrs['email'] = "%s@praekeltconsulting.com" % id
        attrs['mobile_number'] = id
        attrs['country_id'] = attrs['country'].pk
        attrs['password'] = make_password('password')
        del attrs['country']
        columns_user = "("
        values_user = "("
        columns_member = "("
        values_member = "("
        for key, val in attrs.iteritems():
            column = "%s," % key
            if isinstance(val, basestring) or isinstance(val, bool):
                value = "'%s'," % val
            elif isinstance(val, date):
                value = "'%s'," % val.strftime("%Y-%m-%d")
            else:
                value = "%s," % val
            try:
                User._meta.get_field_by_name(key)
                values_user += value
                columns_user += column
            except FieldDoesNotExist:
                values_member += value
                columns_member += column
        columns_user = columns_user + "is_staff,is_superuser,is_active,last_login,date_joined)"
        values_user = values_user + "0,0,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        cursor = connection.cursor()
        cursor.execute("INSERT INTO auth_user %s VALUES %s" % (columns_user, values_user))
        cursor.execute("SELECT id FROM auth_user WHERE username = %s", [attrs['username']])
        pk = cursor.fetchall()[0][0]
        columns_member = columns_member + "user_ptr_id,image,view_count,crop_from,receive_sms,receive_email,is_profile_complete)"
        values_member = values_member + ("%d,'',0,'',0,0,1)" % pk)
        cursor.execute("INSERT INTO foundry_member %s VALUES %s" % (columns_member, values_member))
        transaction.commit_unless_managed()
        member = Member.objects.get(pk=pk)
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoMultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.assertTrue(NeoProfile.objects.filter(user=member).exists())

    def test_password_change(self):
        member = self.create_member()
        self.login_basic(member)
        response = self.client.post(reverse('password_change'), {'old_password': 'password',
            'new_password1': 'new_password', 'new_password2': 'new_password'})
        relative_path = re.sub(r'https?://\w+', '', response['Location'])
        self.assertEqual(relative_path, reverse('password_change_done'))
        self.client.logout()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoMultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='new_password'))

    def test_generate_forgot_password_token(self):
        member = self.create_member()
        token_generator = NeoTokenGenerator()
        self.assertTrue(token_generator.make_token(member))

    def test_password_reset(self):
        member = self.create_member()
        self.login_basic(member)
        response = self.client.post(reverse('password_reset'), {'email': member.email})
        relative_path = re.sub(r'https?://\w+', '', response['Location'])
        self.assertEqual(relative_path, reverse('password_reset_done'))

    def test_password_reset_confirm(self):
        member = self.create_member()
        token_generator = NeoTokenGenerator()
        # get rid of this simplification and actually use the reverse
        token = token_generator.make_token(member)
        self.assertTrue(token_generator.check_token(member, token))
        member.set_password('new_password')
        member.save()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoMultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='new_password'))

    def test_member_create_on_complete(self):
        member = self.create_member_partial()
        self.assertFalse(NeoProfile.objects.filter(user=member).exists())
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.client.logout()
        member.gender = 'F'
        member.save()
        self.assertTrue(NeoProfile.objects.filter(user=member).exists())


class DataLoadToolExportTestCase(_MemberTestCase, TestCase):
    """
    Exporting to the Data Load Tool.
    """

    def setUp(self):
        super(DataLoadToolExportTestCase, self).setUp()
        self.maxDiff = None  # For XML document diffs.
        self.consumers_schema = dataloadtool_schema('Consumers.xsd')
        self.parser = objectify.makeparser(schema=self.consumers_schema)

    def assertValidates(self, xml):
        """
        The given XML string should be a valid Consumers.xsd document.

        :return: The parsed tree.
        """
        tree = etree.fromstring(xml)
        self.assertTrue(
            self.consumers_schema.validate(tree),
            'Validation failed: {0}'.format(self.consumers_schema.error_log.last_error)
        )

    def expected_consumer(self, member, **kwargs):
        """
        Return an expected Consumer record for the current test data.

        :param member: Member instance to take variable fields from.
        :param kwargs: Additional attributes for the Consumer element.
        :rtype: `objectify` tree
        """
        E = objectify.ElementMaker(annotate=False)
        genderkey = {'F': 'FEMALE', 'M': 'MALE'}[member.gender]
        consumerprofile = E.ConsumerProfile(
            E.Title(''),
            E.FirstName(member.first_name), E.LastName(member.last_name),
            E.DOB(member.dob.strftime('%Y-%m-%d')),
            E.Gender(constants.gender[genderkey]),
            E.Address(E.Address1(member.address), E.City(member.city), E.Country(member.country.country_code), E.ZipCode(member.zipcode), E.AddressType(constants.address_type['HOME']), E.StateOther('province'), E.ModifyFlag(constants.modify_flag['INSERT'])),
            E.Phone(E.PhoneNumber(member.mobile_number), E.PhoneType(constants.phone_type['MOBILE']), E.ModifyFlag(constants.modify_flag['INSERT'])),
            E.PromoCode(PROMO_CODE),
            E.Email(E.EmailId(member.mobile_number), E.EmailCategory(constants.email_category['MOBILE_NO']), E.IsDefaultFlag(1), E.ModifyFlag(constants.modify_flag['INSERT'])),
            E.Email(E.EmailId(member.email), E.EmailCategory(constants.email_category['PERSONAL']), E.IsDefaultFlag(0), E.ModifyFlag(constants.modify_flag['INSERT'])),
        )
        preferences = E.Preferences(
            E.QuestionCategory(
                E.CategoryID(constants.question_category['GENERAL']),
                E.QuestionAnswers(
                    E.QuestionID(92),
                    E.Answer(E.OptionID(222), E.ModifyFlag(constants.modify_flag['INSERT'])),
                ),
            ),
            E.QuestionCategory(
                E.CategoryID(constants.question_category['OPTIN']),
                E.QuestionAnswers(
                    E.QuestionID(64),
                    E.Answer(E.OptionID(2), E.ModifyFlag(constants.modify_flag['INSERT']), E.BrandID(BRAND_ID), E.CommunicationChannel(constants.comm_channel['EMAIL'])),
                    E.Answer(E.OptionID(2), E.ModifyFlag(constants.modify_flag['INSERT']), E.BrandID(BRAND_ID), E.CommunicationChannel(constants.comm_channel['SMS'])),
                ),
            ),
        )
        useraccount = E.UserAccount(
            E.LoginCredentials(E.LoginName(member.username), E.Password('password')),
        )
        return E.Consumer(consumerprofile, preferences, useraccount, **kwargs)

    def expected_consumers(self, members):
        """
        Return an expected Consumers structure for the given members.

        :rtype: `objectify` tree
        """
        E = objectify.ElementMaker(annotate=False)
        # The Consumer records must be uniquely numbered to be valid: test that
        # we're numbering them sequentially.
        _consumers = [self.expected_consumer(member, recordNumber=str(i))
                      for (i, member) in enumerate(members)]
        return E.Consumers(*_consumers)

    def test_dataloadtool_export(self):
        """
        Validate `dataloadtool_export()` against the schema and expected data.
        """
        members = [self.create_member_partial(commit=False), self.create_member_partial(commit=False)]
        members[0].gender = 'F'
        members[1].gender = 'M'

        sio = StringIO()
        dataloadtool_export(sio, members)
        xml = sio.getvalue()
        self.assertValidates(xml)

        consumers = objectify.fromstring(xml, self.parser)
        self.assertEqual(
            objectify.dump(self.expected_consumers(members)),
            objectify.dump(consumers))

    def test_dataloadtool_export_unicode(self):
        """
        `dataloadtool_export()` should handle non-ASCII data.
        """
        member = self.create_member_partial(commit=False)
        member.gender = 'F'
        member.first_name = u'fïrstnâmé'

        sio = StringIO()
        dataloadtool_export(sio, [member])
        xml = sio.getvalue()
        self.assertValidates(xml)

        consumers = objectify.fromstring(xml, self.parser)
        self.assertEqual(
            objectify.dump(self.expected_consumers([member])),
            objectify.dump(consumers))
