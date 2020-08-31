from django import template
from django.conf import settings

register = template.Library()

ALLOWABLE_VALUES = ('MAIN_DOMAIN_NAME', 'WEBSETUP_DOMAIN_NAME', 'FAVICONS_PATH', 'LOGO_FILE', 'CONTACT_EMAIL')

@register.simple_tag
def settings_value(name):
    if name in ALLOWABLE_VALUES:
        return getattr(settings, name, '')
    return ''
