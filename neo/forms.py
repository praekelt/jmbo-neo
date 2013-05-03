from django.forms.models import construct_instance

from foundry.forms import JoinForm

from neo.models import NeoProfile


'''
Patch the foundry JoinForm
'''
original_joinform_clean = JoinForm.clean
original_joinform_save = JoinForm.save


def clean_join_form(form):
    cleaned_data = original_joinform_clean(form)
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


def save_join_form(form, commit=True):
    instance = original_joinform_save(form, commit)
    if hasattr(form, 'neoprofile'):
        form.neoprofile.user = instance
        form.neoprofile.save()
    return instance


JoinForm.clean = clean_join_form
JoinForm.save = save_join_form


'''
If jmbo-registration is installed, patch that as well
'''
try:
    from jmbo_registration.forms import JoinForm as RegJoinForm

    original_regjoinform_clean = RegJoinForm.clean
    original_regjoinform_save = RegJoinForm.save

    def clean_reg_join_form(form):
        cleaned_data = original_regjoinform_clean(form)
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

    def save_reg_join_form(form, commit=True):
        instance = original_regjoinform_save(form, commit)
        if hasattr(form, 'neoprofile'):
            form.neoprofile.user = instance
            form.neoprofile.save()
        return instance

    RegJoinForm.clean = clean_reg_join_form
    RegJoinForm.save = save_reg_join_form

except ImportError:
    pass
