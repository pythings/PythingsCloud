import os
import traceback
import hashlib
import random
import logging
import base64

# Setup logging
logger = logging.getLogger(__name__)


#======================
#  Utility functions
#======================

def booleanize(*args, **kwargs):
    # Handle both single value and kwargs to get arg name
    name = None
    if args and not kwargs:
        value=args[0]
    elif kwargs and not args:
        for item in kwargs:
            name  = item
            value = kwargs[item]
            break
    else:
        raise Exception('Internal Error')
    
    # Handle shortcut: an arg with its name equal to ist value is considered as True
    if name==value:
        return True
    
    if isinstance(value, bool):
        return value
    else:
        if value.upper() in ('TRUE', 'YES', 'Y', '1'):
            return True
        else:
            return False


def send_email(to, subject, text):

    # Importing here instead of on top avoids circular dependencies problems when loading booleanize in settings
    from django.conf import settings
    
    if settings.BACKEND_EMAIL_SERVICE == 'Sendgrid':
        import sendgrid
        from sendgrid.helpers.mail import Email, Content, Mail

        sg = sendgrid.SendGridAPIClient(apikey=settings.BACKEND_EMAIL_APIKEY)
        from_email = Email(settings.BACKEND_EMAIL_FROM)
        to_email = Email(to)
        subject = subject
        content = Content('text/plain', text)
        mail = Mail(from_email, subject, to_email, content)
        
        # Send the email
        response = sg.client.mail.send.post(request_body=mail.get())
        
        # Log. Also response.body and response.headers are available
        logger.debug('Sent email, response statuc code: {}'.format(response.status_code))
    

def format_exception(e, debug=False):
    
    # Importing here instead of on top avoids circular dependencies problems when loading booleanize in settings
    from django.conf import settings

    if settings.DEBUG:
        # Cutting away the last char removed the newline at the end of the stacktrace 
        return str('Got exception "{}" of type "{}" with traceback:\n{}'.format(e.__class__.__name__, type(e), traceback.format_exc()))[:-1]
    else:
        return str('Got exception "{}" of type "{}" with traceback "{}"'.format(e.__class__.__name__, type(e), traceback.format_exc().replace('\n', '|')))


def log_user_activity(level, msg, request, caller=None):

    try:
        msg = str(caller) + " view - USER " + str(request.user.email) + ": " + str(msg)
    except AttributeError:
        msg = str(caller) + " view - USER UNKNOWN: " + str(msg)

    try:
        level = getattr(logging, level)
    except:
        raise
    
    logger.log(level, msg)


def username_hash(email):
    '''Create md5 base 64 (25 chrars) hash from user email:'''             
    m = hashlib.md5()
    m.update(email)
    username = m.hexdigest().decode('hex').encode('base64')[:-3]
    return username


def random_username():
    '''Create a random string of 156 alphanumeric chars to be used as username'''
    username = ''.join(random.choice('qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM0123456789') for _ in range(22))
    return username


def discover_apps(folder, only_names=False):
    '''Discover Django Apps, where an "App" is a folder ending with "app"'''

    # List directories in folder
    dirs = [ dir for dir in os.listdir(folder) if os.path.isdir(os.path.join(folder,dir)) ]

    # Detect apps    
    apps = ()
    for dir in dirs:
        if dir.endswith('app'):
            if only_names:
                apps = apps + (dir,)
            else:    
                apps = apps + ('backend.{}'.format(dir),)
        
    
    return apps


def decode_base64(data):
    """Decode base64, padding being optional. Routine by Simon Sapin, taken from Stack overlfow:
    https://stackoverflow.com/questions/2941995/python-ignore-incorrect-padding-error-when-base64-decoding

    :param data: Base64 data as an ASCII byte string
    :returns: The decoded byte string.

    """
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += b'='* (4 - missing_padding)
    return base64.decodestring(data)

