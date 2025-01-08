import os
import logging
import uuid
import time
import pytz
import datetime

# Django imports
from django.shortcuts import render
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.conf import settings
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.mail import send_mail

# Backend imports
from ..common.decorators import private_view, public_view
from ..common.utils import booleanize, format_exception, random_username
from ..common.exceptions import ErrorMessage
from ..common.time import timezonize, s_from_dt, dt, dt_from_s
from ..base_app.models import LoginToken
from .models import App, Thing, Session, Profile, WorkerMessageHandler, MessageCounter, ManagementMessage, WorkerMessage, Pool, File, Commit
from .helpers import create_app as create_app_helper
from .helpers import create_none_app, get_total_messages, get_total_devices, get_timezone_from_request

# Setup logging
logger = logging.getLogger(__name__)


# This is a support var used to prevent double click problems
ONGOING_SIGNUPS = {}

#==========================
#  Web Setup view
#==========================

@public_view
def websetup(request):

    # Init data
    data={}
    data['user']  = request.user
    data['BASE_PATH']  = 'https://' + settings.MAIN_DOMAIN_NAME

    return render(request, 'websetup.html', {'data': data})


#==========================
#  New Thing view
#==========================

@private_view
def new_thing(request):

    # Init data
    data={}
    data['user']  = request.user

    return render(request, 'new_thing.html', {'data': data})


#=========================
#  User login view
#=========================

@public_view
def user_login(request):
  
    redirect= '/postlogin'
    data = {}

    # If authenticated user reloads the main URL
    if request.method == 'GET' and request.user.is_authenticated():
        return HttpResponseRedirect(redirect)
    
    # If unauthenticated user tries to log in
    if request.method == 'POST':
        if not request.user.is_authenticated():
            username = request.POST.get('username')
            password = request.POST.get('password')
            # Use Django's machinery to attempt to see if the username/password
            # combination is valid - a User object is returned if it is.
            
            if "@" in username:
                # Get the username from the email
                try:
                    user = User.objects.get(email=username)
                    username = user.username
                except User.DoesNotExist:
                    if password:
                        raise ErrorMessage('Check email and password')
                    else:
                        # Return here, we don't want to give any hints about existing users
                        data['success'] = 'Ok, you will shortly receive a login link by email (if we have your data).'
                        return render(request, 'login.html', {'data': data})
            
            if password:
                user = authenticate(username=username, password=password)
                if user:
                    login(request, user)
                    return HttpResponseRedirect(redirect)
                else:
                    raise ErrorMessage('Check email and password')
            else:
                
                # If empty password, send mail with login token
                token = uuid.uuid4()
                logger.debug('Sending login token "{}" via mail to {}'.format(token, user.email))
                
                # Create token or update if existent (and never used)
                try:
                    loginToken = LoginToken.objects.get(user=user)
                except LoginToken.DoesNotExist:     
                    LoginToken.objects.create(user=user, token=token)
                else:
                    loginToken.token = token
                    loginToken.save()

                send_mail(
                    subject = 'Pythings Cloud login link',
                    message = 'Hello,\n\nhere is your login link: {}/login/?token={}\n\nOnce logged in, you can go to "My Account" and change password (or just keep using the login link feature).'.format(settings.MAIN_DOMAIN_NAME, token),
                    from_email = 'Emberly <notifications@emberly.live>',
                    recipient_list = [user.email],
                    fail_silently=False,
                )

                # Return here, we don't want to give any hints about existing users
                data['success'] = 'Ok, you will shortly receive a login link by email (if we have your data).'
                return render(request, 'login.html', {'data': data})
                    
                
        else:
            # This should never happen.
            # User tried to log-in while already logged in: log him out and then render the login
            logout(request)        
              
    else:
        # If we are logging in through a token
        token = request.GET.get('token', None)

        if token:
            
            loginTokens = LoginToken.objects.filter(token=token)
            
            if not loginTokens:
                raise ErrorMessage('Token not valid or expired')
    
            
            if len(loginTokens) > 1:
                raise Exception('Consistency error: more than one user with the same login token ({})'.format(len(loginTokens)))
            
            # Use the first and only token (todo: use the objects.get and correctly handle its exceptions)
            loginToken = loginTokens[0]
            
            # Get the user from the table
            user = loginToken.user
            
            # Set auth backend
            user.backend = 'django.contrib.auth.backends.ModelBackend'
    
            # Ok, log in the user
            login(request, user)
            loginToken.delete()
            
            # Now redirect to site
            return HttpResponseRedirect(redirect)
                
    # All other cases, render the login page
    return render(request, 'login.html', {'data': data})


#=========================
#  Post login view
#=========================

@private_view
def postlogin(request):
    
    if request.user.profile.last_accepted_terms < settings.TERMS_VERSION:
        
        accepted = booleanize(request.GET.get('accepted', False))
        if accepted:
            request.user.profile.last_accepted_terms=settings.TERMS_VERSION
            request.user.profile.save()
            return HttpResponseRedirect('/dashboard')
        
        data = {'action':'accept_terms'}
        return render(request, 'postlogin.html', {'data': data})
    else:
        return HttpResponseRedirect('/dashboard')


#=========================
#  User logout view
#=========================

@private_view
def user_logout(request): 
    logout(request)
    return HttpResponseRedirect('/')


#=========================
#  Register view
#=========================

@public_view
def register(request):

    # user var
    user = None

    # Init data
    data={}
    data['user']   = request.user
    data['status'] = None
    if settings.INVITATION_CODE:
        data['require_invitation'] = True
    else:
        data['require_invitation'] = False

    # Get data
    email      = request.POST.get('email', None)
    password   = request.POST.get('password', None)
    invitation = request.POST.get('invitation', None) # Verification code set for anyone

    if request.user.is_authenticated():
        return(HttpResponseRedirect('/dashboard'))

    else:

        if email and password:
            
            # Check both email and password are set
            if not email:
                raise ErrorMessage('Missing email')
         
            if not password:
                raise ErrorMessage('Missing password')
         
            # Check if we have to validate an invitation code
            if settings.INVITATION_CODE:
                if invitation != settings.INVITATION_CODE:
                    raise ErrorMessage('The invitation code you entered is not valid.')
            
            if not email in ONGOING_SIGNUPS:
                
                # Add user to recent signups dict
                ONGOING_SIGNUPS[email] = None
                
                # Check if user with this email already exists
                if len(User.objects.filter(email = email)) > 0:
                    del ONGOING_SIGNUPS[email]
                    raise ErrorMessage('The email address you entered is already registered.')
  
                # Register the user
                user = User.objects.create_user(random_username(), password=password, email=email)

                # Is this necessary?
                user.save()
                
                # Manually set the auth backend for the user
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                
                data['status'] = 'activated'
                data['user'] = user

                # Get email updates preference
                email_updates = booleanize(request.POST.get('email_updates', False))
                
                # Create the user Profile
                logger.debug('Creating user profile for user "{}" with email_updates="{}"'.format(user.email, email_updates))
                Profile.objects.create(user=request.user, last_accepted_terms=settings.TERMS_VERSION, email_updates=email_updates)
                
                # Create Messages counter
                logger.debug('Creating messages counter for user "{}" '.format(user.email))
                MessageCounter.objects.create(user = user)
            
                # Also create the None App for the user
                logger.debug('Creating None App for user "{}" '.format(user.email))
                create_none_app(request.user)
                
                # Remove user from recent signups
                del ONGOING_SIGNUPS[email]
                
                return render(request, 'register.html', {'data': data})
            
            else:

                # Check previous requesta ctivated the user
                i=0
                while True:
                    if email not in ONGOING_SIGNUPS:
                        break
                    else:
                        time.sleep(1)
                        i+=1
                    if i>30:
                        raise ErrorMessage('Timed up. Your user might have been correctly created anyway. Please try to login if it does not work to signup again, if the error persists contact us')

                users_with_this_email = User.objects.filter(email = email)
                if users_with_this_email<1:
                    raise ErrorMessage('Error in creating the user. Please try again and if the error persists contact us')
                else:
                    data['status'] = 'activated'
                    data['user'] = users_with_this_email[0]
                    user = authenticate(username=users_with_this_email[0].username, password=password)
                    if not user:
                        raise ErrorMessage('Error. Please try again and if the error persists contact us')
                    login(request, user)
                    return render(request, 'register.html', {'data': data})

        else:
            return render(request, 'register.html', {'data': data})

    return render(request, 'register.html', {'data': data})


#==========================
#  Account view
#==========================

@private_view
def account(request):

    data={}
    data['user'] = request.user
    
    # Get profile and create on the fly if it does not exist yet (for old users)
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        Profile.objects.create(user=request.user)
        profile = Profile.objects.get(user=request.user)
    data['profile'] = profile
    
    # Set values from POST and GET
    edit = request.POST.get('edit', None)
    if not edit:
        edit = request.GET.get('edit', None)
        data['edit'] = edit
    value = request.POST.get('value', None)
    
    # Fix None
    if value and value.upper() == 'NONE':
        value = None
    if edit and edit.upper() == 'NONE':
        edit = None
    
    # Obtain total messages and total devices for a user
    total_messages, _, _ = get_total_messages(request.user)
    total_devices = get_total_devices(request.user) 
    
    # Set texts for totals
    if profile.plan == 'Unlimited':
        data['messages_usage'] =  '{} of unlimited'.format(total_messages)
        data['devices_usage']  =  '{} of unlimited'.format(total_devices)
    elif profile.plan == 'Betatester':
        data['messages_usage']  =  '{} of {} (remaining: {})'.format(total_messages, profile.plan_messages_limit, profile.plan_messages_limit - total_messages)        
        data['devices_usage'] =  '{} of {}'.format(total_devices, profile.plan_things_limit)
    elif profile.plan == 'Free':
        data['messages_usage'] =  '{} of unlimited'.format(total_messages)
        data['devices_usage']  =  '{} of {} (remaining: {})'.format(total_devices, profile.plan_things_limit, profile.plan_things_limit - total_devices)        
    else:
        raise Exception('Unknown plan "{}" for user "{}"'.format(profile.plan, request.user.username))

    # Do we have to edit something?
    if edit:
        try:
            logger.info('Editing "{}" with value "{}"'.format(edit,value))
            
            # Timezone
            if edit=='timezone' and value:
                # Validate
                timezonize(value)
                profile.timezone = value
                profile.save()
    
            # Email
            elif edit=='email' and value:
                request.user.email=value
                request.user.save()
    
            # Password
            elif edit=='password' and value:
                request.user.set_password(value)
                request.user.save()
    
            # API key
            elif edit=='apikey' and value:
                profile.apikey=value
                profile.save()
    
            # Plan
            elif edit=='plan' and value:
                profile.plan=value
                profile.save()
    
            # Type ID
            elif edit=='type_id' and value:
                value=int(value)
                if value <= 10:
                    profile.type = 'Standard'                                          
                    profile.type_id = int(value)
                else:
                    profile.type = 'Advanced'                                          
                    profile.type_id = int(value)                        
                    
                profile.save()

            # Email preferences
            elif edit=='email_preferences':
                if booleanize(request.POST.get('do_update', False)):
                    email_updates = booleanize(request.POST.get('email_updates', False))
                    if profile.email_updates != email_updates:
                        profile.email_updates = email_updates
                        profile.save()

            # Delete account
            elif edit=='delete_account' and value:
                if value == request.user.username:
                    logger.info('Deleting account for "{}"'.format(value))
                    user = request.user

                    # Logout and delete
                    logout(request)
                    user.delete()                    
                    
                    data['success'] = 'Ok, account deleted. We are sorry to see you go!'
                    data['redirect_home'] = True 
                    return render(request, 'success.html', {'data': data})
                else:
                    raise ErrorMessage('Incorrect double-check on the Account ID.')
            
            # Generic property
            elif edit and value:
                raise Exception('Unknown attribute "{}" to edit'.format(edit))
    
        except ErrorMessage:
            raise
        except Exception as e:
            logger.error('Error in performing the "{}" operation:"{}"'.format(edit, e))
            data['error'] = 'Sorry, something unexpected happened. Please retry or contact support.'
            return render(request, 'error.html', {'data': data})
    
    
    return render(request, 'account.html', {'data': data})


#==========================
#  Main Dashboard view
#==========================

@private_view
def dashboard(request):

    # Init data
    data={}
    data['user']  = request.user

    # Enumerate applications for this user
    apps = App.objects.filter(user=request.user, hidden=False).order_by('name')
    all_apps = App.objects.filter(user=request.user)
    data['apps'] = apps
    
    # Get last edit time
    for app in apps:
        app.latest_commit_ts = str(Commit.objects.filter(app=app).latest('ts').ts.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]

    # Enumerate things for this user Apps
    data['lastsessions'] = []
    for thing in Thing.objects.filter(app_id__in=[app.id for app in all_apps]):
    
        try:
            session = Session.objects.filter(thing=thing).latest('last_contact')
        except:
            pass
        else:
    
            # Get delta between now and last contact
            deltatime_from_last_contact_s = time.time() - s_from_dt(session.last_contact)
            session.connection_status = '<font color="red">OFFLINE</font>'
            session.thing_status = 'OFFLINE'
            try:
                if deltatime_from_last_contact_s < int(thing.pool.settings.management_interval) + settings.CONTACT_TIMEOUT_TOLERANCE:
                    session.connection_status = '<font color="limegreen">ONLINE</font>'
                    session.thing_status = 'ONLINE'
            except:
                pass
            try:
                if deltatime_from_last_contact_s < int(thing.pool.settings.worker_interval) + settings.CONTACT_TIMEOUT_TOLERANCE:
                    session.connection_status = '<font color="limegreen">ONLINE</font>'
                    session.thing_status = 'ONLINE'
            except:
                pass
            
            # Attach App name
            session.app_name = thing.app.name
            
            # Improve displaying time
            session.last_contact = str(session.last_contact.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
            
            global_status = '<font color="limegreen">OK</font>'
            for _ in [1]:
           
                if session.last_pythings_status[0:2].upper() != 'OK':
                    global_status = '<font color="red">NOK</font>'
                    break
                
                if session.last_worker_status[0:2].upper() == 'KO':
                    global_status = '<font color="red">NOK</font>'
                    break
                
                if session.last_management_status[0:2].upper() == 'KO':
                    global_status = '<font color="red">NOK</font>'
                    break
    
                if session.last_worker_status[0:2].upper() == 'UN':
                    global_status = '<font color="orange">HOK</font>'
                    break   
                
                if session.last_management_status[0:2].upper() == 'UN':
                    global_status = '<font color="orange">HOK</font>'
                    break
                             
            session.global_status = global_status
            
            # Append session to last sessions 
            data['lastsessions'].append(session)

            # Get last worker message
            try: 
                last_worker_msgs = WorkerMessageHandler.get(aid=thing.app.aid, tid=thing.tid, last=1)
                for item in last_worker_msgs:
                    session.last_worker_msg = item
                    break
            except Exception as e:
                logger.error(e)
                session.last_worker_msg = None    

    # Reorder based on name
    data['lastsessions'].sort(key=lambda x: x.app_name, reverse=False)

    # Render
    return render(request, 'dashboard.html', {'data': data})


#===========================
#  App Dashboard view
#===========================

@private_view
def dashboard_app(request):

    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)
    data['app'] = None
    data['lastsessions'] = []
    data['pool'] = None
    data['orpool'] = request.GET.get('orpool',None)
    data['action'] = request.GET.get('action', None)
    data['view'] = request.GET.get('view', 'editor')
    confirmed = request.GET.get('confirmed', False)
          
    # Get AID form GET request
    intaid = request.GET.get('intaid',None)
    if intaid is None:
        intaid = request.POST.get('intaid',None)
    
    pool_name = request.GET.get('pool', None)
    if pool_name is None:
        pool_name = request.POST.get('pool', None)
    
    # Set edit values from POST and GET
    edit = request.POST.get('edit', None)
    if not edit:
        edit = request.GET.get('edit', None)
        data['edit'] = edit
    value = request.POST.get('value', None)
    
    # Get the App
    try:
        app = App.objects.get(id=intaid, user=request.user)
        data['app'] = app
    except App.DoesNotExist:
        data['error'] = 'App with intaid "{}" is not existent or you do not have access rights.'.format(intaid)
        return render(request, 'error.html', {'data': data})
    
    # Delete App
    if data['action'] == 'delete' and confirmed:
        
        # Start procedure for deleting the App
        data['appname'] = app.name
        
        # 1) Find all Things registered to this App and delete Up and Down messages
        for thing in Thing.objects.filter(app=app):
            logger.info('Removing messages for TID "{}" '.format(thing.tid))
            WorkerMessage.objects.filter(aid=thing.app.aid, tid=thing.tid).delete()
            ManagementMessage.objects.filter(aid=thing.app.aid, tid=thing.tid).delete()
    
        # 2) Save Settings which are indirectly attached to the App's pools
        setting_objects_to_delete=[]
        for pool in Pool.objects.filter(app=app):
            logger.info('Removing pool settings for pool "{}" '.format(pool.name))
            setting_objects_to_delete.append(pool.settings)
    
        # 3) Delete the App, this will trigger a "delete cascade" basically.
        app.delete()
        
        # 4) Remove settings leftover
        for setting_object_to_delete in setting_objects_to_delete:
            setting_object_to_delete.delete()
        
        # Render OK-deleted page
        return render(request, 'dashboard_app_deleted.html', {'data': data})

    # Set PythingsOS versions
    data['pythings_versions'] = settings.OS_VERSIONS
    
    # If a pool is set, get it, otherwise use the default pool:
    if pool_name:
        try:
            selected_pool = Pool.objects.get(app=app, name=pool_name)
            data['pool'] = selected_pool
        except Pool.DoesNotExist:
            data['error'] = 'The pool "{}" does not exists'.format(pool_name)
            return render(request, 'error.html', {'data': data})
    else:
        selected_pool = app.default_pool
    
    # Enumerate App's versions
    versions = []
    for commit in Commit.objects.filter(app=app):
        if commit.tag is not None:
            versions.append(commit) 
        else:
            if selected_pool.development:
                versions.append(commit)
                   
    versions.reverse()
    data['app_versions'] = versions
    
    # Set the pool for the template            
    data['pool'] = selected_pool
    
    # Enumerate the pools for this application
    data['pools'] = []
    for pool in Pool.objects.filter(app=app):
        data['pools'].append(pool)
    
    # Special case for use_latest
    use_latest_app = request.POST.get('use_latest_app', None)
    if use_latest_app:
        if use_latest_app.upper()=='TRUE':
            use_latest_app = True
            if not selected_pool.use_latest_app_version:
                selected_pool.use_latest_app_version = True
                selected_pool.save()
            
        elif use_latest_app.upper()=='FALSE':
            use_latest_app = False
            if selected_pool.use_latest_app_version:
                selected_pool.use_latest_app_version = False
                selected_pool.save()
            
        else:
            data['error'] = 'Unknown value "{}" for use_latest_app'.format(use_latest_app)
            return render(request, 'error.html', {'data': data})            
    
    # Settings edit required?
    if use_latest_app:
        value=True
    if edit and value:
        try:
            logger.info('Setting "{}" to "{}"'.format(edit,value))
            if edit=='management_interval' and value:
                int(value)
                selected_pool.settings.management_interval = value
                selected_pool.settings.save()
            elif edit=='worker_interval' and value:
                try:
                    int(value)
                except ValueError:
                    if value.lower()=='auto':
                        value=value.lower()
                    else:
                        raise
                selected_pool.settings.worker_interval = value
                selected_pool.settings.save()
            elif edit=='ssl' and value:
                if value.upper()=='TRUE':
                    selected_pool.settings.ssl = True
                else:
                    selected_pool.settings.ssl = False
                selected_pool.settings.save()
            elif edit=='payload_encryption' and value:
                if value.upper()=='TRUE':
                    selected_pool.settings.payload_encryption = True
                else:
                    selected_pool.settings.payload_encryption = False
                selected_pool.settings.save()
            elif edit=='pythings_version' and value:
                if value not in data['pythings_versions']:
                    raise
                selected_pool.settings.pythings_version = value
                selected_pool.settings.save()
            elif edit=='app_name' and value:
                app.name = value
                app.save()
            elif edit=='app_version':
                if use_latest_app:
                    if selected_pool.development:
                        commit = Commit.objects.filter(app=app).latest('ts')
                    else:
                        commit = Commit.objects.filter(app=app,tag__isnull=False).latest('ts')
                    selected_pool.settings.app_version = commit.cid
                    selected_pool.settings.save()
                elif value:
                    # Validate
                    if len(value) >5 and value[0:4]==('tag:'):
                        value = value[4:]
                        commit = Commit.objects.get(app=app,tag=value)
                    else:
                        commit = Commit.objects.get(app=app,cid=value)
                    # Update  
                    selected_pool.settings.app_version = commit.cid
                    selected_pool.settings.save()
                else:
                    pass 
                
            # Generic property
            else:
                raise Exception()

        except Exception as e:
            logger.error('{}:{}'.format(type(e),str(e)))
            data['error'] = 'The property "{}" does not exists or the value "{}" is not valid.'.format(edit, value)
            return render(request, 'error.html', {'data': data})   
    
    # Trick: get pool App version tag if any:
    try:
        commit = Commit.objects.get(app=app,cid=selected_pool.settings.app_version)
        selected_pool.settings.app_tag = commit.tag
    except:
        data['error'] = 'Consistency error: Cannot find commit for cid "{}"'.format(selected_pool.settings.app_version)
        return render(request, 'error.html', {'data': data})           
     
    # Get latest version
    data['app_latest_commit'] = Commit.objects.filter(app=app).latest('ts')
    data['app_latest_commit_ts'] = str(data['app_latest_commit'].ts.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
   
    # Enumerate things for this App and pool
    for thing in Thing.objects.filter(app=app, pool=selected_pool):
    
        try:
            session = Session.objects.filter(thing=thing).latest('last_contact')
        except:
            pass
        else:
    
            # Get delta between now and last contact 
            deltatime_from_last_contact_s = time.time() - s_from_dt(session.last_contact) #session.last_contact 
            session.connection_status = '<font color="red">OFFLINE</font>'
            session.thing_status = 'OFFLINE'
            try:
                if deltatime_from_last_contact_s < int(selected_pool.settings.management_interval) + settings.CONTACT_TIMEOUT_TOLERANCE:
                    session.connection_status = '<font color="limegreen">ONLINE</font>'
                    session.thing_status = 'ONLINE'
            except:
                pass
            try:
                if deltatime_from_last_contact_s < int(selected_pool.settings.worker_interval) + settings.CONTACT_TIMEOUT_TOLERANCE:
                    session.connection_status = '<font color="limegreen">ONLINE</font>'
                    session.thing_status = 'ONLINE'
            except:
                pass

            # Improve displaying time
            session.last_contact = str(session.last_contact.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
            
            global_status = '<font color="limegreen">OK</font>'
            for _ in [1]:
           
                if session.last_pythings_status[0:2].upper() != 'OK':
                    global_status = '<font color="red">KO</font>'
                    break
                
                if session.last_worker_status[0:2].upper() == 'KO':
                    global_status = '<font color="red">KO</font>'
                    break
                
                if session.last_management_status[0:2].upper() == 'KO':
                    global_status = '<font color="red">KO</font>'
                    break
    
                if session.last_worker_status[0:2].upper() == 'UN':
                    global_status = '<font color="orange">~OK</font>'
                    break   
                
                if session.last_management_status[0:2].upper() == 'UN':
                    global_status = '<font color="orange">~OK</font>'
                    break
                             
            session.global_status = global_status
            
            # Add latest commit to understand if we have an AI
            session.app_latest_commit = data['app_latest_commit']
            
            # Append last session
            data['lastsessions'].append(session)
    
            # Get last worker message
            try: 
                last_worker_msgs = WorkerMessageHandler.get(aid=thing.app.aid, tid=thing.tid, last=1)
                for item in last_worker_msgs:
                    session.last_worker_msg = item
                    break
                logger.debug('Last worker message: {}'.format(session.last_worker_msg) )

            except Exception as e:
                logger.error(e)
                session.last_worker_msg = None
    
    # Render
    return render(request, 'dashboard_app.html', {'data': data})


#==================================
#  Thing Dashboard view
#==================================

@private_view
def dashboard_thing(request):

    profile_timezone = timezonize(get_timezone_from_request(request))
    
    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)
    data['apps']  = {}
    data['metrics'] = {}
    data['timeseries'] = {}
    
    tid = request.GET.get('tid',None)
    if not tid:
        # Try to set  from POST
        tid = request.POST.get('tid',None)

    intaid = request.GET.get('intaid',None)
    if not intaid:
        # Try to set  from POST
        intaid = request.POST.get('intaid',None)

    confirmed = request.GET.get('confirmed', False)
    last = request.GET.get('last',None)
    pool_name = request.GET.get('pool',None)
    data['orpool'] = request.GET.get('orpool', None)
    data['action'] = request.GET.get('action', None)
    data['refresh'] = request.GET.get('refresh', '')
    data['filterby'] = request.GET.get('filterby', '') # Do not use None, or you will end up with it in the HTML page
    data['sid'] = request.GET.get('sid', None)

    from_str = request.GET.get('from', None)
    to_str   = request.GET.get('to', None)

    from_t = request.GET.get('from_t', None)
    to_t   = request.GET.get('to_t', None)

    # Set values from POST and GET
    edit = request.POST.get('edit', None)
    if not edit:
        edit = request.GET.get('edit', None)
        data['edit'] = edit
    name = request.POST.get('name', None)

    if not tid:
        return render(request, 'error.html', {'data': {'error': 'No Thing ID provided'}})

    if not intaid:
        return render(request, 'error.html', {'data': {'error': 'No App ID provided'}})
        
    # Get all Apps
    data['apps'] = App.objects.filter(user=request.user, hidden=False)

    # Get App
    try:
        app = App.objects.get(id=intaid, user=request.user)
    except App.DoesNotExist:
        data['error'] = 'The App with Internal ID "{}" does not exists or you do not have access rights'.format(intaid)
        return render(request, 'error.html', {'data': data})   

    # Get Thing
    try:
        thing = Thing.objects.get(tid=tid, app=app)
    except Thing.DoesNotExist:
        data['error'] = 'The Thing with ID "{}" does not exists or you do not have access rights'.format(tid)
        return render(request, 'error.html', {'data': data})   
    data['thing'] = thing
    
    # Check ownership
    if thing.app.user != request.user:
        data['error'] = 'The Device with ID "{}" does not exists or you do not have access rights'.format(tid)
        return render(request, 'error.html', {'data': data})   

    # Change name if we have to:
    if edit =='name' and name:
        logger.debug('Changing device "{}" name to: {}'.format(thing.tid, name))
        thing.name=name
        thing.save()

    # Install App if we have to
    if data['action'] == 'install' and confirmed:
        if thing.app_set_via != 'backend':
            data['error'] = 'Error, the App for Thing "{}" was setup on the Thing itself and a new one cannot be installed'.format(thing.tid)
            return render(request, 'error.html', {'data': data})
        
        new_app_intaid = confirmed
                  
        logger.info('Will install App "{}" on thing "{}"'.format(new_app_intaid, thing.tid))
        
        # Get the App to install:
        try:
            new_app = App.objects.get(id=new_app_intaid, user=request.user)
        except Thing.DoesNotExist:
            data['error'] = 'The new App to install with internal ID "{}" does not exists or you do not have access rights'.format(new_app_intaid)
            return render(request, 'error.html', {'data': data})   

        # Set new App on the Thing 
        thing.app  = new_app
        thing.pool = new_app.default_pool
        thing.save()
        
        # Redirect to a fresh dashboard
        return HttpResponseRedirect('/dashboard_thing/?tid={}&intaid={}'.format(thing.tid, new_app_intaid))

    # Uninstall App if we have to
    if data['action'] == 'uninstall' and confirmed:
        if thing.app_set_via != 'backend':
            data['error'] = 'Error, the App for Thing "{}" was setup on the Thing itself and cannot be uninstalled'.format(thing.tid)
            return render(request, 'error.html', {'data': data})      
        logger.info('Will uninstall App on thing "{}"'.format(thing.tid))

        # Get the "NoneApp" for this user, and if it does not exist, create it.
        try:
            none_app = App.objects.get(user=request.user, aid='00000000-0000-0000-0000-000000000000')
        except App.DoesNotExist:
            none_app = create_none_app(request.user)

        # Set new (None) App on the Thing 
        thing.app  = none_app
        thing.pool = none_app.default_pool
        thing.save()
        
        # Redirect to a fresh dashboard
        return HttpResponseRedirect('/dashboard_thing/?tid={}&intaid={}'.format(thing.tid, none_app.id))

    # Delete (remove) a Thing
    if data['action'] == 'remove' and confirmed:
        logger.info('Removing TID "{}" '.format(thing.tid))
        data['tid'] = thing.tid
        try:
            WorkerMessageHandler.delete(aid=thing.app.aid, tid=thing.tid)
        except Exception as e:
            data['error'] = 'Error in deleting Thing with ID "{}": {}'.format(thing.tid, e)
            return render(request, 'error.html', {'data': data})
        else:
            try: 
                ManagementMessage.objects.filter(tid=thing.tid).delete()
            except Exception as e:
                logger.error('Error when deleting management messages for tid "{}"'.format(thing.tid))
            thing.delete()
 
            return render(request, 'dashboard_thing_deleted.html', {'data': data})

    # If a pool is set get it, and change
    if pool_name:
        try:
            thing.pool = Pool.objects.get(app=thing.app, name=pool_name)
            thing.save()
        except Pool.DoesNotExist:
            data['error'] = 'The pool named "{}" does not exists'.format(pool_name)
            return render(request, 'error.html', {'data': data})             
    
    # Get last worker messages
    last_worker_msgs=[]
    try: 
        
        last_worker_msgs_or = WorkerMessageHandler.get(aid=thing.app.aid, tid=thing.tid, last=3)
        for item in last_worker_msgs_or:
            
            # Fix time
            item.ts = str(item.ts.astimezone(profile_timezone)).split('.')[0]
            
            # Convert from json to string
            item.data = str(item.data)

            # Truncate if too long
            if len(item.data) >= 150:
                item.data = str(item.data[0:150]) + '...'
                
            last_worker_msgs.append(item)

    except Exception as e:
        logger.error('Error when looping over worker messages for the dashboard: {}'.format(e))

    data['last_worker_msgs'] = last_worker_msgs
    
    # Get last management messages
    last_management_msgs = []
    try: 
        last_management_msgs = ManagementMessage.objects.filter(tid=thing.tid, aid=thing.app.aid).order_by('ts')[:3].reverse()
        for msg in last_management_msgs:
            msg.ts = str(msg.ts.astimezone(profile_timezone)).split('.')[0]
        
    except:
        logger.error('Error when looping over management messages for the dashboard: {}'.format(e))
        
    data['last_management_msgs'] = last_management_msgs

    # Load session
    try:
        session = Session.objects.filter(thing=thing).latest('last_contact')
        data['session'] = session
        session.duration = str(session.last_contact-session.started).split('.')[0]
        if session.duration.startswith('0'):
            session.duration = '0'+session.duration
    except:
        data['session'] = None 
    else:
        
        # Compute status
        deltatime_from_last_contact_s = time.time() - s_from_dt(session.last_contact) #session.last_contact 
        data['connection_status'] = '<font color="red">OFFLINE</font>'
        data['thing_status'] = 'OFFLINE'
        try:
            if deltatime_from_last_contact_s < int(thing.pool.settings.management_interval) + settings.CONTACT_TIMEOUT_TOLERANCE:
                data['connection_status'] = '<font color="limegreen">ONLINE</font>'
                data['thing_status']  = 'ONLINE'

        except:
            pass
        try:
            if deltatime_from_last_contact_s < int(thing.pool.settings.worker_interval) + settings.CONTACT_TIMEOUT_TOLERANCE:
                data['connection_status'] = '<font color="limegreen">ONLINE</font>'
                data['thing_status']  = 'ONLINE'
        except:
            pass

        # Formatting tricks
        session.last_contact = str(session.last_contact.astimezone(profile_timezone)).split('.')[0]
        if session.last_pythings_status.startswith('Ok:'):
            session.last_pythings_status = 'OK'
    
        # Format worker traceback if any
        session.last_worker_status_traceback = None
        try:
            if session.last_worker_status.startswith('KO: '):
                pieces = session.last_worker_status.replace('(Traceback', '\nTraceback').split('\n') 
                sub_pieces = pieces[0].split(' ')
                session.last_worker_status = sub_pieces[0] + ' ' + sub_pieces[1] + ': ' + ' '.join(sub_pieces[2:])
                session.last_worker_status_traceback = '\n'.join(pieces[1:])[:-1]
        except:
            pass
        
        # Format management traceback if any
        session.last_management_status_traceback = None
        try:
            if session.last_management_status.startswith('KO: '):
                pieces = session.last_management_status.replace('(Traceback', '\nTraceback').split('\n') 
                sub_pieces = pieces[0].split(' ')
                session.last_management_status = sub_pieces[0] + ' ' + sub_pieces[1] + ': ' + ' '.join(sub_pieces[2:])
                session.last_management_status_traceback = '\n'.join(pieces[1:])[:-1]
        except:
            pass

    # Prepare data for the plots: parse last messages json contents, and if float add to the data for the plots    
    if from_str and to_str:
        
        # Parse from
        from_str_date_part, from_str_time_part = from_str.split(' ')      
        from_day, from_month, from_year = from_str_date_part.split('/')
        from_hour, from_minute = from_str_time_part.split(':')
        from_dt = dt(int(from_year), int(from_month), int(from_day), int(from_hour), int(from_minute), 0, tzinfo=timezonize(request.user.profile.timezone))

        # Parse to
        to_str_date_part, to_str_time_part = to_str.split(' ')      
        to_day, to_month, to_year = to_str_date_part.split('/')
        to_hour, to_minute = to_str_time_part.split(':')
        to_dt = dt(int(to_year), int(to_month), int(to_day), int(to_hour), int(to_minute), 0, tzinfo=timezonize(request.user.profile.timezone))

    elif from_t and to_t:
        from_dt = dt_from_s(float(from_t)) 
        to_dt   = dt_from_s(float(to_t)) 

    else:
        # Set "to" to NOW
        to_dt   = datetime.datetime.now()

        if last == '1m':
            from_dt = to_dt - datetime.timedelta(minutes=1)
        
        elif last == '10m':
            from_dt = to_dt - datetime.timedelta(minutes=10)
        
        elif last == '1h':
            from_dt = to_dt - datetime.timedelta(minutes=60)
        
        elif last == '1d':
            from_dt = to_dt - datetime.timedelta(days=1)
            
        elif last == '1W':
            from_dt = to_dt - datetime.timedelta(days=7)
        
        elif last == '1M':
            from_dt = to_dt - datetime.timedelta(days=31)
        
        elif last == '1Y':
            from_dt = to_dt - datetime.timedelta(days=365)
           
        else:
            # Default to last is 1 hour
            last    = '1h'
            from_dt = to_dt - datetime.timedelta(minutes=60)
    
    # Now set from_t and to_t
    data['from_t'] = s_from_dt(from_dt)
    data['to_t'] = s_from_dt(to_dt)

    # Add timezone if not already present
    try:
        from_dt = pytz.UTC.localize(from_dt)
    except ValueError:
        pass
    try:
        to_dt = pytz.UTC.localize(to_dt)
    except ValueError:
        pass        
    
    # Move to right timezone
    from_dt = from_dt.astimezone(profile_timezone)
    to_dt = to_dt.astimezone(profile_timezone)
    
    data['last'] = last
    data['from_dt'] = from_dt
    data['to_dt']   = to_dt
    data['from_dt_str'] = str(from_dt)
    data['to_dt_str']   = str(to_dt)
    
    data['from_dt_utcfake_str'] = str(from_dt.replace(tzinfo=pytz.UTC))
    data['to_dt_utcfake_str']   = str(to_dt.replace(tzinfo=pytz.UTC))
    
    # Get messages from DB
    messages = []
    try:
        messages = WorkerMessageHandler.get(aid=thing.app.aid, tid=thing.tid, from_dt=from_dt, to_dt=to_dt)
    except Exception as e:
        logger.error(format_exception(e))
     
    # Prepare data for Dygraphs
    total_messages = 0
    for message in messages:

        # Increment message counter
        total_messages += 1
        
        # Load content
        content = message.data

        if not content:
            continue

        # Load timestamp
        ts = message.ts.astimezone(profile_timezone)

        timestamp_dygraphs = '{}/{:02d}/{:02d} {:02d}:{:02d}:{:02d}'.format(ts.year, ts.month, ts.day, ts.hour, ts.minute,ts.second)
        #timestamp_dygraphs = int(s_from_dt(ts)*1000)

        # Porcess all the message keys              
        for key in content:

            # Try loading as numeric value
            try:
                metric_num_value = float(content[key])
            except:
                continue

            # Append data
            try:
                data['timeseries'][key].append((timestamp_dygraphs, metric_num_value, ts))
            except KeyError:
                data['metrics'][key] = key   
                data['timeseries'][key] = []
                data['timeseries'][key].append((timestamp_dygraphs, metric_num_value, ts))

    # Set total messages
    data['total_messages'] = total_messages

    # Do we have to aggregate?
    if total_messages > 10000:
        logger.debug('Too many messages, we need to aggregate.')

        aggrgeate_by = 10**len(str(int(total_messages/10000.0)))
        data['aggregated'] = True
        data['aggregate_by'] = aggrgeate_by
        data['total_messages_aggregated'] = int(total_messages/aggrgeate_by)
        data['timeseries_aggregated']={}
        for key in data['timeseries']:
            if key not in data['timeseries_aggregated']:
                data['timeseries_aggregated'][key] = []
    
            # Support vars
            metric_avg = 0 
            metric_min = None
            metric_max = None
            start_time_dt = None
            end_time_dt   = None
            
            # Loop and aggregate data
            for i, entry in enumerate(data['timeseries'][key]):
                
                # Start time
                if start_time_dt is None:
                    start_time_dt = entry[2]
                
                # Avg
                metric_avg += entry[1]
                
                # Min
                if metric_min is None or entry[1] < metric_min:
                    metric_min = entry[1]
                
                # Max
                if metric_max is None or entry[1] > metric_max:
                    metric_max = entry[1]
                
                if (i+1) % aggrgeate_by ==0:
                    
                    # Append aggregated data
                    end_time_dt = entry[2]
                    avg_time_dt = dt_from_s(s_from_dt(start_time_dt) +  ((s_from_dt(end_time_dt) - s_from_dt(start_time_dt))/2)).astimezone(profile_timezone)
                    timestamp_dygraphs_avg = '{}/{:02d}/{:02d} {:02d}:{:02d}:{:02d}'.format(avg_time_dt.year, avg_time_dt.month, avg_time_dt.day, avg_time_dt.hour, avg_time_dt.minute, avg_time_dt.second)
                    data['timeseries_aggregated'][key].append((timestamp_dygraphs_avg, metric_avg/aggrgeate_by, metric_min, metric_max))
                    
                    # Reset counters
                    metric_avg = 0 
                    metric_min = None
                    metric_max = None
                    start_time_dt = None
    
        # Reassign series
        del data['timeseries']
        data['timeseries'] = data['timeseries_aggregated']
        logger.debug('Done aggregating')

    # Load last sessions
    try:
        count =0
        sessions = Session.objects.filter(thing=thing).order_by('-last_contact')[0:3]
        for session in sessions:
            count  += 1
            session.count = count
            session.duration = str(session.last_contact-session.started)
            if '.' in session.duration:
                session.duration=session.duration.split('.')[0]
            session.started = str(session.started.astimezone(profile_timezone)).split('.')[0]
            session.last_contact = str(session.last_contact.astimezone(profile_timezone)).split('.')[0]
            
            # Format worker traceback if any
            session.last_worker_status_traceback = None
            try:
                if session.last_worker_status.startswith('KO: '):
                    pieces = session.last_worker_status.replace('(Traceback', '\nTraceback').split('\n') 
                    sub_pieces = pieces[0].split(' ')
                    session.last_worker_status = sub_pieces[0] + ' ' + sub_pieces[1] + ': ' + ' '.join(sub_pieces[2:])
                    session.last_worker_status_traceback = '\n'.join(pieces[1:])[:-1]
            except:
                pass
            
            # Format management traceback if any
            session.last_management_status_traceback = None
            try:
                if session.last_management_status.startswith('KO: '):
                    pieces = session.last_management_status.replace('(Traceback', '\nTraceback').split('\n') 
                    sub_pieces = pieces[0].split(' ')
                    session.last_management_status = sub_pieces[0] + ' ' + sub_pieces[1] + ': ' + ' '.join(sub_pieces[2:])
                    session.last_management_status_traceback = '\n'.join(pieces[1:])[:-1]
            except:
                pass

        data['sessions'] = sessions

    except:
        data['sessions'] = None
    
    # Enumerate the pools for this application
    data['pools'] = []
    for pool in Pool.objects.filter(app=thing.app):
        data['pools'].append(pool)
    
    # Ok, render       
    return render(request, 'dashboard_thing.html', {'data': data})


#===========================
#  Session Dashboard view
#===========================

@private_view
def dashboard_thing_sessions(request):

    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)
    tid = request.GET.get('tid',None)
    data['tid'] = tid
    data['orpool'] = request.GET.get('orpool', None)

    intaid = request.GET.get('intaid',None)
    if not intaid:
        intaid = request.POST.get('intaid',None)
    data['intaid'] = intaid

    start = request.GET.get('start', None)
    end = request.GET.get('end', None)
    
    if start is not None:
        start = int(start)
        end   = start + 10
    elif end is not None:
        end = int(end)
        start = end-10
        if start<0: start = 0
    else:
        start = 0
        end   = 10
    data['start'] = start
    data['end']   = end
    
    # Get App
    try:
        app = App.objects.get(id=intaid, user=request.user)
    except App.DoesNotExist:
        data['error'] = 'The App with Internal ID "{}" does not exists or you do not have access rights'.format(intaid)
        return render(request, 'error.html', {'data': data})   

    # Get Thing
    try:
        thing = Thing.objects.get(tid=tid, app=app)
    except Thing.DoesNotExist:
        data['error'] = 'The Thing with ID "{}" does not exists or you do not have access rights'.format(tid)
        return render(request, 'error.html', {'data': data})   
    data['thing'] = thing

    # Load sessions
    try:
        count  = 0
        sessions = Session.objects.filter(thing=thing).order_by('-last_contact')[start:end]
        for session in sessions:
            count += 1
            session.count = count
            session.duration = session.last_contact-session.started
            session.started = str(session.started.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
            session.last_contact = str(session.last_contact.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
                
            # Format worker traceback if any
            session.last_worker_status_traceback = None
            try:
                if session.last_worker_status.startswith('KO: '):
                    pieces = session.last_worker_status.replace('(Traceback', '\nTraceback').split('\n') 
                    sub_pieces = pieces[0].split(' ')
                    session.last_worker_status = sub_pieces[0] + ' ' + sub_pieces[1] + ': ' + ' '.join(sub_pieces[2:])
                    session.last_worker_status_traceback = '\n'.join(pieces[1:])[:-1]
            except:
                pass
            
            # Format management traceback if any
            session.last_management_status_traceback = None
            try:
                if session.last_management_status.startswith('KO: '):
                    pieces = session.last_management_status.replace('(Traceback', '\nTraceback').split('\n') 
                    sub_pieces = pieces[0].split(' ')
                    session.last_management_status = sub_pieces[0] + ' ' + sub_pieces[1] + ': ' + ' '.join(sub_pieces[2:])
                    session.last_management_status_traceback = '\n'.join(pieces[1:])[:-1]
            except:
                pass

        data['sessions'] = sessions
    except:
        data['sessions'] = None

    # Ok, render       
    return render(request, 'dashboard_thing_sessions.html', {'data': data})


#===========================
#  Message Dashboard view
#===========================

@private_view
def dashboard_thing_messages(request):
 
    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)

    tid = request.GET.get('tid',None)
    if not tid:
        tid = request.POST.get('tid',None)
    data['tid'] = tid

    intaid = request.GET.get('intaid',None)
    if not intaid:
        intaid = request.POST.get('intaid',None)
    data['intaid'] = intaid
            
    data['orpool'] = request.GET.get('orpool', None)
    if not data['orpool']:
        data['orpool'] = request.POST.get('orpool', None)
        
    data['type'] = request.GET.get('type', None)
    if not data['type']:
        data['type'] = request.POST.get('type', None)

    pagination = request.GET.get('pagination', 100) 

    # Force a pagination of 10 messages for the management
    if data['type']=='management':
        pagination=10

    start = request.GET.get('start', None)
    end = request.GET.get('end', None)

    if start is not None:
        start = int(start)
        end   = start + pagination
    elif end is not None:
        end = int(end)
        start = end-pagination
        if start<0: start = 0
    else:
        start = 0
        end   = pagination

    # Get App
    try:
        app = App.objects.get(id=intaid, user=request.user)
    except App.DoesNotExist:
        data['error'] = 'The App with Internal ID "{}" does not exists or you do not have access rights'.format(intaid)
        return render(request, 'error.html', {'data': data})   

    # Get Thing
    try:
        thing = Thing.objects.get(tid=tid, app=app)
    except Thing.DoesNotExist:
        data['error'] = 'The Thing with ID "{}" does not exists or you do not have access rights'.format(tid)
        return render(request, 'error.html', {'data': data})   
    data['thing'] = thing

    data['messages'] = []

    if data['type']=='worker':
        
        # Load worker messages
        try:
            for msg in WorkerMessageHandler.get(aid=thing.app.aid, tid=thing.tid, last=100):
                
                # Fix time
                msg.ts = str(msg.ts.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
                
                # Convert from json to string
                msg.data = str(msg.data)

                # Truncate if too long
                if len(msg.data) >= 150:
                    msg.data = str(msg.data[0:150]) + '...'
                
                data['messages'].append(msg)
        except Exception as e:
            logger.debug('Error: {}'.format(e))
            pass
                 
    elif data['type'] == 'management':
        
        # Create new message if we are requested to do so
        new_msg = request.POST.get('new_msg',None)
        data['generated_uuid'] = str(uuid.uuid4())
        generated_uuid = request.POST.get('generated_uuid',None)
        
        if new_msg and generated_uuid:
            # Does a message already exists?
            try:
                ManagementMessage.objects.get(tid=thing.tid, uuid=generated_uuid)
            except:
                ManagementMessage.objects.create(aid=thing.app.aid, tid=thing.tid, data=new_msg, uuid=generated_uuid)
     
        # Load management messages
        try:
            for msg in ManagementMessage.objects.filter(tid=thing.tid, aid=thing.app.aid, type='APP').order_by('-ts')[start:end]:
                msg.ts = str(msg.ts.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
                data['messages'].append(msg)
        except:
            pass
            
    else:
        data['error'] = 'The value "{}" for message type is not valid.'.format(type)
        return render(request, 'error.html', {'data': data})

    # Set pagination
    data['start'] = start
    data['end']   = end if len(data['messages'])>=pagination else 0
    
    # Ok, render      
    return render(request, 'dashboard_thing_messages.html', {'data': data})


#===========================
#  Remote Shell view
#===========================

@private_view
def dashboard_thing_shell(request):

    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)

    intaid = request.GET.get('intaid',None)
    if not intaid:
        intaid = request.POST.get('intaid',None)

    tid = request.GET.get('tid',None)
    if not tid:
        tid = request.POST.get('tid',None)
    data['tid'] = tid
            
    data['orpool'] = request.GET.get('orpool', None)
    if not data['orpool']:
        data['orpool'] = request.POST.get('orpool', None)
        
    # Get App
    try:
        app = App.objects.get(id=intaid)
    except App.DoesNotExist:
        data['error'] = 'The app with internal id "{}" does not exists'.format(intaid)
        return render(request, 'error.html', {'data': data})   

    # Get Thing
    try:
        thing = Thing.objects.get(tid=tid, app=app)
    except Thing.DoesNotExist:
        data['error'] = 'The thing with tid "{}" does not exists'.format(tid)
        return render(request, 'error.html', {'data': data})   
    data['thing'] = thing

    data['messages'] = []

    # Create new message if we are requested to do so
    new_msg = request.POST.get('new_msg',None)
    if not new_msg:
        new_msg = request.GET.get('new_msg',None)
    data['generated_uuid'] = str(uuid.uuid4())
    generated_uuid = request.POST.get('generated_uuid',None)
    if not generated_uuid:
        generated_uuid = request.GET.get('generated_uuid',None)

    if new_msg and generated_uuid:
        
        # Does a message already exists?
        try:
            ManagementMessage.objects.get(tid=thing.tid, uuid=generated_uuid)
        except:
            ManagementMessage.objects.create(aid=thing.app.aid, tid=thing.tid, data=new_msg, uuid=generated_uuid, type='CMD', thing=thing)
 
    # Load CMD management messages (filter by Thing as they are linked to the thing and not a specific app)
    for msg in ManagementMessage.objects.filter(thing=thing, type='CMD').order_by('ts'):
        msg.ts = str(msg.ts.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]
        if msg.reply:
            msg.reply_clean = msg.reply.rstrip('\n')
            msg.reply_clean = msg.reply_clean.rstrip('\n\r')
        else:
            msg.reply = None 
        data['messages'].append(msg)

    # Ok, render       
    return render(request, 'dashboard_thing_shell.html', {'data': data})
        

#===========================
#  New App view
#===========================

@private_view
def new_app(request):

    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)
    data['app'] = None
    data['lastsessions'] = []
    data['pool'] = None
    data['pythings_versions'] = settings.OS_VERSIONS
             
    # Get name form GET request
    app_name = request.POST.get('app_name',None)
    pythings_version = request.POST.get('pythings_version',None)
    management_interval = request.POST.get('management_interval',None)
    worker_interval = request.POST.get('worker_interval',None)
    
    # Set if to use the latest app version or not
    use_latest_app_version = request.POST.get('uselatest', False)
    if use_latest_app_version:
        use_latest_app_version = True

    if app_name:
        create_app_helper(name                = app_name,
                          user                = request.user,
                          aid                 = None,
                          management_interval = management_interval,
                          worker_interval     = worker_interval,
                          pythings_version    = pythings_version,
                          use_latest_app_version = use_latest_app_version)
        data['app_name'] = app_name

    return render(request, 'new_app.html', {'data': data})


#===========================
#  App code editor view
#===========================

@private_view
def dashboard_app_code_editor(request, embed=False):

    # Init data
    data={}
    data['user']  = request.user
    data['profile'] = Profile.objects.get(user=request.user)
    data['app'] = None
    data['embed'] = '_embed' if embed else ''

    # Get data
    intaid    = request.GET.get('intaid', None)
    cid       = request.GET.get('cid', None)
    fileid    = request.GET.get('fileid', None)
    do_commit = request.GET.get('commit', None)
    savednew  = request.GET.get('savednew', False)
    tagop     = request.GET.get('tagop', None)
    tagname   = request.GET.get('tagname', None)
    openworker = booleanize(request.GET.get('openworker', False))
    
    data['savednew'] = savednew
    data['tagop'] = tagop
    data['tagname'] = tagname
    
    if savednew != False and savednew.upper() != 'FALSE':
        savednew=True

    # Fix None
    if cid is not None and cid.upper() == 'NONE':
        cid = None
        
    if savednew:
        cid=None
    data['cid'] = cid

    # Get the application
    try:
        app = App.objects.get(id=intaid, user=request.user)
        data['app'] = app
    except App.DoesNotExist:
        data['error'] = 'The app does not exist or you don\'t have access rights'
        return render(request, 'error.html', {'data': data})

    # Do we have to open the worker by default?
    if openworker:
        file = File.objects.filter(app=app,name='worker_task.py').order_by('-ts').first()
        fileid = file.id

    # Get the file if set
    if fileid:
        try:
            fileid = int(fileid)
        except:
            data['error'] = 'Cannot properly handle file id'
            return render(request, 'error.html', {'data': data})
        try:
            logger.debug('Trying to load file %s for app %s', fileid,app)
            file = File.objects.get(app=app,id=fileid)
            
            # Switch to new version if just saved
            if savednew:
                file = File.objects.get(app=app,name=file.name,committed=False)
                fileid = file.id

            data['file'] = file                
        except File.DoesNotExist:
            # TODO: create empty file, not raise
            data['error'] = 'Cannot find the version of the specified file'
            return render(request, 'error.html', {'data': data})

    # Get last or required commit. This is always the base for now.
    latest_commit = Commit.objects.filter(app=app).latest('ts')
    try:
        if cid is not None and cid != latest_commit.cid:
            commit = Commit.objects.get(app=app,cid=cid)
            data['editable'] = False
        else:
            commit = latest_commit
            data['editable'] = True
    except:
        data['error'] = 'Cannot find commit with cid "{}"'.format(cid)
        return render(request, 'error.html', {'data': data})
                             
    # Load uncommitted files, if we don't have specified a particular cid
    global_app_uncommitted_files = File.objects.filter(app=app,committed=False)
    data['global_app_uncommitted_files'] = global_app_uncommitted_files
    if cid is None:
        uncommitted_files = global_app_uncommitted_files
    else:
        uncommitted_files = []

    # Create a new commit if required
    if do_commit:
        if len(File.objects.filter(app=app,committed=False)) > 0:
            newcommit = Commit.objects.create(app=app)
            committed_files=[]
            
            # First, newcommit the unnewcommitted
            for file in uncommitted_files:
                newcommit.files.add(file)
                file.committed=True
                file.save()
                committed_files.append(file.path+'/'+file.name)
            
            # Then, all the last commit app's files (if not already committed in newer version)
            for file in commit.files.all():
                if file.path+'/'+file.name in committed_files:
                    pass
                else:
                    newcommit.files.add(file)

            newcommit.valid=True
            newcommit.save()
            
            # Reload uncommitted files
            uncommitted_files = File.objects.filter(app=app,committed=False)
            
            # If we had to commit but we still have uncommitted files, somethign went wrong
            if uncommitted_files:
                data['error'] = 'Something went wrong in committing, some files are still not committed.'
                return render(request, 'error.html', {'data': data})

            # Remap commit to the new one
            commit = newcommit

            # Get all the pools for this app
            for pool in Pool.objects.filter(app=app):
             
                # Update version only on development if set so
                if pool.use_latest_app_version and pool.development:
                    pool.settings.app_version = commit.cid
                    pool.settings.save() 
         
                    # Also, for each thing in the pool with custom settings, update the version
                    for thing in Thing.objects.filter(pool=pool, use_custom_settings=True):
                        thing.version = commit.cid
                        thing.save()
                    
            data['cid'] = commit.cid
            data['global_app_uncommitted_files'] = []

    # Do we have to tag the commit?
    if tagop in ['create','edit'] and tagname is not None:
        commit.tag=tagname
        commit.save()

        # Get all the pools for this app
        for pool in Pool.objects.filter(app=app):

            # Update version only on staging if set so
            if pool.use_latest_app_version and pool.staging:
                pool.settings.app_version = commit.cid
                pool.settings.save() 
     
                # Also, for each thing in the pool with custom settings, update the version
                for thing in Thing.objects.filter(pool=pool, use_custom_settings=True):
                    thing.version = commit.cid
                    thing.save()

    # Set commit in data
    data['commit'] = commit

    # Set commit status
    if uncommitted_files:
        data['commit_status'] = 'UN'
    else:
        data['commit_status'] = 'EV'
        
    # Get all commits
    data['commits'] = Commit.objects.filter(app=app).order_by('-ts')

    # Create data files lists for app_files, commited and uncommitted
    app_files = []
    for file in commit.files.all():
        app_files.append(file)
    for file in uncommitted_files:
        app_files.append(file)
    data['app_files'] = app_files
        
    data['app_committed_files'] = {}
    data['app_uncommitted_files'] = {}
    for file in commit.files.all():
        data['app_committed_files'][file.name]=file.id
    for file in uncommitted_files:
        data['app_uncommitted_files'][file.name]=file.id
    data['fileid'] = fileid

    # Fix timestamp for file
    if 'file' in data and data['file']:
        data['file'].ts= str(data['file'].ts.astimezone(timezonize(get_timezone_from_request(request)))).split('.')[0]

    # Render
    return render(request, 'dashboard_app_code_editor.html', {'data': data})


def dashboard_app_code_editor_embed(request):
    return dashboard_app_code_editor(request, embed=True)


#===========================
#  Apps list view
#===========================

@private_view
@xframe_options_exempt
def list_apps(request):

    # Init data
    data={}
    data['user'] = request.user
    data['apps'] = [] 

    # Enumerate applications
    for app in App.objects.filter(user=request.user):
        data['apps'].append(app)

    return render(request, 'list_apps.html', {'data': data})


#==========================
#  Main view
#==========================

@public_view
def main(request):

    # Init data
    data={}
    data['user'] = request.user
    data['menu'] = request.GET.get('menu', 'closed')
    
    if os.path.isfile('/opt/code/backend/pythings_app/templates/custom/main.html'):
        return render(request, 'custom/main.html', {'data': data})
    else:
        return HttpResponseRedirect('/dashboard')  


#==========================
#  Terms view
#==========================

@public_view
def terms(request):

    # Init data
    data={}
    data['user'] = request.user

    return render(request, 'terms.html', {'data': data})


#==========================
#  Privacy view
#==========================

@public_view
def privacy(request):

    # Init data
    data={}
    data['user'] = request.user

    return render(request, 'privacy.html', {'data': data})



#==================================================
#
#              E X T R A    V I E W S
#
#==================================================



