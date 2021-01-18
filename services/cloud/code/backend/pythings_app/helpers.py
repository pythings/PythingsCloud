import calendar
import time
import uuid
import logging

# Backend imports
from .models import App, Settings, Pool, File, MessageCounter, WorkerMessage, ManagementMessage, Commit, Thing, Profile

# Setup logging
logger = logging.getLogger(__name__)


#=========================
#  Create App
#=========================

default_worker_code = '''
import random

class WorkerTask(object):

    def __init__(self):
        logger.debug('Initializing App worker task')
        self.prev_value = 21

    def call(self):
        \'\'\'This function gets called every "worker interval" seconds\'\'\'

        logger.debug('Called App worker task')

        # Generate a demo random temperature reading
        value = self.prev_value + random.randint(-1, 1)
        self.prev_value = value
        
        # Uncomment the following two lines, then save and commit to 
        # see the demo temperature readings on your Thing Dashboard.

        #data = {'temperature': value}
        #return data

'''

default_management_code = '''
class ManagementTask(object):

    def __init__(self):
        logger.debug('Initializing App management task')

    def call(self, data):
        \'\'\'This function gets called every "management interval" seconds\'\'\'

        logger.debug('Called App management task with data {}', data)
        
        return 'Got "{}"'.format(data)

'''

empty_worker_code = '''
class WorkerTask(object):

    def call(self):
        pass

'''

empty_management_code = '''
class ManagementTask(object):

    def call(self, data):
        pass

'''


def create_app(name,user,aid=None, management_interval='60', worker_interval='300', pythings_version='factory', empty_app=False, use_latest_app_version=False):
    '''Create the app with default pools, settings and code'''
    
    # TODO: this must be a single transaction.
    
    if aid is None:
        aid=str(uuid.uuid4())

    # TODO: Check if app with this AID exists, and if so raise
     
    # Create the app
    app = App.objects.create(aid=aid, name=name, user=user)

    # Create the pools with default settings.
    
    epoch_now            = int(calendar.timegm(time.gmtime())) 
    app_version          =  str(epoch_now)

    if not empty_app:
        # Create production settings and pool 
        settings = Settings.objects.create(pythings_version     = pythings_version,
                                           app_version          = app_version,
                                           worker_interval      = worker_interval,
                                           management_interval  = management_interval)
        _ = Pool.objects.create(name='production', app=app, settings=settings, production=True, use_latest_app_version=False)
        
            
        # Create staging settings and and pool
        settings = Settings.objects.create(pythings_version     = pythings_version,
                                           app_version          = app_version,
                                           worker_interval      = worker_interval,
                                           management_interval  = management_interval)
        _ = Pool.objects.create(name='staging', app=app, settings=settings, staging=True, use_latest_app_version=use_latest_app_version)    
    
        # Create development settings and pool
        settings = Settings.objects.create(pythings_version     = pythings_version,
                                           app_version          = app_version,
                                           worker_interval      = worker_interval,
                                           management_interval  = management_interval)
        default_pool = Pool.objects.create(name='development', app=app, settings=settings, development=True, use_latest_app_version=use_latest_app_version)
    
    else:
        # Create unbound settings and pool
        settings = Settings.objects.create(pythings_version     = pythings_version,
                                           app_version          = app_version,
                                           worker_interval      = worker_interval,
                                           management_interval  = management_interval)
        default_pool = Pool.objects.create(name='unbound', app=app, settings=settings, development=True, use_latest_app_version=True)

    # Set app's default pool and hidden attributes
    app.default_pool = default_pool
    if empty_app:
        app.hidden = True
    app.save()

    # Create empty app skeleton
    file1 = File.objects.create(name = 'worker_task.py',
                                content = default_worker_code if not empty_app else empty_worker_code,
                                app = app,
                                committed = True)

    file2 = File.objects.create(name = 'management_task.py',
                                content = default_management_code if not empty_app else empty_management_code,
                                app = app,
                                committed = True)  

    #File.objects.create(name    = 'new_file.py',
    #                    content = '\n#Empty sample uncomitted file\n\n\n\n\n\n',
    #                    app = app)  
    
    # Create first commit
    #commit = Commit.objects.create(app=app, cid=str(epoch_now), tag='v0.0')
    commit = Commit.objects.create(app=app, cid=str(epoch_now))
    commit.files.add(file1)
    commit.files.add(file2)
    commit.valid=True
    commit.save()
    
    return app


def create_none_app(user):
    create_app(name='NoneApp', user=user, aid='00000000-0000-0000-0000-000000000000',
               management_interval='5', worker_interval='300', pythings_version='factory',
               empty_app=True)


def settings_to_dict(settings):
    
    settings_dict = {'pythings_version': settings.pythings_version,
                     'app_version': settings.app_version,
                     'management_interval': settings.management_interval,
                     #'management_sync': settings.management_sync,
                     'worker_interval': settings.worker_interval,
                     #'worker_sync': settings.worker_sync,
                     'battery_operated': settings.battery_operated,
                     'setup_timeout': settings.setup_timeout,
                     'ssl': settings.ssl,
                     'payload_encryption': settings.payload_encryption}
        
    if settings.backend:
        settings_dict['backend'] = settings.backend

    return settings_dict


def get_total_messages(user):
    try:
        message_counter = MessageCounter.objects.get(user=user)
    except MessageCounter.DoesNotExist:
        MessageCounter.objects.create(user=user)
        message_counter = MessageCounter.objects.get(user=user)
    return [message_counter.total, message_counter.worker, message_counter.management]


def get_total_devices(user):
    user_apps = App.objects.filter(user=user)
    total_devices = 0
    for app in user_apps:
        total_devices += Thing.objects.filter(app=app).count()
    return  total_devices           


def inc_total_messages(user, worker=0, management=0):
    if not worker and not management:
        return
    try:
        message_counter = MessageCounter.objects.get(user=user)
    except MessageCounter.DoesNotExist:    
        MessageCounter.objects.create(user=user)
        message_counter = MessageCounter.objects.get(user=user)
    if worker:
        message_counter.worker += worker
        message_counter.total  += worker
    if management:
        message_counter.management += management
        message_counter.total  += management
    message_counter.save()


def get_timezone_from_request(request):
    return request.user.profile.timezone

