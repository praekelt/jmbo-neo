import os.path
import re
import time
from datetime import timedelta, date, datetime

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
from django.contrib.auth import login, get_backends
from django.contrib.auth.models import User
from django.db.models.fields import FieldDoesNotExist
from django.contrib.auth.hashers import make_password
from django.db import connection, transaction

from foundry.models import Member, Country, RegistrationPreferences
from competition.models import Competition

from neo.models import NeoProfile, NEO_ATTR, ADDRESS_FIELDS
from neo.forms import NeoTokenGenerator
from neo import api


class NeoTestCase(TestCase):

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
        required_fields_str = ','.join(['first_name', 'last_name', 'dob', \
            'email', 'mobile_number', 'country', 'gender', 'city', 'country', \
            'province', 'zipcode', 'address'])
        cursor = connection.cursor()
        cursor.execute("DELETE FROM preferences_registrationpreferences")
        cursor.execute("INSERT INTO preferences_preferences (id) VALUES (1)")
        cursor.execute("""INSERT INTO preferences_registrationpreferences (preferences_ptr_id, 
            raw_required_fields, raw_display_fields, raw_unique_fields, raw_field_order) VALUES (1, %s, '', '', '{}')""", \
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
        cache.clear();
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
        '''
        member = self.create_member()
        request = HttpRequest()
        request.session = self.session
        request.COOKIES[settings.SESSION_COOKIE_NAME] = self.session.session_key
        backend = get_backends()[0]
        member.backend = "%s.%s" % (backend.__module__, backend.__class__.__name__)
        login(request, member)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = self.session.session_key
        self.client.logout()

    def test_authentication(self):
        member = self.create_member()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        Session.objects.all().delete()
        settings.AUTHENTICATION_BACKENDS = ('foundry.backends.MultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.assertTrue(self.login_basic(member))
    
    def test_auto_create_member_from_consumer(self):
        member = self.create_member()
        Member.objects.filter(username=member.username).delete()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend', )
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
        values_user = values_user + "'False','False','True','now','now')"
        cursor = connection.cursor()
        cursor.execute("INSERT INTO auth_user %s VALUES %s" % (columns_user, values_user))
        cursor.execute("SELECT id FROM auth_user WHERE username = %s", [attrs['username']])
        pk = cursor.fetchall()[0][0]
        columns_member = columns_member + "user_ptr_id,image,view_count,crop_from,receive_sms,receive_email,is_profile_complete)"
        values_member = values_member + ("%d,'',0,'','False','False','True')" % pk)
        cursor.execute("INSERT INTO foundry_member %s VALUES %s" % (columns_member, values_member))
        transaction.commit_unless_managed()
        member = Member.objects.get(pk=pk)
        self.client.login(username=member.username, password='password')
        self.assertTrue(NeoProfile.objects.filter(user=member).exists())

    def test_password_change(self):
        member = self.create_member()
	self.login_basic(member)
        response = self.client.post(reverse('password_change'), {'old_password': 'password',
            'new_password1': 'new_password', 'new_password2': 'new_password'})
	relative_path = re.sub(r'https?://\w+', '', response['Location'])
	self.assertEqual(relative_path, reverse('password_change_done'))
        self.client.logout()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend', )
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
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend', )
        self.assertTrue(self.client.login(username=member.username, password='new_password'))

    def test_member_create_on_complete(self):
        member = self.create_member_partial()
        self.assertFalse(NeoProfile.objects.filter(user=member).exists())
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.client.logout()
        member.gender = 'F'
        member.save()
        self.assertTrue(NeoProfile.objects.filter(user=member).exists())
