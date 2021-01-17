import time
import json
import logging

# Django imports
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response

# Backend imports
from ..common.utils import format_exception
from ..common.time import dt_from_str, dt_from_s
from ..common.returns import ok200, error400, error401, error404, error500
from ..common.returns import ok200rest, error400rest, error401rest, error404rest, error500rest
from .models import ManagementMessage, App, Thing, File, Profile, WorkerMessageHandler

# Setup logging
logger = logging.getLogger(__name__)

#==============================
#  Pythings Web auth
#==============================

def pythings_web_authenticate(request, caller):
    
    # Get data
    user = request.user if request.user.is_authenticated() else None
    username = request.data.get('username', None)
    password = request.data.get('password', None)
    apikey   = request.data.get('apikey', None)

    try:         
        # Try standard user authentication
        if user:
            return user 
        
        # Try username/password  authentication
        elif username or password:
            
            # Check we got both
            if not username:
                return error400rest(caller=caller, error_msg='Got empty username')
            if not password:
                return error400rest(caller=caller, error_msg='Got empty password')

            # Authenticate
            user = authenticate(username=username, password=password)
            if not user:
                return error401rest(caller=caller, error_msg='Wrong username/password')  
            else:
                return user

        # Try api key authentication 
        elif apikey:
            try:
                profile = Profile.objects.get(apikey=apikey)
            except Profile.DoesNotExist:
                return error400rest(caller=caller, error_msg='Wrong API key')
            return profile.user
        else:
            return error401rest(caller=caller, error_msg='This is a private API. Login or provide username/password or apikey')
   
    except Exception as e:
        logger.error(format_exception(e, debug=False))
        return error500rest(caller=caller, error_msg='Got exception in processing request: ' + str(e))



#==============================
#  Base public Web API class
#==============================

class PublicWebAPI(APIView):
    '''Base public API class'''

    def post(self, request):
        return self._post(request)

    def get(self, request):
        return self._get(request)

    def log(self, level, msg, *strings):
        logger.log(level, self.__class__.__name__ + ': ' + msg, *strings)


#==============================
#  Base private Web API class
#==============================

class PrivateWebAPI(APIView):
    '''Base private API class'''

    # POST
    def post(self, request):

        # Authenticate using pythings authentication
        user = pythings_web_authenticate(request, self)
        
        # If we got a response (so an error) return it
        # TODO: change this approach...
        if isinstance(user, Response):
            return user
        else:
            self.user = user
        
        # Call API logic
        return self._post(request)

    
    # GET  
    def get(self, request):
        
        # Authenticate using pythings authentication
        user = pythings_web_authenticate(request, self)
        
        # If we got a response (so an error) return it
        # TODO: change this approach...
        if isinstance(user, Response):
            return user
        else:
            self.user = user
        
        # Call API logic
        return self._get(request)


    # Log utility
    def log(self, level, msg, *strings):
        logger.log(level, self.__class__.__name__ + ': ' + str(self.user) + ': ' + msg, *strings)


#==============================
#  Save code from Web Editor
#==============================

class api_code_editor_uploadfile(PrivateWebAPI):
    '''Api for uploading a file fro the Web code editor'''

    def _post(self, request):

        # Obtain values
        name = request.data.get('name', None)
        content = request.data.get('content', None)
        version = request.data.get('version', None)
        intaid = request.data.get('intaid', None)

        # If no version set, by default we use the epoch numbering
        if not version:
            import calendar 
            version = str(calendar.timegm(time.gmtime()))

        # Sanity checks
        if not intaid:
            return error400(caller=self, error_msg='Got empty "intaid"')     
        if not name:
            return error400(caller=self, error_msg='Got empty "name"')     
        if not content:
            return error400(caller=self, error_msg='Got empty "content"')   

        # Get the app
        logger.info('Getting app for internal aid="{}"'.format(intaid))
        try:   
            app = App.objects.get(id=intaid)
        except App.DoesNotExist:
            return error401(caller=self, error_msg='Error: app internal id "{}" is not valid.'.format(intaid))
        
        # Check rights
        if app.user != self.user:
            return error400(caller=self, error_msg='Not valid app or no access rights.{}-{}'.format(app.user,self.user)) 

        try:
            try:
                # If file exists and is not commited, just updated the content:
                files = File.objects.filter(name=name, app=app, committed=False)
                if len(files) == 0:
                    raise File.DoesNotExist
                if len(files)>1:
                    return error500(caller=self, error_msg='Found more than one file to commit (found {})'.format(len(files))) 
                file = files[0] # Mandatory step
                file.content=content
                file.ts=timezone.now()
                file.save()
            except File.DoesNotExist:
                # Otherwise, create new not committed file.
                File.objects.create(name=name, app=app, content=content, committed=False)            

        except Exception as e:
            logger.error(format_exception(e))
            return error500(caller=self, error_msg='Got error: {}'.format(str(e))) 
        
        return ok200()


#==============================
#  Management APIs
#==============================

class api_msg_management_new(PrivateWebAPI):
    '''API for creating a new management message'''

    def _post(self, request):

        # Obtain values
        msg = request.data.get('msg', None)
        tid = request.data.get('tid', None)

        # Sanity checks
        if not tid:
            return error400rest(caller=self, error_msg='Got empty "tid"')     
        if not msg:
            return error400rest(caller=self, error_msg='Got empty "msg"')

        # Load thing for given TID
        try:   
            thing = Thing.objects.get(tid=tid)
        except Thing.DoesNotExist:
            return error400rest(caller=self, error_msg='Not existent Thing or no access rights')
                
        # Check authorization on the thing
        if self.user != thing.app.user:
            return error400rest(caller=self, error_msg='Not existent Thing or no access rights')
            logger.info('SECURITY: Denied access for thing with tid="{}" for user={}"'.format(tid, self.user))

        # Store message
        management_message = ManagementMessage.objects.create(aid=thing.app.aid, tid=tid, data=msg)

        # Ok, return
        return ok200rest(caller=self, data={'mid': management_message.uuid})


class api_msg_management_get(PrivateWebAPI):
    '''API for getting a specific management message'''

    def _post(self, request):

        # Obtain values
        mid = request.data.get('mid', None)

        # Sanity checks
        if not mid:
            return error400rest(caller=self, error_msg='Got empty mid')     

        # Load message for given MID
        try:   
            management_message = ManagementMessage.objects.get(uuid=mid)
        except ManagementMessage.DoesNotExist:
            return error400rest(caller=self, error_msg='Not existent Message or no access rights')
                    
        # TODO: check authorization on the message trought AID -> App -> app.user ?
        return ok200rest(caller=self, data={'status': management_message.status,
                                            'reply': management_message.reply})


#==============================
#  Worker APIs
#==============================

class api_msg_worker_get(PrivateWebAPI):
    '''API for getting worker messages'''

    def _post(self, request):

        # Obtain values
        tid   = request.data.get('tid', None)
        _from = request.data.get('from', None)
        _to   = request.data.get('to', None)

        # Epoch?
        try:
            from_s = float(_from)
        except:
            from_s = None        
        try:
            to_s = float(_to)
        except:
            to_s = None
            
        # Datetime?
        try:
            from_dt = dt_from_str(_from)
        except:
            from_dt = None
        try:
            to_dt = dt_from_str(_to)
        except:
            to_dt = None

        # Convert to datetime and check
        if from_s:
            from_dt = dt_from_s(from_s, tz='UTC')   
        if from_dt is None:
            return error400rest(caller=self, error_msg='No from set')     
        if to_s:
            to_dt = dt_from_s(to_s, tz='UTC')   
        if to_dt is None:
            return error400rest(caller=self, error_msg='No to set')   

        # Sanity checks
        if not tid:
            return error400rest(caller=self, error_msg='Got empty tid')     
    
        # Check thing exists
        try:
            thing = Thing.objects.get(tid=tid)
        except Thing.DoesNotExist:
            return error400rest(caller=self, error_msg='Not existent Thing or no access rights')
            
        # Check access rights
        if thing.app.user != self.user:
            return error400rest(caller=self, error_msg='Not existent Thing or no access rights')
                    
        # Load messages for given TID
        worker_messages = []
        for message in WorkerMessageHandler.get(aid=thing.app.aid, tid=tid, from_dt=from_dt, to_dt=to_dt):
            worker_messages.append({'ts':message.ts, 'data':message.data})
        
        return ok200rest(caller=self, data=worker_messages)

