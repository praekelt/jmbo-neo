import warnings
from StringIO import StringIO

from lxml import etree, objectify

from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out, user_logged_in
from django.db.models import signals
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from django.conf import settings

from preferences import preferences
from foundry.models import Member, DefaultAvatar
from social_auth.db.django_models import UserSocialAuth

from neo import api
from neo.utils import ConsumerWrapper
from neo.constants import modify_flag


class NeoProfile(models.Model):
    user = models.OneToOneField(User)
    # the Neo consumer id used in API requests
    consumer_id = models.PositiveIntegerField(primary_key=True)
    '''
    The login_alias is for the benefit of exporting existing users with
    usernames that clash without case-sensitivity. If a site was launched
    with Neo integration, user.username = login_alias for all members.
    '''
    login_alias = models.CharField(max_length=50, unique=True)

    def save(self, *args, **kwargs):
        if not self.login_alias:
            '''
            Always store login_alias in lowercase to be able to enforce uniqueness.
            '''
            self.login_alias = self.user.username.lower()
        super(NeoProfile, self).save(*args, **kwargs)


'''
The member attributes that are stored on Neo and in memcached
NB. These attributes must be required during registration for any Neo app
NB. Password is a special case and is handled separately
NB. Address, city and province are also special cases
'''
NEO_ATTR = frozenset((
    'first_name', 'last_name', 'dob',
    'email', 'mobile_number', 'receive_sms',
    'receive_email', 'country', 'gender'))

# These fields are used together to create an address and don't exist as individual neo attributes
ADDRESS_FIELDS = frozenset(('city', 'country', 'province', 'zipcode', 'address'))

# These fields correspond to the available login fields in jmbo-foundry
JMBO_REQUIRED_FIELDS = frozenset(('username', 'mobile_number', 'email'))

USE_MCAL = settings.NEO.get('USE_MCAL', False)


def notify_logout(sender, **kwargs):
    try:
        neo_profile = kwargs['user'].neoprofile
        api.logout(neo_profile.consumer_id)
    except NeoProfile.DoesNotExist:
        pass  # figure out something to do here


def neo_login(sender, **kwargs):
    try:
        user = kwargs['user']
        if user.has_usable_password():  # for normal members
            kwargs['request'].session['raw_password'] = user.raw_password
        else:  # members signed up via Facebook/other
            social = user.social_auth.all()[:1]
            if social:
                kwargs['request'].session['raw_password'] = social[0].uid
                user.raw_password = social[0].uid
            else:
                raise UserSocialAuth.DoesNotExist
        # check that neo profile exists - throws DoesNotExist if there is no profile
        user.neoprofile
        # Authenticate via Neo in addition to Django
        api.authenticate(user.neoprofile.login_alias, user.raw_password)
    except NeoProfile.DoesNotExist:
        try:
            user.save()
        except ValidationError, e:
            warnings.warn("Consumer could not be created via Neo - %s" % str(e))
    except AttributeError:
        warnings.warn("User was not logged in via Neo - raw password not available")
    except UserSocialAuth:
        warnings.warn("User was not logged in via Neo - the user does not have a usable password or social authentication id.")

user_logged_in.connect(neo_login)
user_logged_out.connect(notify_logout)


def stash_neo_fields(member, clear=False):
    stashed_fields = {}
    '''
    Stash the neo fields that aren't required and clear
    them on the instance so that they aren't saved to db
    '''
    for key in (NEO_ATTR.union(ADDRESS_FIELDS)).difference(JMBO_REQUIRED_FIELDS):
        stashed_fields[key] = getattr(member, key)
        '''
        If field can be null, set to None. Otherwise assign
        a default value. If a default value has not been
        specified, assign the default of the python type
        '''
        field = Member._meta.get_field_by_name(key)[0]
        if clear:
            if field.null:
                setattr(member, key, None)
            elif field.default != models.fields.NOT_PROVIDED:
                setattr(member, key, field.default)
            else:
                setattr(member, key, type(stashed_fields[key])())
    return stashed_fields


def wrap_member(member, login_alias=None):
    """
    Return a `ConsumerWrapper` reflecting the given `Member`.
    """
    wrapper = ConsumerWrapper()
    for a in NEO_ATTR:
        getattr(wrapper, "set_%s" % a)(getattr(member, a))
    # Use a login_alias instead if specified
    # member.username.lower() is not guaranteed to be unique
    if login_alias:
        wrapper.set_username(login_alias)
    else:
        wrapper.set_username(member.username.lower())
    # A raw_password is not always set (for example, when exporting members
    # from the command line).
    if getattr(member, 'raw_password', None):
        wrapper.set_password(member.raw_password)

    # assign address
    has_address = False
    for k in ADDRESS_FIELDS:
        if getattr(member, k, None):
            has_address = True
            break
    if has_address:
        wrapper.set_address(member.address, member.city,
            member.province, member.zipcode, member.country)

    return wrapper


def create_consumer(member):
    wrapper = wrap_member(member)
    consumer_id, uri = api.create_consumer(wrapper.consumer)
    api.complete_registration(consumer_id)  # activates the account
    return consumer_id


def update_consumer(member):
    consumer_id = member.neoprofile.consumer_id
    # update changed attributes
    old_member = cache.get('neo_consumer_%s' % member.pk, None)
    wrapper = ConsumerWrapper()
    if old_member is not None:  # it should never be None
        for k in NEO_ATTR:
            # check where cached version and current version of member differ
            current = getattr(member, k, None)
            old = old_member.get(k, None)
            if current != old:
                # update attribute on Neo
                if old is None:
                    getattr(wrapper, "set_%s" % k)(current, mod_flag=modify_flag['INSERT'])
                elif current is None:
                    getattr(wrapper, "set_%s" % k)(old, mod_flag=modify_flag['DELETE'])
                else:
                    getattr(wrapper, "set_%s" % k)(current, mod_flag=modify_flag['UPDATE'])

        # check if address needs to change
        has_address = False
        had_address = False
        address_changed = False
        for k in ADDRESS_FIELDS:
            current = getattr(member, k, None)
            old = old_member.get(k, None)
            if current:
                has_address = True
            if old:
                had_address = True
            if current != old:
                address_changed = True
        # update address accordingly
        if address_changed:
            if not has_address:
                wrapper.set_address(old_member.address, old_member.city,
                    old_member.province, old_member.zipcode, old_member.country,
                    modify_flag['DELETE'])
            elif not had_address:
                wrapper.set_address(member.address, member.city,
                    member.province, member.zipcode, member.country)
            else:
                wrapper.set_address(member.address, member.city,
                    member.province, member.zipcode, member.country,
                    mod_flag=modify_flag['UPDATE'])

    if not wrapper.is_empty:
        if not wrapper.profile_is_empty:
            wrapper.set_ids_for_profile(api.get_consumer_profile(consumer_id, username=member.neoprofile.login_alias,
                password=member.raw_password))
        api.update_consumer(consumer_id, wrapper.consumer, username=member.neoprofile.login_alias, password=member.raw_password)

    # check if password needs to be changed
    if hasattr(member, 'raw_password'):
        if hasattr(member, 'old_password'):
            api.change_password(member.neoprofile.login_alias, member.raw_password, old_password=member.old_password)
        elif hasattr(member, 'forgot_password_token'):
            api.change_password(member.neoprofile.login_alias, member.raw_password, token=member.forgot_password_token)
    return consumer_id


def clean_member(member):
    super(Member, member).full_clean(called_from_child=True)
    # only create/update consumer if the member is complete
    if member.is_profile_complete and hasattr(member, 'raw_password'):
        # attempt to store the data on Neo in order to validate it
        try:
            has_neoprofile = bool(member.neoprofile)
        except NeoProfile.DoesNotExist:
            has_neoprofile = False

        if member.pk and has_neoprofile:
            consumer_id = update_consumer(member)
        else:
            consumer_id = create_consumer(member)
            if member.pk:
                # the member had already been logged in by the join form - do the same via Neo
                consumer_id = api.authenticate(member.username, member.raw_password)
        member.consumer_id = consumer_id
    member.need_to_clean_member = False


def save_member(member, *args, **kwargs):
    '''
    NB: Keep this in sync with changes to foundry.models.Member
    '''
    # START - copied from foundry
    member.is_profile_complete = True
    required_fields = preferences.RegistrationPreferences.required_fields
    for name in required_fields:
        if not getattr(member, name, None):
            member.is_profile_complete = False
            break
    # END

    if getattr(member, 'need_to_clean_member', True):
        member.full_clean()
        member.need_to_clean_member = True

    stash_fields = hasattr(member, 'consumer_id')
    clear_fields = not USE_MCAL
    if stash_fields:
        # stash fields, clearing them if we are not using MCAL, and reassign them after save
        stashed_fields = stash_neo_fields(member, clear=clear_fields)

    super(Member, member).save(*args, **kwargs)

    if stash_fields:
        if clear_fields:
            for key, val in stashed_fields.iteritems():
                setattr(member, key, val)
        stashed_fields.update(dict((k, getattr(member, k)) for k in JMBO_REQUIRED_FIELDS))
        # cache the member fields after successfully creating/updating
        cache.set('neo_consumer_%s' % member.pk, stashed_fields, 1200)

    # no consumer on Neo yet
    if hasattr(member, 'consumer_id'):
        NeoProfile.objects.get_or_create(user=member, consumer_id=member.consumer_id)

    # START - copied from foundry
    if not member.image:
        # Set a default avatar
        avatars = DefaultAvatar.objects.all().order_by('?')
        if avatars.exists():
            member.image = avatars[0].image
    # END


def clean_user(user, called_from_child=False):
    super(User, user).full_clean()
    try:
        if not called_from_child and user.neoprofile:
            # check if password needs to be changed
            if hasattr(user, 'raw_password'):
                if hasattr(user, 'old_password'):
                    api.change_password(user.neoprofile.login_alias, user.raw_password, old_password=user.old_password)
                elif hasattr(user, 'forgot_password_token'):
                    api.change_password(user.neoprofile.login_alias, user.raw_password, token=user.forgot_password_token)
    except NeoProfile.DoesNotExist:
        pass

    user.need_to_clean_user = False


def save_user(user, *args, **kwargs):
    try:
        if not isinstance(user, Member) and user.neoprofile:
            if getattr(user, 'need_to_clean_user', True):
                user.full_clean()
                user.need_to_clean_user = True
    except NeoProfile.DoesNotExist:
        pass

    super(User, user).save(*args, **kwargs)


def load_consumer(sender, *args, **kwargs):
    instance = kwargs['instance']
    # if the object being instantiated has a pk, i.e. has been saved to the db
    if instance.id:
        pk = instance.id
        cache_key = 'neo_consumer_%s' % pk
        member = cache.get(cache_key, None)
        try:
            if member is None:
                if USE_MCAL:
                    member = dict((k, getattr(instance, k)) for k in NEO_ATTR.union(ADDRESS_FIELDS))
                else:
                    consumer_id = instance.neoprofile.consumer_id
                    # retrieve consumer from Neo
                    consumer = api.get_consumer(consumer_id)
                    wrapper = ConsumerWrapper(consumer=consumer)
                    member = dict((k, getattr(wrapper, k)) for k in NEO_ATTR)
                    member.update(wrapper.address)  # special case
                    # update instance with Neo attributes
                    for key, val in member.iteritems():
                        setattr(instance, key, val)

                # cache the neo member dictionary
                cache.set(cache_key, member, 1200)

        except NeoProfile.DoesNotExist:
            pass
signals.post_init.connect(load_consumer, sender=Member)


def set_password(user, raw_password, old_password=None):
    '''
    Store the clear text password on a user, thus making
    it accessible by Neo.
    '''
    try:
        if user.neoprofile and old_password:
            user.old_password = old_password
    except NeoProfile.DoesNotExist:
        pass
    user.raw_password = raw_password
    user.password = make_password(raw_password)


def dataloadtool_export(output, output_login_alias, members, password_callback=None, pretty_print=False):
    """
    Export the given members as XML input for the CIDB Data Load Tool.

    :param output: File-like object to write to.
    :param members: Queryset of members to export. If this is a large queryset,
        consider using `iterator()` on it, to avoid excessive caching.

    :param password_callback:
        If supplied, use this function to set or generate new passwords as part
        of the export. This can be used, for example, to port member passwords
        from another source into CIDB.

        The function will be passed each `Member` in turn, and should return
        either a new (raw, unhashed) password, or `None`, to not include a
        password in the export. (To preserve what the default exported password
        would be, the function can explicitly return the member's
        `raw_password`, if it is set.)
    """
    # XXX: We take advantage of the existing ConsumerWrapper logic to construct
    # a GeneratedsSuper instance, which we then convert to lxml for further
    # manipulation. Once ConsumerWrapper (or its replacement) can give us a
    # lxml tree directly, we can skip this step.
    def etree_from_gds(gds):
        sio = StringIO()
        gds.export(sio, 0, pretty_print=False)
        return etree.fromstring(sio.getvalue())
    password_path = objectify.ObjectPath('Consumer.UserAccount.LoginCredentials.Password')

    output.write('<Consumers>\n')
    last_username = ''
    import time
    # Important: The iterator() call prevents memory usage from growing out
    # of control, when exporting many members. Don't remove it accidentally.
    for (i, member) in enumerate(members.select_related('neoprofile').order_by('username').iterator()):
        # Resolve duplicate usernames, or use available login_alias
        try:
            wrapper = wrap_member(member, login_alias=member.neoprofile.login_alias)
        except (NeoProfile.DoesNotExist, AttributeError):
            if member.username.lower() == last_username:
                # append part of timestamp to username to make it unique
                timestamp = str(int(time.time() * 1000000))[-10:]
                login_alias = "%s%s" % (member.username, timestamp)
                wrapper = wrap_member(member, login_alias=login_alias)
                # write aliases to file
                output_login_alias.write('"%s","%s"\n' % (member.username, login_alias))
            else:
                wrapper = wrap_member(member)
        last_username = member.username.lower()

        elem = etree_from_gds(wrapper.consumer)
        elem.attrib['recordNumber'] = str(i)

        if password_callback is not None:
            new_password = password_callback(member)
            if new_password is not None:
                # Set (or replace) the password.
                password_path.setattr(elem, new_password)
                objectify.deannotate(password_path(elem), cleanup_namespaces=True)
            elif password_path.hasattr(elem):
                # Clear the existing password element, if one exists.
                old_password = password_path(elem)
                old_password.getparent().remove(old_password)

        output.write(etree.tostring(elem, pretty_print=pretty_print))
        output.write('\n')
    output.write('</Consumers>\n')


'''
Patch User and Member
'''
User.set_password = set_password
User.save = save_user
User.full_clean = clean_user
Member.save = save_member
Member.full_clean = clean_member
