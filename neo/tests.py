import os.path
from datetime import timedelta

from django.test import TestCase
from django.test.client import Client
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.core.urlresolvers import reverse
from django.contrib.sessions.models import Session

from foundry.models import Member, Country

from neo.models import NeoProfile, NEO_ATTR
from neo.utils import NeoTokenGenerator

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
            'mobile_number': '+27733416692',
            'email': 'rizmari@praekeltconsulting.com',
            'address': 'address',
            'city': 'city',
            'province': 'province',
            'zipcode': 'zipcode',
            'gender': 'F',
        }

    def create_member(self):
        attrs = self.member_attrs.copy()
        # unique email and username for this test run
        attrs['username'] = 'user_%s' % timezone.now().strftime("%H:%M:%S.%f")
        attrs['email'] = "%s@praekeltconsulting.com" % attrs['username']
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
        for key in NEO_ATTR:
            self.assertEqual(getattr(member1, key), getattr(member2, key))
    
    def test_update_member(self):
        member = self.create_member()
        new_dob = timezone.now().date() - timedelta(days=24 * 365)
        new_country = Country.objects.create(
            title="South Africa",
            slug="south-africa",
            country_code="ZA",
        )
        # change the member attributes
        for key, val in self.member_attrs.iteritems():
            if key == 'dob':
                new_val = new_dob
            elif key == 'country':
                new_val = new_country
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
        self.assertEqual(response.status_code, 302)

    def test_forgot_password_token(self):
        member = self.create_member()
        token_generator = NeoTokenGenerator()
        self.assertTrue(token_generator.make_token(member))

    def test_reset_password(self):
        member = self.create_member()
        self.login_basic(member)
        response = self.client.post(reverse('password_reset'), {'mobile_number': '+27733416692'})
        self.assertEqual(response.status_code, 200)

    def test_reset_password_confirm(self):
        member = self.create_member()
        token_generator = NeoTokenGenerator()
        token = token_generator.make_token(member)
        if token_generator.check_token(member, token):
            member.set_password('new_password')
            member.save()
        else:
            self.assertTrue(False)
