import os
import traceback
import hashlib
import random
import subprocess
import logging
from collections import namedtuple

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
    from backend.settings import BACKEND_EMAIL_APIKEY, BACKEND_EMAIL_FROM, BACKEND_EMAIL_SERVICE

    if BACKEND_EMAIL_SERVICE == 'Sendgrid':
        import sendgrid
        from sendgrid.helpers.mail import Email,Content,Mail

        sg = sendgrid.SendGridAPIClient(apikey=BACKEND_EMAIL_APIKEY)
        from_email = Email(BACKEND_EMAIL_FROM)
        to_email = Email(to)
        subject = subject
        content = Content('text/plain', text)
        mail = Mail(from_email, subject, to_email, content)
        response = sg.client.mail.send.post(request_body=mail.get())
        #logger.debug(response.status_code)
        #logger.debug(response.body)
        #logger.debug(response.headers)
    

def format_exception(e, debug=False):
    
    # Importing here instead of on top avoids circular dependencies problems when loading booleanize in settings
    from backend.settings import DEBUG

    if DEBUG:
        # Cutting away the last char removed the newline at the end of the stacktrace 
        return str('Got exception "{}" of type "{}" with traceback:\n{}'.format(e.__class__.__name__, type(e), traceback.format_exc()))[:-1]
    else:
        return str('Got exception "{}" of type "{}" with traceback "{}"'.format(e.__class__.__name__, type(e), traceback.format_exc().replace('\n', '|')))


def log_user_activity(level, msg, request, caller=None):

    # Get the caller function name through inspect with some logic
    #import inspect
    #caller =  inspect.stack()[1][3]
    #if caller == "post":
    #    caller =  inspect.stack()[2][3]
    
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
    '''Create a random string of 156 chars to be used as username'''             
    #username = ''.join(random.choice('abcdefghilmnopqrtuvz') for _ in range(16))
    #import uuid
    #username = str(uuid4()).replace('-','')[0:16] # or [0:22]
    username = ''.join(random.choice('qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM0123456789') for _ in range(22))
    return username


def discover_apps(folder, only_names=False):

    # List directories in folder
    dirs = [ dir for dir in os.listdir(folder) if os.path.isdir(os.path.join(folder,dir)) ]
    
    apps = ()
    # Detect apps
    for dir in dirs:
        if dir.endswith('app'):
            if only_names:
                apps = apps + (dir,)
            else:    
                apps = apps + ('backend.{}'.format(dir),)
        
    
    return apps


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
    '''Execute a command in the OS shell. By default prints everything. If the capture switch is set,
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


def get_md5(string):
    if not string:
        raise Exception("Colund not compute md5 of empty/None value")
    
    m = hashlib.md5()
    
    # Fix for Python3
    try:
        if isinstance(string,unicode):
            string=string.encode('utf-8')
    except NameError:
        string=string.encode('utf-8')
        
    m.update(string)
    md5 = str(m.hexdigest())
    return md5


def fix_url_encode(url):
    url_unicode =  unicode(url)              
    url_sanitized = url_unicode.encode('utf-8')              
    url_cleaned = urllib.unquote(url_sanitized)
    return url_cleaned    
