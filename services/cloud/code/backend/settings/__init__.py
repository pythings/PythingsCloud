
# Import common settings
from backend.settings.common import *

# Apps setttings auto discovery

from backend.common.utils import discover_apps


for app in discover_apps('backend', only_names=True):

    # Check if we have the populate:
    settings_file = 'backend/{}/settings.py'.format(app)
    if os.path.isfile(settings_file):
        
        app_settings_module = 'backend.{}.settings'.format(app)

        # A bit triky but should be fine...
        exec('from {} import *'.format(app_settings_module))
