Changelog
=========

0.4.5.1 (17-01-2014)
--------------------
#. Increase upper limit on jmbo-foundry version.

0.4.5 (23-10-2013)
------------------
#. Log all API calls. Uses `neo.api` logger.

0.4.4.1 (28-09-2013)
--------------------
#. Add `ModifyFlag` to empty `Answer` element. Invalid otherwise.

0.4.4 (28-09-2013)
------------------
#. Add `answer_set` to `QuestionAnswerWrapper` for adding answers in bulk.

0.4.3 (18-06-2013)
------------------
#. Don't create consumer on member load - issue for views with many members and unmigrated accounts.

0.4.2 (14-06-2013)
------------------
#. Normalize login_alias, removing bad characters and padding it.
#. Add a validation module with validators for email, mobile_number and login_alias - to be expanded.
#. Fix error on `user_logged_out` if there is no authenticated user.

0.4.1 (06-06-2013)
------------------
#. Only clean via Neo if no local errors in join form.

0.4 (23-05-2013)
----------------
#. Use random password for Neo auth instead of actual user password.
#. Only `Member.full_clean` throws ValidationError, not `Member.save` anymore.
#. Remove auth backend and middleware. The user's plain text password isn't stashed in the session or on the `member` object anymore.
#. Add `created` field to `NeoProfile` - useful for checking consumer creation limit (10 000 per day at the moment).
#. Reduce test time by re-using an immutable member where possible.

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
