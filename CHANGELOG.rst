Changelog
=========

0.3 (03-05-2013)
----------------
#. Add a new management command to export members for bulk upload:
   ``members_to_cidb_dataloadtool``
#. Automatically create consumers on CIDB for members on login.
#. Consumer creation deferred until a member is complete according to `RegistrationPreferences.required_fields`.
#. Consumer fields are kept in sync with member fields over MCAL.
#. Use `login_alias` instead of `Member.username` for CIDB communications. 

0.2 (09-11-2012)
----------------
#. Create member if credentials are valid and the member does not exist.
#. Fix bug in logout.

0.1 (18-10-2012)
----------------
#. Initial release
