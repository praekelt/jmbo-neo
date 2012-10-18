import os.path
import re
import time
from datetime import timedelta

from django.test import TestCase
from django.test.client import Client
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.sessions.models import Session
from django.contrib.sites.models import Site

from foundry.models import Member, Country
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

    def create_member(self):
        attrs = self.member_attrs.copy()
        # unique email and username for this test run
        id = "%f" % time.time()
        dot = id.rindex('.')
        id = id[dot - 7:dot] + id[dot+1:dot+4]
        attrs['username'] = 'user_%s' % id
        attrs['email'] = "%s@praekeltconsulting.com" % id
        attrs['mobile_number'] = id
        member = Member(**attrs)
        member.set_password('password')
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

    def test_login(self):
        member = self.create_member()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        Session.objects.all().delete()
        settings.AUTHENTICATION_BACKENDS = ('foundry.backends.MultiBackend', )
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.assertTrue(self.login_basic(member))

    # test needs to be improved
    def test_logout(self):
        member = self.create_member()
        settings.AUTHENTICATION_BACKENDS = ('neo.backends.NeoBackend', )
        self.client.login(username=member.username, password='password')
        self.client.logout()

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
