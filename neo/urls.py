from django.conf.urls.defaults import patterns, url, include

from foundry import forms

from neo.utils import NeoTokenGenerator, NeoPasswordChangeForm


neo_token_generator = NeoTokenGenerator()

urlpatterns = patterns('',
    # Password reset with foundry form and Neo token generator
    url(
        r'^password_reset/$', 
        'django.contrib.auth.views.password_reset', 
        {
            'password_reset_form': forms.PasswordResetForm,
            'token_generator': neo_token_generator,
        },
        name='password_reset',
    ),
    # Password reset with foundry form
    url(
        r'^password_reset_confirm/$', 
        'django.contrib.auth.views.password_reset_confirm', 
        {
            'token_generator': neo_token_generator,
        },
        name='password_reset',
    ),
    url(
        r'^password_change/$',
        'django.contrib.auth.views.password_change',
        {
            'password_change_form': NeoPasswordChangeForm,
        },
        name='password_change',
    ),
    url(
        r'^password_change/done/$',
        'django.contrib.auth.views.password_change_done',
        name='password_change_done'
    ),
)
