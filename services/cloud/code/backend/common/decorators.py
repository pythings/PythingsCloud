import inspect
import logging

# Django imports
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.conf import settings

# Backend inports
from .utils import format_exception, log_user_activity, random_username
from ..common.exceptions import ErrorMessage, ConsistencyException

# Setup logging
logger = logging.getLogger(__name__)


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
                
                # Log the exception 
                logger.error(format_exception(e))

                # Raise the exception if we are in debug mode
                if settings.DEBUG:
                    raise

                # Otherwise, mask it
                else:
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
                    
                    # Log the exception 
                    logger.error(format_exception(e))
    
                    # Raise the exception if we are in debug mode
                    if settings.DEBUG:
                        raise
    
                    # Otherwise, mask it
                    else:
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














