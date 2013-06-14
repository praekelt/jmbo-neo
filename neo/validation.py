from django.core.validators import RegexValidator, validate_email
from django.core.exceptions import ValidationError


def validate(fieldname, value):
    validator_name = 'validate_%s' % fieldname
    if validator_name in globals():
        globals()[validator_name](value)


validate_mobile_number = RegexValidator(regex=r'^[\+]?[0-9]*$')
validate_login_alias = RegexValidator(regex=r'[^ +A-Z]{4,}')
