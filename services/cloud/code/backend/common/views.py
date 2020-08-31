

import time
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
#from common import log_user_activity, timezonize, username_hash, format_exception, os_shell
from django.contrib.auth import update_session_auth_hash
import uuid
import json
import socket
import os
import inspect
from backend import settings

from backend.base_app.models import LoginToken
from backend.common.utils import send_email, format_exception, log_user_activity, random_username

from backend.settings import MAIN_DOMAIN_NAME

# Setup logging
import logging
logger = logging.getLogger(__name__)

from backend.common.exceptions import ErrorMessage, ConsistencyException

# This is a support array used to prevent double click problems
ONGOING_SIGNUPS = {}


#=========================
#  Decorators
#=========================

# Public view
def public_view(wrapped_view):
    def public_view_wrapper(request, *argv, **kwargs):
        # -------------- START Public/private common code --------------
        log_user_activity("DEBUG", "Called", request, wrapped_view.__name__)
        try:
            
            # Try to get the templates from view kwargs
            # Todo: Python3 compatibility: https://stackoverflow.com/questions/2677185/how-can-i-read-a-functions-signature-including-default-argument-values

            argSpec=inspect.getargspec(wrapped_view)

            if 'template' in argSpec.args:
                template = argSpec.defaults[0]
            else:
                template = None
            
            # Call wrapped view
            data = wrapped_view(request, *argv, **kwargs)
            
            if not isinstance(data, HttpResponse):
                if template:
                    #logger.debug('using template + data ("{}","{}")'.format(template,data))
                    return render(request, template, {'data': data})
                else:
                    raise ConsistencyException('Got plain "data" output but no template defined in view')
            else:
                #logger.debug('using returned httpresponse')
                return data

        except Exception as e:
            if isinstance(e, ErrorMessage):
                error_text = str(e)
            else: 
                
                # Raise te exception if we are in debug mode
                if settings.DEBUG:
                    raise
                    
                # Otherwise,
                else:
                    
                    # first log the exception
                    logger.error(format_exception(e))
                    
                    # and then mask it.
                    error_text = 'something went wrong'
                    
            data = {'user': request.user,
                    'title': 'Error',
                    'error' : 'Error: "{}"'.format(error_text)}
            #logger.debug(data)
            if template:
                return render(request, template, {'data': data})
            else:
                return render(request, 'error.html', {'data': data})
        # --------------  END Public/private common code --------------        
    return public_view_wrapper

# Private view
def private_view(wrapped_view):
    def private_view_wrapper(request, *argv, **kwargs):
        if request.user.is_authenticated():
            # -------------- START Public/private common code --------------
            log_user_activity("DEBUG", "Called", request, wrapped_view.__name__)
            try:
                
                # Try to get the templates from view kwargs
                # Todo: Python3 compatibility: https://stackoverflow.com/questions/2677185/how-can-i-read-a-functions-signature-including-default-argument-values
    
                argSpec=inspect.getargspec(wrapped_view)
    
                if 'template' in argSpec.args:
                    template = argSpec.defaults[0]
                else:
                    template = None
                
                # Call wrapped view
                data = wrapped_view(request, *argv, **kwargs)
                
                if not isinstance(data, HttpResponse):
                    if template:
                        #logger.debug('using template + data ("{}","{}")'.format(template,data))
                        return render(request, template, {'data': data})
                    else:
                        raise ConsistencyException('Got plain "data" output but no template defined in view')
                else:
                    #logger.debug('using returned httpresponse')
                    return data
    
            except Exception as e:    
                if isinstance(e, ErrorMessage):
                    error_text = str(e)
                else: 
                    
                    # Raise te exception if we are in debug mode
                    if settings.DEBUG:
                        raise
                        
                    # Otherwise,
                    else:
                        
                        # first log the exception
                        logger.error(format_exception(e))
                        
                        # and then mask it.
                        error_text = 'something went wrong'
                        
                data = {'user': request.user,
                        'title': 'Error',
                        'error' : 'Error: "{}"'.format(error_text)}
                #logger.debug(data)
                if template:
                    return render(request, template, {'data': data})
                else:
                    return render(request, 'error.html', {'data': data})
            # --------------  END  Public/private common code --------------

        else:
            log_user_activity("DEBUG", "Redirecting to login since not authenticated", request)
            return HttpResponseRedirect('/login')               
    return private_view_wrapper





def login_view_template(request, redirect):
    
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
                        return data
            
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
                
                send_email(to=user.email, subject='Pythings Cloud login link', text='Hello,\n\nhere is your login link: {}/login/?token={}\n\nOnce logged in, you can go to "My Account" and change password (or just keep using the login link feature).'.format(MAIN_DOMAIN_NAME, token))
               
                # Return here, we don't want to give any hints about existing users
                data['success'] = 'Ok, you will shortly receive a login link by email (if we have your data).'
                return data
                    
                
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

                
    # All other cases, render the login page again with no other data than title
    return data


def logout_view_template(request, redirect):
    logout(request)
    return HttpResponseRedirect(redirect)

def register_view_template(request, redirect, invitation_code=None, callback=None):
    '''Register a user. Call the "callback" function with the User object just created on success
    '''

    # user var
    user = None

    # Init data
    data={}
    data['user']   = request.user
    data['status'] = None

    # Get data
    email      = request.POST.get('email', None)
    password   = request.POST.get('password', None)
    invitation = request.POST.get('invitation', None) # Verification code set for anyone

    if request.user.is_authenticated():
        return(HttpResponseRedirect(redirect))

    else:

        if email and password:
            
            # Check both email and password are set
            if not email:
                raise ErrorMessage('Missing email')
         
            if not password:
                raise ErrorMessage('Missing password')
         
            # Check if we have to validate an invitation code
            if invitation_code:
                if invitation != invitation_code:
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

                # Call the callback if any
                if callback:
                    callback(user)
                
                # Remove user from recent signups
                del ONGOING_SIGNUPS[email]
                
                return data
            
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
                    return data 

        else:
            return data





