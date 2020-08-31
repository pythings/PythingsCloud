
# Settings that you put here will be included in the Django settings.

from backend.settings.common import INSTALLED_APPS
INSTALLED_APPS = INSTALLED_APPS + (
    'rest_framework',
)
