import os.path
from datetime import timedelta

from django.test import TestCase
from django.test.client import Client
from django.core.urlresolvers import reverse
from django.utils import timezone

from foundry.models import Member, Country
from neo.models import NeoProfile


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
            'password': 'password',
            'country': country,
            'mobile_number': '7733387786',
            'email': 'firstname@test.com',
        }

    def test_create_member(self):
        attrs = self.member_attrs.copy()
        # unique username for this test run
        attrs['username'] = 'user_%s' % timezone.now().strftime("%H:%M:%S.%f")
        member = Member.objects.create(**attrs)
        self.assertEqual(NeoProfile.objects.filter(user=member.id).count(), 1)
    
    def test_get_member(self):
        # create member
        attrs = self.member_attrs.copy()
        attrs['username'] = 'user_%s' % timezone.now().strftime("%H:%M:%S.%f")
        Member.objects.create(**attrs)
        # retrieve member from db
        member = Member.objects.all()[0]
        for key, val in self.member_attrs.iteritems():
            self.assertEqual(getattr(member, key), val)
    
    def test_login(self):
        member = Member.objects.all()[0]
        self.client.login(username=member.username, password=member.password)
        self.assertTrue(member.is_authenticated())

    def test_logout(self):
        self.client.logout(username=member.username)
        self.assertFalse(member.is_authenticated())
