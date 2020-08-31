import os
import hashlib
import calendar
import time
import uuid
import pytz
import traceback
import random
import logging
import subprocess
import datetime
from collections import namedtuple
try:
    from dateutil.tz import tzoffset
except ImportError:
    tzoffset = None

# Backend imports
from .models import App, Settings, Pool, File, MessageCounter, WorkerMessage, ManagementMessage, Commit, Thing, Profile

# Setup logging
logger = logging.getLogger(__name__)

# OS versions available
OS_VERSIONS = ['v1.0.0-rc3', 'v1.0.0', 'v1.1.0', 'factory']
OS_VERSIONS.reverse()


#=========================
#  Utilities
#=========================

def random_string():
    return ''.join(random.choice('abcdefghilmnopqrtuvz') for _ in range(16))


def log_user_activity(level, msg, request):

    # Get the caller funcition name trought inspect with some logic
    import inspect
    caller =  inspect.stack()[1][3]
    if caller == "post":
        caller =  inspect.stack()[2][3]
    
    try:
        msg = str(caller) + " view - USER " + str(request.user.email) + ": " + str(msg)
    except AttributeError:
        msg = str(caller) + " view - USER UNKNOWN: " + str(msg)

    try:
        level = getattr(logging, level)
    except:
        raise
    
    logger.log(level, msg)


def format_exception(e):
    return 'Exception: ' + str(e) + '; Traceback: ' + traceback.format_exc().replace('\n','|')

def get_timezone(request):
    profile = Profile.objects.get(user=request.user)
    return profile.timezone

def sanitize_shell_encoding(text):
    return text.encode("utf-8", errors="ignore")

def format_shell_error(stdout, stderr, exit_code):
    
    string  = '\n#---------------------------------'
    string += '\n# Shell exited with exit code {}'.format(exit_code)
    string += '\n#---------------------------------\n'
    string += '\nStandard output: "'
    string += sanitize_shell_encoding(stdout)
    string += '"\n\nStandard error: "'
    string += sanitize_shell_encoding(stderr) +'"\n\n'
    string += '#---------------------------------\n'
    string += '# End Shell output\n'
    string += '#---------------------------------\n'

    return string

def os_shell(command, capture=False, verbose=False, interactive=False, silent=False):
    '''Execute a command in the os_shell. By default prints everything. If the capture switch is set,
    then it returns a namedtuple with stdout, stderr, and exit code.'''
    
    if capture and verbose:
        raise Exception('You cannot ask at the same time for capture and verbose, sorry')

    # Log command
    logger.debug('Shell executing command: "%s"', command)

    # Execute command in interactive mode    
    if verbose or interactive:
        exit_code = subprocess.call(command, shell=True)
        if exit_code == 0:
            return True
        else:
            return False

    # Execute command getting stdout and stderr
    # http://www.saltycrane.com/blog/2008/09/how-get-stdout-and-stderr-using-python-subprocess-module/
    
    process          = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (stdout, stderr) = process.communicate()
    exit_code        = process.wait()

    # Convert to str (Python 3)
    stdout = stdout.decode(encoding='UTF-8')
    stderr = stderr.decode(encoding='UTF-8')

    # Formatting..
    stdout = stdout[:-1] if (stdout and stdout[-1] == '\n') else stdout
    stderr = stderr[:-1] if (stderr and stderr[-1] == '\n') else stderr

    # Output namedtuple
    Output = namedtuple('Output', 'stdout stderr exit_code')

    if exit_code != 0:
        if capture:
            return Output(stdout, stderr, exit_code)
        else:
            print(format_shell_error(stdout, stderr, exit_code))      
            return False    
    else:
        if capture:
            return Output(stdout, stderr, exit_code)
        elif not silent:
            # Just print stdout and stderr cleanly
            print(stdout)
            print(stderr)
            return True
        else:
            return True


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

        logger.debug('Called App worker task')

        # Generate a demo random temperature reading
        value = self.prev_value + random.randint(-1, 1)
        self.prev_value = value
        
        # Uncomment the following two lines, then save and commit to 
        # see the demo temperature readings on your Thing Dashboard.

        #data = {'temperature_C': value}
        #return data

'''

default_management_code = '''
class ManagementTask(object):

    def __init__(self):
        logger.debug('Initializing App management task')

    def call(self, data):
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


#=========================
#   Time 
#=========================

def timezonize(timezone):
    '''Convert a string representation of a timezone to its pytz object or do nothing if the argument is already a pytz timezone'''
    
    # Check if timezone is a valid pytz object is hard as it seems that they are spread arount the pytz package.
    # Option 1): Try to convert if string or unicode, else try to
    # instantiate a datetiem object with the timezone to see if it is valid 
    # Option 2): Get all memebers of the pytz package and check for type, see
    # http://stackoverflow.com/questions/14570802/python-check-if-object-is-instance-of-any-class-from-a-certain-module
    # Option 3) perform a hand.made test. We go for this one, tests would fail if it gets broken
    
    if not 'pytz' in str(type(timezone)):
        timezone = pytz.timezone(timezone)
    return timezone

def now_t():
    '''Return the current time in epoch seconds'''
    return now_s()

def now_s():
    '''Return the current time in epoch seconds'''
    return calendar.timegm(now_dt().utctimetuple())

def now_dt(tzinfo='UTC'):
    '''Return the current time in datetime format'''
    if tzinfo != 'UTC':
        raise NotImplementedError()
    return datetime.datetime.utcnow().replace(tzinfo = pytz.utc)

def dt(*args, **kwargs):
    '''Initialize a datetime object in the proper way. Using the standard datetime leads to a lot of
     problems with the tz package. Also, it forces UTC timezone if no timezone is specified'''
    
    if 'tz' in kwargs:
        tzinfo = kwargs.pop('tz')
    else:
        tzinfo  = kwargs.pop('tzinfo', None)
        
    offset_s  = kwargs.pop('offset_s', None)   
    trustme   = kwargs.pop('trustme', None)
    
    if kwargs:
        raise Exception('Unhandled arg: "{}".'.format(kwargs))
        
    if (tzinfo is None):
        # Force UTC if None
        timezone = timezonize('UTC')
        
    else:
        timezone = timezonize(tzinfo)
    
    if offset_s:
        # Special case for the offset
        if not tzoffset:
            raise Exception('For ISO date with offset please install dateutil')
        time_dt = datetime.datetime(*args, tzinfo=tzoffset(None, offset_s))
    else:
        # Standard  timezone
        time_dt = timezone.localize(datetime.datetime(*args))

    # Check consistency    
    if not trustme and timezone != pytz.UTC:
        if not check_dt_consistency(time_dt):
            raise Exception('Sorry, time {} does not exists on timezone {}'.format(time_dt, timezone))

    return  time_dt

def get_tz_offset_s(time_dt):
    '''Get the time zone offset in seconds'''
    return s_from_dt(time_dt.replace(tzinfo=pytz.UTC)) - s_from_dt(time_dt)

def check_dt_consistency(date_dt):
    '''Check that the timezone is consistent with the datetime (some conditions in Python lead to have summertime set in winter)'''

    # https://en.wikipedia.org/wiki/Tz_database
    # https://www.iana.org/time-zones
    
    if date_dt.tzinfo is None:
        return True
    else:
        
        # This check is quite heavy but there is apparently no other way to do it.
        if date_dt.utcoffset() != dt_from_s(s_from_dt(date_dt), tz=date_dt.tzinfo).utcoffset():
            return False
        else:
            return True

def correct_dt_dst(datetime_obj):
    '''Check that the dst is correct and if not change it'''

    # https://en.wikipedia.org/wiki/Tz_database
    # https://www.iana.org/time-zones

    if datetime_obj.tzinfo is None:
        return datetime_obj

    # Create and return a New datetime object. This corrects the DST if errors are present.
    return dt(datetime_obj.year,
              datetime_obj.month,
              datetime_obj.day,
              datetime_obj.hour,
              datetime_obj.minute,
              datetime_obj.second,
              datetime_obj.microsecond,
              tzinfo=datetime_obj.tzinfo)

def change_tz(dt, tz):
    return dt.astimezone(timezonize(tz))

def dt_from_t(timestamp_s, tz=None):
    '''Create a datetime object from an epoch timestamp in seconds. If no timezone is given, UTC is assumed'''
    # TODO: check if uniform everything on this one or not.
    return dt_from_s(timestamp_s=timestamp_s, tz=tz)
    
def dt_from_s(timestamp_s, tz=None):
    '''Create a datetime object from an epoch timestamp in seconds. If no timezone is given, UTC is assumed'''

    if not tz:
        tz = "UTC"
    try:
        timestamp_dt = datetime.datetime.utcfromtimestamp(float(timestamp_s))
    except TypeError:
        raise Exception('timestamp_s argument must be string or number, got {}'.format(type(timestamp_s)))

    pytz_tz = timezonize(tz)
    timestamp_dt = timestamp_dt.replace(tzinfo=pytz.utc).astimezone(pytz_tz)
    
    return timestamp_dt

def s_from_dt(dt):
    '''Returns seconds with floating point for milliseconds/microseconds.'''
    if not (isinstance(dt, datetime.datetime)):
        raise Exception('s_from_dt function called without datetime argument, got type "{}" instead.'.format(dt.__class__.__name__))
    microseconds_part = (dt.microsecond/1000000.0) if dt.microsecond else 0
    return  ( calendar.timegm(dt.utctimetuple()) + microseconds_part)

def dt_from_str(string, timezone=None):

    # Supported formats on UTC
    # 1) YYYY-MM-DDThh:mm:ssZ
    # 2) YYYY-MM-DDThh:mm:ss.{u}Z

    # Supported formats with offset    
    # 3) YYYY-MM-DDThh:mm:ss+ZZ:ZZ
    # 4) YYYY-MM-DDThh:mm:ss.{u}+ZZ:ZZ

    # Split and parse standard part
    date, time = string.split('T')
    
    if time.endswith('Z'):
        # UTC
        offset_s = 0
        time = time[:-1]
        
    elif ('+') in time:
        # Positive offset
        time, offset = time.split('+')
        # Set time and extract positive offset
        offset_s = (int(offset.split(':')[0])*60 + int(offset.split(':')[1]) )* 60   
        
    elif ('-') in time:
        # Negative offset
        time, offset = time.split('-')
        # Set time and extract negative offset
        offset_s = -1 * (int(offset.split(':')[0])*60 + int(offset.split(':')[1])) * 60      
    
    else:
        raise Exception('Format error')
    
    # Handle time
    hour, minute, second = time.split(':')
    
    # Now parse date (easy)
    year, month, day = date.split('-') 

    # Convert everything to int
    year    = int(year)
    month   = int(month)
    day     = int(day)
    hour    = int(hour)
    minute  = int(minute)
    if '.' in second:
        usecond = int(second.split('.')[1])
        second  = int(second.split('.')[0])
    else:
        second  = int(second)
        usecond = 0
    
    return dt(year, month, day, hour, minute, second, usecond, offset_s=offset_s)

def dt_to_str(dt):
    '''Return the ISO representation of the datetime as argument'''
    return dt.isoformat()









