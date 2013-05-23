import os
from os import path
from functools import reduce
from optparse import make_option
from textwrap import dedent

from django.core.management.base import NoArgsCommand, CommandError
from django.utils import importlib

from neo.models import Member, dataloadtool_export


class Command(NoArgsCommand):
    help = dedent("""\
        Export members as XML for the CIDB Data Load Tool.

        By default, only members without existing NeoProfiles are exported.

        Usage: members_to_cidb_dataloadtool credentials_filepath [options]""")

    option_list = list(NoArgsCommand.option_list) + [
        make_option('-f', '--file', dest='filepath', help='Output file (default: standard output)', metavar='FILE'),
        make_option('-p', '--pretty-print', dest='pretty_print', action='store_true', default=False,
                    help='Enable pretty-printing.'),
        make_option('-a', '--all', dest='pretty_print', action='store_true', default=False,
                    help='Export all members, including those with existing NeoProfiles.'),
        make_option('--password-callback', dest='password_callback',
                    help='Provide a password-setting callback, in "some.module:some.function" format.'),
    ]

    def handle(self, credentials_filepath, filepath=None, pretty_print=False, all=False, password_callback=None, **options):
        for p in (credentials_filepath, filepath):
            if p:
                if not path.isabs(p):
                    p = path.join(os.getenv('PWD'), p)
                if not path.isdir(path.dirname(p)):
                    raise Exception("Output directory %s does not exist." % p)
                elif not os.access(path.dirname(p), os.W_OK):
                    raise Exception("Output directory %s does not have write access." % p)

        members = self.get_members(include_all=all)
        callback = None if password_callback is None else self.load_callback(password_callback)

        with open(filepath, 'w') if filepath else self.stdout as output:
            with open(credentials_filepath, 'w') as credentials_output:
                dataloadtool_export(output, credentials_output, members,
                                    password_callback=callback, pretty_print=pretty_print)

    def load_callback(self, password_callback):
        """
        Load the named callback, or raise an appropriate CommandError.
        """
        (module_name, sep, callback_name) = password_callback.partition(':')

        if not (module_name and callback_name):
            raise CommandError('Provide a password callback in "some.module:some.function" format.')

        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise CommandError('Failed to import password callback module {0!r}: {1}'.format(module_name, e))

        attrs = callback_name.split('.')
        try:
            callback = reduce(getattr, attrs, module)
        except AttributeError as e:
            raise CommandError('Failed to look up {0!r} on {1!r}: {2}'.format(callback_name, module_name, e))

        if not callable(callback):
            raise CommandError('Provided password callback is not callable: {0!r}'.format(callback))
        return callback

    def get_members(self, include_all=False):
        """
        Return the members to export.
        """
        return Member.objects.all() if include_all else Member.objects.filter(neoprofile__isnull=True)
