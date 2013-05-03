from foundry.forms import JoinForm


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
