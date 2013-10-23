# encoding: utf-8
import time
from os import path
from datetime import timedelta
from io import BytesIO
import logging
import requests

from lxml import etree, objectify
from mock import patch

from django.test import TestCase
from django.utils import timezone
from django.core import management
from django.core.cache import cache
from django.conf import settings
from django.http import HttpRequest
from django.utils.importlib import import_module
from django.contrib.auth import login, authenticate
from django.db import connection, transaction, IntegrityError

from foundry.models import Member, Country

from neo.models import NeoProfile, NEO_ATTR, ADDRESS_FIELDS, dataloadtool_export
from neo import api, constants
from neo.xml import AnswerType
from neo.utils import BRAND_ID, PROMO_CODE, ConsumerWrapper, dataloadtool_schema, \
    normalize_username


class _MemberTestCase(object):
    """
    Test helper for member creation.
    """

    @classmethod
    def setUpClass(cls):
        country, created = Country.objects.get_or_create(
            title='United States of America',
            slug='united-states-of-america',
            country_code='US',
        )
        cls.member_attrs = {
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
        cls.session = store
        required_fields_str = ','.join(['first_name', 'last_name', 'dob',
            'email', 'mobile_number', 'country', 'gender', 'city', 'country',
            'province', 'zipcode', 'address'])
        cursor = connection.cursor()
        cursor.execute("DELETE FROM preferences_preferences WHERE EXISTS (SELECT * FROM preferences_registrationpreferences WHERE preferences_ptr_id = id)")
        cursor.execute("DELETE FROM preferences_registrationpreferences")
        cursor.execute("INSERT INTO preferences_preferences (id) VALUES (1)")
        cursor.execute("""INSERT INTO preferences_registrationpreferences (preferences_ptr_id,
            raw_required_fields, raw_display_fields, raw_unique_fields, raw_field_order) VALUES (1, %s, '', '', '{}')""",
            [required_fields_str])
        try:
            cursor.execute("INSERT INTO preferences_preferences_sites (preferences_id, site_id) VALUES (1, 1)")
        except IntegrityError:
            pass
        transaction.commit_unless_managed()

    @classmethod
    def create_member_partial(cls, commit=True):
        attrs = cls.member_attrs.copy()
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

    @classmethod
    def create_member(cls):
        member = cls.create_member_partial(commit=False)
        member.gender = 'F'
        member.save()
        return member

    @classmethod
    def create_member_without_neo(cls):
        from neo.models import original_member_save
        stashed_save = Member.save
        Member.save = original_member_save
        member = cls.create_member()
        Member.save = stashed_save
        return member


class NeoTestCase(_MemberTestCase, TestCase):

    @classmethod
    def setUpClass(cls):
        super(NeoTestCase, cls).setUpClass()
        # create a member for tests that don't change member fields
        cls.immutable_member = cls.create_member()

    def test_create_member(self):
        member = self.create_member()
        self.assertEqual(NeoProfile.objects.filter(user=member.id).count(), 1)

    def test_get_member(self):
        # clear the cached attributes of the newly created member
        cache.clear()
        # retrieve the member from db + Neo
        member2 = Member.objects.get(username=self.immutable_member.username)
        for key in NEO_ATTR.union(ADDRESS_FIELDS):
            self.assertEqual(getattr(self.immutable_member, key), getattr(member2, key))

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
            consumer = api.get_consumer(member.neoprofile.consumer_id, username=member.username, password=member.neoprofile.password)
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
        member = self.immutable_member
        request = HttpRequest()
        request.session = self.session
        request.COOKIES[settings.SESSION_COOKIE_NAME] = self.session.session_key
        member = authenticate(username=member.username, password='password')
        login(request, member)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = self.session.session_key
        self.client.logout()

    def test_authentication(self):
        member = self.immutable_member
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.client.logout()

    def test_neoprofile_password_reset(self):
        member = self.create_member()
        n_pk = member.neoprofile.pk
        member.neoprofile.reset_password('password_new')
        self.assertEqual(api.authenticate(member.neoprofile.login_alias, 'password_new'),
                         member.neoprofile.consumer_id)
        self.assertEqual(NeoProfile.objects.get(pk=n_pk).password, 'password_new')

    def test_member_create_on_complete(self):
        member = self.create_member_partial()
        self.assertFalse(NeoProfile.objects.filter(user=member).exists())
        self.assertTrue(self.client.login(username=member.username, password='password'))
        self.client.logout()
        member.gender = 'F'
        member.save()
        self.assertTrue(NeoProfile.objects.filter(user=member).exists())

    def test_add_promo_code(self):
        '''
        This test can fail due to the new promo code not having propagated in CIDB.
        To solve, one can put time.sleep(2) before get_consumer_profile.
        '''
        member = self.immutable_member
        api.add_promo_code(member.neoprofile.consumer_id, 'added_promo_code',
            username=member.username, password=member.neoprofile.password)
        #time.sleep(5)
        consumer = api.get_consumer_profile(member.neoprofile.consumer_id, username=member.username,
            password=member.neoprofile.password)
        self.assertEqual('added_promo_code', consumer.ConsumerProfile.PromoCode)

    def test_add_consumer_preferences(self):
        '''
        This test can fail due to the new promo code not having propagated in CIDB.
        To solve, one can put time.sleep(2) before get_consumer_preferences.
        '''
        member = self.immutable_member
        cw = ConsumerWrapper()
        cw._set_preference(answer=AnswerType(OptionID=2), category_id=10, question_id=112,
            mod_flag=constants.modify_flag['INSERT'])
        # the promo code for this particular question is mandatory
        cw.consumer.Preferences.PromoCode = 'special_preference_promo'
        api.update_consumer_preferences(member.neoprofile.consumer_id, cw.consumer.Preferences,
            username=member.username, password=member.neoprofile.password, category_id=10)
        #time.sleep(5)
        prefs = api.get_consumer_preferences(member.neoprofile.consumer_id, username=member.username,
            password=member.neoprofile.password, category_id=10)
        self.assertEqual(prefs.PromoCode, 'special_preference_promo')
        question = prefs.QuestionCategory[0].QuestionAnswers[0]
        self.assertEqual(question.QuestionID, 112)
        self.assertEqual(question.Answer[0].OptionID, 2)

    def test_login_alias(self):
        member = self.create_member()
        member.username = "%sx" % member.username
        member.save()
        self.assertTrue(self.client.login(username=member.username, password='password'))
        # check that consumer update works
        member.first_name = "%sx" % member.first_name
        member.save()

    @patch.object(logging.NullHandler, 'handle')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_logging(self, mock_get, mock_post, mock_put, mock_handle):
        # patch requests to avoid hitting the Neo API
        mocked_response = requests.Response()
        mocked_response.status_code = 200
        mocked_response._content = '1'
        mock_get.return_value = mocked_response
        mock_put.return_value = mocked_response
        mocked_response_201 = requests.Response()
        mocked_response_201.status_code = 201
        mocked_response_201.headers['Location'] = "/consumers/1/"

        def mock_post_response(*args, **kwargs):
            if args[0].endswith('registration'):
                return mocked_response
            return mocked_response_201

        mock_post.side_effect = mock_post_response
        # configure and set the logger manually since
        # it's created before the Django settings are parsed
        logging.config.dictConfig(settings.LOGGING)
        api.logger = logging.getLogger('neo.api')
        # should log create_consumer and complete_registration calls
        member = self.create_member()
        self.assertEqual(mock_handle.call_count, 2)
        self.assertIn('create_consumer(consumer=',
                      mock_handle.call_args_list[0][0][0].getMessage())
        self.assertIn("complete_registration(consumer_id='1'",
                      mock_handle.call_args_list[1][0][0].getMessage())
        # should log an update_consumer call
        member.receive_sms = not member.receive_sms
        member.save()
        self.assertEqual(mock_handle.call_count, 3)
        self.assertIn("update_consumer(consumer_id='1', consumer=",
                      mock_handle.call_args_list[2][0][0].getMessage())
        # should log an authenticate call
        self.client.login(username=member.username, password='password')
        self.assertEqual(mock_handle.call_count, 4)
        self.assertIn("authenticate(username=%s, password='***', "
                      % repr(unicode(member.neoprofile.login_alias)),
                      mock_handle.call_args_list[3][0][0].getMessage())
        # should log an error update_consumer call
        mocked_response.status_code = 500
        member.receive_sms = not member.receive_sms
        with self.assertRaises(Exception):
            member.save()
        self.assertEqual(mock_handle.call_count, 5)
        self.assertIn("update_consumer(consumer_id='1', consumer=",
                      mock_handle.call_args_list[4][0][0].getMessage())

    def test_username_normalization(self):
        # username should be lower case, [ +] replaced with '', and padded up to len = 4
        self.assertEqual(normalize_username('+T '), 't000')


class DataLoadToolExportTestCase(_MemberTestCase, TestCase):
    """
    Exporting to the Data Load Tool: `dataloadtool_export()`.
    """

    def setUp(self):
        super(DataLoadToolExportTestCase, self).setUp()
        self.maxDiff = None  # For XML document diffs.
        self.consumers_schema = dataloadtool_schema('Consumers.xsd')
        self.parser = objectify.makeparser(schema=self.consumers_schema)
        self.test_output_path = path.join(path.dirname(__file__), 'test.out')
        self.test_output_credentials_path = path.join(path.dirname(__file__), 'test_alias.out')

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

    def _dataloadtool_export(self, *args, **kwargs):
        """
        Call `dataloadtool_export()` with the supplied additional arguments.

        :return: Validated Consumers `objectify` tree.
        """
        sio = BytesIO()
        sio2 = BytesIO()
        dataloadtool_export(sio, sio2, *args, **kwargs)
        xml = sio.getvalue()
        sio.close()
        self.assertValidates(xml)

        consumers = objectify.fromstring(xml, self.parser)
        return consumers

    def expected_consumer(self, member, password, **kwargs):
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
                    E.Answer(E.OptionID(99), E.ModifyFlag(constants.modify_flag['INSERT']), E.BrandID(BRAND_ID), E.CommunicationChannel(constants.comm_channel['EMAIL'])),
                    E.Answer(E.OptionID(99), E.ModifyFlag(constants.modify_flag['INSERT']), E.BrandID(BRAND_ID), E.CommunicationChannel(constants.comm_channel['SMS'])),
                ),
            ),
        )
        credentials = [E.LoginName(member.username.lower())]
        if password:
            credentials.append(E.Password(password))
        useraccount = E.UserAccount(
            E.LoginCredentials(*credentials),
        )
        return E.Consumer(consumerprofile, preferences, useraccount, **kwargs)

    def expected_consumers(self, members):
        """
        Return an expected Consumers structure for the given members.

        :rtype: `objectify` tree
        """
        from operator import attrgetter
        members.sort(key=attrgetter('username'))

        E = objectify.ElementMaker(annotate=False)
        # The Consumer records must be uniquely numbered to be valid: test that
        # we're numbering them sequentially.
        _consumers = [self.expected_consumer(member, member.neoprofile.password, recordNumber=str(i))
                      for (i, member) in enumerate(members)]
        return E.Consumers(*_consumers)

    def test_dataloadtool_export(self):
        """
        Validate `dataloadtool_export()` against the schema and expected data.
        """
        members = [self.create_member_partial(commit=False), self.create_member_partial(commit=False)]
        members[0].gender = 'F'
        members[1].gender = 'M'
        members[0].save()
        members[1].save()

        consumers = self._dataloadtool_export(Member.objects.filter(pk__in=(members[0].pk, members[1].pk)))
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
        member.save()

        consumers = self._dataloadtool_export(Member.objects.filter(pk=member.pk))
        self.assertEqual(
            objectify.dump(self.expected_consumers([member])),
            objectify.dump(consumers))

    def test_password_callback(self):
        """
        `dataloadtool_export()` should use the password callback.
        """
        # One member with a password, and one without.
        m1 = self.create_member_partial(commit=False)
        m2 = self.create_member_partial(commit=False)
        m1.gender = 'F'
        m2.gender = 'M'
        m1.save()
        m2.save()

        expected = self.expected_consumers([m1, m2])
        expected.Consumer[0].UserAccount.LoginCredentials.Password = 'fnord'
        del expected.Consumer[1].UserAccount.LoginCredentials.Password
        objectify.deannotate(expected, cleanup_namespaces=True)

        def mock_password(given_member):
            # XXX: Unsaved objects compare equal by default, so lookup by id instead.
            passwords = {m1.username: 'fnord', m2.username: None}
            self.assertIn(given_member.username, passwords,
                          'Called with unexpected member: {0!r}'.format(given_member))
            return passwords[given_member.username]

        consumers = self._dataloadtool_export(Member.objects.filter(pk__in=(m1.pk, m2.pk)),
                                              password_callback=mock_password)
        self.assertEqual(
            objectify.dump(expected),
            objectify.dump(consumers))


class DataLoadToolExportCommandTestCase(_MemberTestCase, TestCase):
    """
    Tests the `members_to_cidb_dataloadtool` management command.
    """

    def setUp(self):
        super(DataLoadToolExportCommandTestCase, self).setUp()
        self.command = management.load_command_class('neo', 'members_to_cidb_dataloadtool')
        self.consumers_parser = objectify.makeparser(schema=dataloadtool_schema('Consumers.xsd'))
        self.test_output_path = path.join(path.dirname(__file__), 'test.out')
        self.test_output_credentials_path = path.join(path.dirname(__file__), 'test_alias.out')

    def _call_command(self, *args, **kwargs):
        """
        Call the command, and return standard output.
        """
        sio = open(self.test_output_path, 'w')
        management.call_command('members_to_cidb_dataloadtool', credentials_filepath=self.test_output_credentials_path, stdout=sio, *args, **kwargs)
        return open(self.test_output_path).read()

    def _call_command_validated(self, *args, **kwargs):
        """
        Like `_call_command`, but parse the result into a validated `objectify` tree.
        """
        xml = self._call_command(*args, **kwargs)
        consumers = objectify.fromstring(xml, self.consumers_parser)
        return consumers

    def create_member_named(self, first_name, with_neoprofile=True):
        """
        Create a test member with the given first name.

        :param bool with_neoprofile:
            Whether the member should have an associated `NeoProfile`.
        """
        m = self.create_member_partial(commit=False)
        m.gender = 'F'
        m.first_name = first_name
        if with_neoprofile:
            m.save()
        else:
            from neo.models import original_member_save
            stashed_save = Member.save
            Member.save = original_member_save
            m.save()
            Member.save = stashed_save
        # XXX: This is a bit of a hack, but the best we can do for now.
        if with_neoprofile:
            assert NeoProfile.objects.filter(user=m).exists()  # sanity check
        else:
            try:
                assert bool(m.neoprofile) is False
            except NeoProfile.DoesNotExist:
                pass

    def test_nomembers(self):
        """
        The command should at least run, and produce an empty list of records.
        """
        xml = self._call_command()  # zero Consumer records won't validate
        self.assertEqual(
            objectify.dump(objectify.fromstring(xml)),
            objectify.dump(objectify.E.Consumers()))

    def test_members(self):
        """
        Test with plain members.
        """
        self.create_member_named('foo', with_neoprofile=False)
        self.create_member_named('bar', with_neoprofile=False)
        self.create_member_named('baz', with_neoprofile=False)

        consumers = self._call_command_validated()
        self.assertEqual(
            set(c.ConsumerProfile.FirstName for c in consumers.Consumer),
            set(['foo', 'bar', 'baz']))

    def test_neoprofile_members(self):
        """
        Members with existing `NeoProfile`s should be excluded, unless "--all" is given.
        """
        self.create_member_named('foo', with_neoprofile=False)
        self.create_member_named('bar', with_neoprofile=False)
        self.create_member_named('NEO member', with_neoprofile=True)

        consumers = self._call_command_validated()
        self.assertEqual(
            set(c.ConsumerProfile.FirstName for c in consumers.Consumer),
            set(['foo', 'bar']))

        consumers = self._call_command_validated(all=True)
        self.assertEqual(
            set(c.ConsumerProfile.FirstName for c in consumers.Consumer),
            set(['foo', 'bar', 'NEO member']))

    @staticmethod
    def mock_password_callback(member):
        return 'fnord'

    def test_load_callback(self):
        """
        `load_callback()` works.
        """
        callback = self.command.load_callback('neo.tests:DataLoadToolExportCommandTestCase.mock_password_callback')
        self.assertIs(callback, self.mock_password_callback)

    def test_load_callback_error(self):
        """
        `load_callback()` raises a descriptive user error for bad names.
        """
        examples = [
            ('', 'Provide a password callback in "some.module:some.function" format.'),
            (':', 'Provide a password callback in "some.module:some.function" format.'),
            ('sys:', 'Provide a password callback in "some.module:some.function" format.'),
            (':map', 'Provide a password callback in "some.module:some.function" format.'),
            ('sys:foo', "Failed to look up 'foo' on 'sys': 'module' object has no attribute 'foo'"),
            ('foo:bar', "Failed to import password callback module 'foo': No module named foo"),
            ('os:path', "Provided password callback is not callable: <module .*>"),
        ]
        for (name, message) in examples:
            with self.assertRaisesRegexp(management.CommandError, message):
                self.command.load_callback(name)
