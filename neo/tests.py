import os.path
from datetime import timedelta

from django.test import TestCase
from django.test.client import Client
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.core.cache import cache

from foundry.models import Member, Country
from neo.models import NeoProfile, NEO_ATTR


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
            'mobile_number': '7733387786',
            'email': 'firstname@test.com',
        }

    def create_member(self):
        attrs = self.member_attrs.copy()
        # unique username for this test run
        attrs['username'] = 'user_%s' % timezone.now().strftime("%H:%M:%S.%f")
        member = Member(**attrs)
        member.set_password('password')
        member.save()
        return member
        
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
    
    def test_login(self):
        member = self.create_member()
        self.client.login(username=member.username, password=member.password)
        self.assertTrue(member.is_authenticated())

    def test_logout(self):
        member = self.create_member()
        self.client.login(username=member.username, password=member.password)
        self.client.logout()
        self.assertFalse(member.is_authenticated())
