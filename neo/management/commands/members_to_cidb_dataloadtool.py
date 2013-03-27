from optparse import make_option
from textwrap import dedent

from django.core.management.base import NoArgsCommand

from neo.models import Member, dataloadtool_export


class Command(NoArgsCommand):
    help = dedent("""\
        Export members as XML for the CIDB Data Load Tool.

        By default, only members without existing NeoProfiles are exported.""")

    option_list = list(NoArgsCommand.option_list) + [
        make_option('-f', '--file', dest='file', help='Output file (default: standard output)'),
        make_option('-p', '--pretty-print', dest='pretty_print', action='store_true', default=False,
                    help='Enable pretty-printing.'),
        make_option('-a', '--all', dest='pretty_print', action='store_true', default=False,
                    help='Export all members, including those with existing NeoProfiles.'),
    ]

    def handle_noargs(self, filename=None, pretty_print=False, all=False, **options):
        output = self.stdout if filename is None else open(filename)
        members = self.get_members(include_all=all)

        dataloadtool_export(output, members, pretty_print=pretty_print)

    def get_members(self, include_all=False):
        """
        Return the members to export.
        """
        qs = Member.objects.all() if include_all else Member.objects.filter(neoprofile__isnull=True)
        # Important: The iterator() call prevents memory usage from growing out
        # of control, when exporting many members. Don't remove it accidentally.
        return qs.iterator()
