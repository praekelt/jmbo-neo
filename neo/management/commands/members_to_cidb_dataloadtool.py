import sys
from optparse import make_option

from django.core.management.base import NoArgsCommand, CommandError

from neo.models import Member, dataloadtool_export


class Command(NoArgsCommand):
    help = 'Export members as XML for the CIDB Data Load Tool.'

    option_list = list(NoArgsCommand.option_list) + [
        make_option('-f', '--file', dest='file', help='Output file (default: standard output)'),
        make_option('-p', '--pretty-print', dest='pretty_print', action='store_true', default=False,
                    help='Enable pretty-printing.'),
    ]

    def handle_noargs(self, filename=None, pretty_print=False, **options):
        output = sys.stdout if filename is None else open(filename)
        members = self.get_members()

        dataloadtool_export(output, members, pretty_print=pretty_print)

    def get_members(self):
        """
        Return the members to export.
        """
        # Important: The iterator() call prevents memory usage from growing out
        # of control, when exporting many members. Don't remove it accidentally.
        return Member.objects.all().iterator()
