from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_out
from django.db.models import signals
from django.dispatch import receiver

from neo.api import logout as logout_neo


class NeoProfile(models.Model):
    user = models.ForeignKey(User, unique=True)
    # the Neo consumer id used in API requests
    consumer_id = models.PositiveIntegerField(primary_key=True)


@receiver(user_logged_out)
def notify_logout(sender, **kwargs):
    try:
        neo_profile = NeoProfile.objects.get(user=kwargs['user'])
        logout_neo(neo_profile.consumer_id)
    except NeoProfile.DoesNotExist:
        pass # figure out something to do here


# ModifyFlag needs to be set to one of I (insert), U (update) and D (delete) for the following:
# AnswerType
# EmailDetailsType
# AddressDetailsType
# PhoneDetailsType