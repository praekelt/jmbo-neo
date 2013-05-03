from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.forms import PasswordChangeForm

from foundry.forms import JoinForm

from neo import api
from neo.models import NeoProfile


class NeoTokenGenerator(PasswordResetTokenGenerator):
    '''
    A token generator to be used in password_reset and password_reset_confirm
    forms - the token can then be used to change the user's password locally
    and on Neo
    '''
    def make_token(self, user):
        try:
            return api.get_forgot_password_token(user.neoprofile.login_alias).TempToken
        except NeoProfile.DoesNotExist:
            return super(NeoTokenGenerator, self).make_token(user)

    def check_token(self, user, token):
        try:
            user.neoprofile
            user.forgot_password_token = token
            return True
        except NeoProfile.DoesNotExist:
            return super(NeoTokenGenerator, self).check_token(user, token)


class NeoPasswordChangeForm(PasswordChangeForm):
    '''
    Overrides the Django password change form so that the the old password
    is stored in clear text on the user object, thus making it accessible
    to Neo
    '''
    def clean_new_password1(self):
        new = self.cleaned_data['new_password1']
        self.user.set_password(new, old_password=self.cleaned_data['old_password'])
        self.user.full_clean()
        return new

    def save(self, commit=True):
        if commit:
            self.user.save()
        return self.user


'''
Patch the foundry JoinForm
'''


def clean_join_form(form):
    from foundry.forms import JoinForm
    from django.forms.models import construct_instance
    cleaned_data = super(JoinForm, form).clean()
    opts = form._meta
    # Update the model instance with cleaned_data.
    member = construct_instance(form, form.instance, opts.fields, opts.exclude)
    member.set_password(form.cleaned_data["password1"])
    member.full_clean()
    return cleaned_data


def save_join_form(form, commit=True):
    if commit:
        form.instance.save()
    return form.instance

JoinForm.clean = clean_join_form
JoinForm.save = save_join_form
