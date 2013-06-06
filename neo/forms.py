from functools import wraps

from django.forms.models import construct_instance

from foundry.forms import JoinForm

from neo.models import NeoProfile


def patch_join_clean(original_clean):

    @wraps(original_clean)
    def clean_join_form(form):
        cleaned_data = original_clean(form)
        if not form._errors and not form.non_field_errors():
            opts = form._meta
            # Update the model instance with cleaned_data.
            member = construct_instance(form, form.instance, opts.fields, opts.exclude)
            member.set_password(form.cleaned_data["password1"])
            member.full_clean()
            try:
                form.neoprofile = member.neoprofile
            except NeoProfile.DoesNotExist:
                pass
        return cleaned_data

    return clean_join_form


def patch_join_save(original_save):

    @wraps(original_save)
    def save_join_form(form, commit=True):
        instance = original_save(form, commit)
        if hasattr(form, 'neoprofile') and form.neoprofile:
            form.neoprofile.user = instance
            form.neoprofile.save()
        return instance

    return save_join_form


JoinForm.clean = patch_join_clean(JoinForm.clean)
JoinForm.save = patch_join_save(JoinForm.save)
try:
    from jmbo_registration.forms import JoinForm as RegJoinForm
    RegJoinForm.clean = patch_join_clean(RegJoinForm.clean)
    RegJoinForm.save = patch_join_save(RegJoinForm.save)
except ImportError:
    pass
