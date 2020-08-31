import os
import json
import logging
import hashlib
import base64
import uuid
import time
import re

# Django imports
from django.http import HttpResponse
from django.utils import timezone
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

# Backend imports
from backend.common.utils import format_exception
from .models import WorkerMessageHandler, WorkerMessage, ManagementMessage, App, Thing, Session, Pool, Commit
from .common import get_total_messages, dt_from_s, get_total_devices, inc_total_messages, create_app

from .crypto_rsa import Srsa
from .crypto_aes import Aes128ecb

# Setup Logging
logger = logging.getLogger(__name__)


#=========================
# Utility functions
#=========================

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


#=========================
# Common returns
#=========================

def response(payload, status=None, caller=None, raw=False):
    #logger.info(' ** OUT ** - Preparing payload {}'.format(payload))
    if caller and caller.payload_encrypter:
        payload_encrypter = caller.payload_encrypter
    else:
        payload_encrypter = None
    
    if payload_encrypter:
        
        if raw:     
            # Payload must be string
            payload = payload_encrypter.encrypt_text(str(payload))
            #logger.info(' ** OUT ** - Returning encypted payload: {}'.format(payload))
            return HttpResponse(payload, status=status)
        else:
            # Payload must be JSON-serializable object
            payload = payload_encrypter.encrypt_text(json.dumps(payload))
            #logger.info(' ** OUT ** - Returning encypted payload: {}'.format(payload))
            return HttpResponse(payload, status=status)

    else:
        
        # If it was explicitlt asked to return RAW do so, otherwise return JSON-encoded
        if raw:
            #logger.info(' ** OUT ** - Returning not encypted raw payload: {}'.format(payload))
            return HttpResponse(payload, status=status)
        else:
            return Response(payload, status=status)


# Ok (with data)
def ok200(caller=None, data=None, raw=False):
    if raw:
        #print('caller', caller, caller.payload_encrypter)
        return response(data, status.HTTP_200_OK, caller, raw=True)
    else:
        return response(data, status.HTTP_200_OK, caller)


# Error 400
def error400(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_400_BAD_REQUEST, caller)

# Error 401
def error401(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_401_UNAUTHORIZED, caller)

# Error 404
def error404(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_404_NOT_FOUND, caller)

# Error 500
def error500(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_500_INTERNAL_SERVER_ERROR, caller)


#=========================
#  Base public API class
#=========================
class publicAPI(APIView):
    '''Base public API class'''

    def post(self, request):
        try:
            # Can we handle the data?
            try:
                # This will trigger the REST framework to parse the data and raise if errors
                # TODO: what if the payload is in wrng format but encypted?
                len(request.data)
            except Exception:
                return error400(caller=None, error_msg='Wrong data format')
            
            #logger.info(' ** IN ** - Received data: {}'.format(request.data))
            self.payload_encrypter = None
            # Handle the case of encrypted data
            encrypted = request.data.get('encrypted', None)
            if encrypted:
                token = request.data.get('token', None)
                if not token:
                    return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: token is missing.')
                
                # Obtain the key for this token
                #print ('token', token)
                try:
                    session = Session.objects.get(token=token)
                except MultipleObjectsReturned:
                    sessions = Session.objects.filter(token=token)
                    for session in sessions:
                        logger.info('Multiple sessions for {}: {}'.format(token, session))
                    session = sessions[0]
                
                # Set crypto engine            
                aes128ecb = Aes128ecb(key=int(session.key), comp_mode=True)
                self.payload_encrypter = aes128ecb
                
                # Decrypt data
                data = aes128ecb.decrypt_text(str(encrypted))
                
                # Convert to dict
                logger.info('Token="{}"; Decrypted data : "{}"'.format(token, data))
                data = json.loads(data)
                
                # Set back values in request.data
                for key in data:
                    request.data[key] = data[key]
    
            return self._post(request)
        except Exception as e:
            logger.error(format_exception(e))
            return error500(caller=None, error_msg='Hi, Pythings Cloud here. It seems like we are experiencing a problem, please try again later.')

    def get(self, request):
        try:

# TODO: Do we want payload-encrypted GETs?
#             logger.info(' ** IN ** - Received data: {}'.format(request.data))
#             self.payload_encrypter = None
#             # Handle the case of encrypted data
#             encrypted = request.data.get('encrypted', False)
#             if encrypted:
#                 token = request.data.get('token', None)
#                 if not token:
#                     return error401(caller=self, error_msg='Hi, Pythings Cloud here. Erro: token is missing.')
#                  
#                 # Obtain the key for this token
#                 session = Session.objects.get(token=token)
#                  
#                 # Set crypto engine
#                 from crypto_aes import Aes128ecb
#                 aes128ecb = Aes128ecb(key=int(session.key), comp_mode=True)
#                 self.payload_encrypter = aes128ecb
    
            return self._get(request)
        except Exception as e:
            logger.error(format_exception(e))
            return error500(caller=None, error_msg='Hi, Pythings Cloud here. It seems like we are experiencing a problem, please try again later.')


    def log(self, level, msg, *strings):
        logger.log(level, self.__class__.__name__ + ': ' + msg, *strings)



#=========================
#  Base private API class
#=========================
class privateWebAPI(APIView):
    '''Base private API class'''

    payload_encrypter = None

    def post(self, request):

        try:         
            # Check user authentication
            if not request.user.is_authenticated() and 'username' not in request.data and 'password' not in request.data:
                return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but this is a private API. Login or provide username/password.')
            
            elif not request.user.is_authenticated() or ('username' in request.data and 'password' in request.data):
                
                # logger.info 'Authenticating'
                
                # Try to authenticate
                try:
                    username = request.data["username"] # Not request.POST
                except:
                    username = None       
    
                try:
                    password = request.data["password"]
                except:
                    password = None  
        
                # Sanity checks
                if not username:
                    return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty username.')
                if not password:
                    return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty password.')
    
                # Authenticate
                user = authenticate(username=username, password=password)
                if not user:
                    return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but the username/password is not valid.')  
                else:
                    self.user = user                   
                    # Call API logic 
                    return self._post(request)
            else:
                self.user = request.user
                # Call API logic 
                return self._post(request)
                      
        except Exception as e:
            logger.error(format_exception(e))
            return error500(caller=None, error_msg='Hi, Pythings Cloud here. It seems like we are experiencing a problem, please try again later.')

    def get(self, request):
        try:         
            # Check user authentication
            if not request.user.is_authenticated() and 'username' not in request.GET and 'password' not in request.GET:
                return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but this is a private API. Login or provide username/password or token.')
            
            elif not request.user.is_authenticated() or ('username' in request.GET and 'password' in request.GET):
                
                #logger.info 'Authenticating' 
                #username = request.GET.get('username', None)
                #password = request.GET.get('username', None)
                #token    = request.GET.get('username', None)
                
                # Try to authenticate
                try:
                    username = request.GET["username"] # Not request.POST
                except:
                    username = None       
    
                try:
                    password = request.GET["password"]
                except:
                    password = None  
        
                # Sanity checks
                if not username:
                    return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty username.')
                if not password:
                    return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty password.')
    
                # Authenticate
                user = authenticate(username=username, password=password)
                if not user:
                    return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but the username/password is not valid.')  
                else:
                    self.user = user                   
                    # Call API logic 
                    return self._get(request)
            else:
                self.user = request.user
                # Call API logic 
                return self._get(request)
                      
        except Exception as e:
            logger.error(format_exception(e))
            return error500(caller=None, error_msg='Hi, Pythings Cloud here. It seems like we are experiencing a problem, please try again later.')


    def log(self, level, msg, *strings):
        logger.log(level, self.__class__.__name__ + ': ' + str(self.user) + ': ' + msg, *strings)


#=========================
#  Message upload
#=========================

class api_msg_up(privateWebAPI):
    '''Api for uploading a message'''

    def _post(self, request):

        # Obtain values
        try:
            msg = request.data["msg"]
        except:
            msg = None       
 
        try:
            tid = request.data["tid"]
        except:
            tid = None 
 
        try:
            ts = request.data["ts"]
        except:
            ts = None 
 
        # Sanity checks
        if not tid:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "tid".')     
        if not msg:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "msg".')
         
        # Handle timestamp
        # if timestamp is epoch, or epoch:ms or datetime ISO....
 
        # Store message
        if ts is not None:
            msg_up_obj, created = WorkerMessage.objects.get_or_create(aid='test-shiould-be-from-session', tid=tid, ts=ts, msg=msg)
        else:
            msg_up_obj, created = WorkerMessage.objects.get_or_create(aid='test-shiould-be-from-session', tid=tid, msg=msg)
             
        created =True
        if created:
            # Ok, return
            return ok200(caller=self, data=None)
        else:        
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but a message from this Thing ID with this timestamp already present for this user.')


class api_msg_drop(publicAPI):
    '''Api for dropping a message (in an unsecure way)'''

    def _post(self, request):

        # Get token 
        token  = request.data.get('token', None)

        # Obtain values
        msg  = request.data.get('msg', None)
        ts  = request.data.get('ts', None)

        # Sanity checks
        if not token:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     
        if not msg:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "msg".')
        
        # Handle timestamp
        # if timestamp is epoch, or epoch:ms or datetime ISO....
        if ts is not None:
            try:
                
                ts = dt_from_s(ts)
            except Exception as e:
                logger.error(e)
                return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I cannot handle this timestamp (got "{}").'.format(ts))
 
        # Try to get a session for this thing
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
        else:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        # Get the app for this thing
        if not thing.app.aid:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but this thing is not registered to any AID. This should never happen, please report to the support.')

        # Check data consumption
        total_messages, _, _, = get_total_messages(thing.app.user)
        
        
        # Limits are DISABLED for now
        #if total_messages >= thing.app.user.profile.plan_messages_limit:
        #    logger.info('LIMIT: reached messages limit for the account "{}" ({})'.format(thing.app.user.email, thing.app.user.username))
        #    return error401(caller=self, error_msg='Reached messages limit for the account! Please upgrade.')
     
        def decode_base64(data):
            """Decode base64, padding being optional.
        
            :param data: Base64 data as an ASCII byte string
            :returns: The decoded byte string.
        
            """
            missing_padding = len(data) % 4
            if missing_padding != 0:
                data += b'='* (4 - missing_padding)
            return base64.decodestring(data)

        
        # Check message size
        msg_len = len(json.dumps(msg))
        if msg_len > 1024:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Error: message too long ({} chars, maximum is 1024)'.format(msg_len))

        # Store message
        logger.info('Storing message with aid="{}", tid="{}", ts="{}", msg="{}...")'. format(thing.app.aid, thing.tid, ts, str(msg)[0:50]))

        if ts is not None:
            WorkerMessageHandler.put(aid=thing.app.aid, tid=thing.tid, ts=ts, msg=msg)
        else:
            WorkerMessageHandler.put(aid=thing.app.aid, tid=thing.tid, msg=msg)
        inc_total_messages(user=thing.app.user, worker=1)

        logger.info('Received and stored message dropped from TID={}'.format(thing.tid))
        
        return ok200(caller=self, data=None)


class api_apps_management(publicAPI):
    '''Api for dropping a message (in an unsecure way)'''

    def _post(self, request):

        # Get token 
        token  = request.data.get('token', None)

        # Sanity checks
        if not token:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     

        # Session data
        status = request.data.get('status', None)

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            if status:
                sessions[0].last_heartbeat_status=json.dumps(status)
            sessions[0].save()
        else:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found (managemet api).')

        # Get the app for this thing
        if not thing.app:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but this thing is not registered to any App. This should never happen, please report to the support.')

        # Load settings for this thing
        if thing.use_custom_settings and thing.settings:
            settings_dict = settings_to_dict(thing.settings)
        else:
            settings_dict = settings_to_dict(thing.pool.settings)
            
        settings_dict['pool'] = thing.pool.name


        # If management task is up:
        if sessions[0].last_management_status.startswith('OK'):
    
            # Get queued managemtn messages
            queued_management_messages = ManagementMessage.objects.filter(tid=thing.tid, status='Queued').order_by('ts')
    
            if len(queued_management_messages) > 0:
                # Deliver the first one
                msg_to_deliver = queued_management_messages[0]
                msg            = msg_to_deliver.data
                mid            = msg_to_deliver.uuid
                management_message={'settings': settings_dict, 'msg': msg, 'mid':mid, 'type':msg_to_deliver.type}
                msg_to_deliver.status='Delivered'
                msg_to_deliver.save()
            else:
                management_message={'settings': settings_dict}
        else:
            management_message={'settings': settings_dict}
            
        logger.info('Sending management info to TID={}'.format(thing.tid))
        return ok200(caller=self, data=management_message)


class api_apps_get(publicAPI):
    '''Api for getting the code of an app'''

    #=========================------------
    # POST api, for getting the files list
    #=========================------------
    def _post(self, request):

        # Obtain values
        
        # Get token 
        token  = request.data.get('token', None)
        
        # Version and action (list or get specific file_name)
        version   = request.data.get('version', None)
        list      = request.data.get('list', False)
        file_name = request.data.get('file_name', None)
        
        # Sanity checks
        if not token:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            sessions[0].save()
        else:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        if list:
            # Return files for the app
            files_list=[]
    
            # Get the commit #TOOD: fixme! cannot use thisa hybrid approach with timestamps and epoches..   
            commit = Commit.objects.get(app=thing.app, cid=version)
    
          
            for file in commit.files.all():
                files_list.append(file.name)
            
            return ok200(caller=self, data=files_list)
        
        else:

            # Get the app for this thing
            if not thing.app:
                return error401(caller=self, error_msg='Error: This thing is not registered to any App or Account. This should never happen, please report to the support.')
    
            # Get the commit #TOOD: fixme! cannot use thisa hybrid approach with timestamps and epoches..   
            commit = Commit.objects.get(app=thing.app, cid=version)
    
            # Get the file for the required version
            try:
                if file_name:
                    
                    # New Behavior
                    
                    # Extra: logger and sensors
                    content  = 'import logger\n'
                    if 'worker' in file_name:
                        content += 'try:\n'
                        content += '    import sensors\n'
                        content += 'except ImportError:\n'
                        content += '    pass\n\n'
                        
                    # Get proper file
                    for file in commit.files.all():
                        if file.name == file_name:

                            # Handle binary data
                            #if file.is_binary():
                            #    
                            #    # Open real file and set real content 
                            #    with open (file.content, 'rb') as f:
                            #        content = f.read()
                            #        # To base 64
                            #        import base64
                            #        content = base64.encodestring(content)       
                            #else:
                            
                            # Load file content
                            content += file.content
                            
                            # Include also app version
                            content += '\nversion=\'{}\''.format(commit.cid)
        
                    logger.info('Sending file "{}" code  to TID={}'.format(file_name, thing.tid))
                    return ok200(caller=self, data=content, raw=True)
                
                else: 
                    # Old behavior
                    
                    # GET files for this version, and paste them together (for now)
                    content  = 'import logger\n'
                    for file in commit.files.all():
                        content += file.content
                    
                    # Include also app version
                    content += '\nversion=\'{}\''.format(commit.cid)
        
                    logger.info('Sending application code  to TID={}'.format(thing.tid))
                    return ok200(caller=self, data=content, raw=True)
    
            except Commit.DoesNotExist:
                return error404('No commit found for the specified version')            



    # Back-compatibility
    #=========================------------
    # GET api, for getting the files
    #=========================------------
    def _get(self, request):

        # Obtain values
        token     = request.GET.get('token', None)
        version   = request.GET.get('version', None)
        file_name = request.GET.get('file', None)

        # Sanity checks
        if not token:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     
        if not version:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "version".') 

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            sessions[0].save()
        else:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        # Get the app for this thing
        if not thing.app:
            return error401(caller=self, error_msg='Error: This thing is not registered to any App or Account. This should never happen, please report to the support.')

        # Get the commit #TOOD: fixme! cannot use thisa hybrid approach with timestamps and epoches..   
        commit = Commit.objects.get(app=thing.app, cid=version)

        # Get the file for the required version
        try:
            if file_name:
                # New Behavior
                
                content=''
                # Get proper file
                for file in commit.files.all():
                    if file.name == file_name:
                        # Load file content
                        content += file.content
                
                        # Include also app version
                        content += '\nversion=\'{}\''.format(commit.cid)
    
                logger.info('Sending file "{}" code  to TID={}'.format(file_name, thing.tid))
                return HttpResponse(content)
            
            else: 
                # Old behavior
                
                # GET files for this version, and paste them together (for now)
                content='import logger\n'
                for file in commit.files.all():
                    content += file.content
                
                # Include also app version
                content += '\nversion=\'{}\''.format(commit.cid)
    
                logger.info('Sending application code  to TID={}'.format(thing.tid))
                return HttpResponse(content)

        except Commit.DoesNotExist:
            return error404('No commit found for the specified version')
            


#=========================------------
#  Update Pythings OS API
#=========================------------

class api_pythings_get(publicAPI):
    '''Api for getting the code of pything OS'''

    def _post(self, request):

        # Get token 
        token  = request.data.get('token', None)
        
        # Version and action (list for given platform or get specific file_name for given platform)
        version   = request.data.get('version', None)
        platform      = request.data.get('platform', None)
        list      = request.data.get('list', False)
        file_name = request.data.get('file_name', None)
        
        # Sanity checks
        if not token:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     

        # Sanity checks
        if not version or not platform:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Please tell me which platform and version.')     

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            sessions[0].save()
        else:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        if list:
            # Return files for the given version and platform

            #tree='/opt/Pythings/pythings_app/static/dist/PythingsOS/{}/{}'.format(version,platform)
            tree='/opt/PythingsOS-dist/PythingsOS/{}/{}'.format(version,platform)
            files_txt = tree+'/files.txt'
            logger.info('Opening {}'.format(files_txt))
            try:
                with open(files_txt) as f:
                    content = f.read()
            except:
                return error404(caller=self, error_msg='Hi, Pythings Cloud here. Could not find platform \''+platform+'\' or version \''+version+'\'.')
            
            files_list = {}
            for line in content.split('\n'):
                #print ('line', line)
                try:
                    _, size, file_name = line.split(':')
                    files_list[file_name]=size
                except:
                    pass
            
            # Stupid, simple  check
            if 'version.py' not in files_list:
                return error404(caller=self, error_msg='Hi, Pythings Cloud here. Could not find platform \''+platform+'\' or version \''+version+'\'.')

            return ok200(caller=self, data=files_list)
        
        else:

            # Get the app for this thing
            if not thing.app:
                return error401(caller=self, error_msg='Hi, Pythings Cloud here. This thing is not registered to any App or Account. This should never happen, please report to the support.')

            #file_path='/opt/Pythings/pythings_app/static/dist/PythingsOS/{}/{}/{}'.format(version,platform,file_name)
            file_path='/opt/PythingsOS-dist/PythingsOS//{}/{}/{}'.format(version,platform,file_name)            
            logger.info('Opening {}'.format(file_path))
            try:
                with open(file_path) as f:
                    content = f.read()
            except:
                return error404(caller=self, error_msg='Hi, Pythings Cloud here. Could not find platform \''+platform+'\' or version \''+version+'\'.')
            #print 'content', content
            return ok200(caller=self, data=content, raw=True)

            
#=========================
#  Pre-register thing
#=========================

class api_things_preregister(publicAPI):
    '''Api for pre-registering a thing. It basically just starts an encrypted session'''

    def _post(self, request):

        # Key and Key type
        key  = request.data.get('key', None)
        kty  = request.data.get('kty', None)
        ken  = request.data.get('ken', None)
        
        # Sanity checks
        if not key or not kty or not ken: 
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: key/kty/ken are all required.')
        
        if ken not in ['srsa1']: 
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, only srsa encryption is supported.')
        
        # Un-encrypt the key                
        with open('../pubkey.key') as f:
            pubkey = int(f.read())

        with open('../privkey.key') as f:
            privkey = int(f.read())  

        # Init simple RSA
        srsa = Srsa(pubkey=pubkey, privkey=privkey)
        try:
            key = srsa.decrypt_text(key)
        except Exception as e:
            
            logger.error('Error in decrypting public-key encrypted text: {}'.format(format_exception(e)))         
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, got error in decrypting public-key encrypted text.')

        # Convert key in int (and polish from invisible chars)
        m = re.search(r'\d+', key)
        numeric = m.group() 
        key = int(numeric)

        # Set payload encrypter (will be used by all the returns)
        
        aes128ecb = Aes128ecb(key=key, comp_mode=True)
        self.payload_encrypter=aes128ecb

        # Generate token
        token = str(uuid.uuid4())

        # Save key in Session
        try:
            Session.objects.create(token=token,key=key,kty=kty)
        except Exception as e:
            logger.error(str(e))
            return error500(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, something went wrong. Please report this error.')
        
        # Prerpare data
        data = {'token': token}

        # Return
        return ok200(caller=self, data=data)


#=========================
#  Register thing 
#=========================

class api_things_register(publicAPI):
    '''Api for registering a thing'''

    def _post(self, request):

        # TID, AID & Session token
        tid    = request.data.get('tid', None)
        aid    = request.data.get('aid', None)
        token  = request.data.get('token', None)
        
        # Running versions
        running_app_version       = request.data.get('app_version', 'Unknown')
        running_pythings_version  = request.data.get('pythings_version', 'Unknown')
        frozen_pythings           = request.data.get('frozen', False)
        
        # Platform
        platform = request.data.get('platform', None)
        
        # Device capabilities
        capabilities  = request.data.get('capabilities', None)
        
        # Pool and Settings
        pool_name = request.data.get('pool', None)

        # Sanity checks
        if not tid:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: "tid" is required.')
        if not aid:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: "aid" is required.')

        # Check if there is a valid application or account for this AID
        logger.info('Registering TID "{}": checking for AID "{}"'.format(tid,aid))
        
        # Check for AID as App ID
        try:   
            app = App.objects.get(aid=aid)
        except App.DoesNotExist:
            app = None
        
        # Check for AID as Account ID
        try:
            user = User.objects.get(username=aid)
        except User.DoesNotExist:
            user = None
        
        # Check we have a t least one of the two
        if not app and not user:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: AID "{}" is not valid.'.format(aid))

        # If our thing communicated an accoutn ID, and therefore we have the user,
        # check if we have an app installed via the backend.
        
        #-----------------------------------
        # If we have been giving an App AID
        #-----------------------------------
        if app:

            # Does a thing already exist on this App?
            try:
                thing = Thing.objects.get(tid=tid, app=app)
            except Thing.DoesNotExist:
                thing = None
                
                # Does the user of the App has another App where the thing is already registerd?
                for this_app in App.objects.filter(user=app.user):
                    for this_thing in Thing.objects.filter(app=this_app):
                        #logger.debug('{} vs {}'.format(this_thing.tid, tid))
                        if this_thing.tid == tid:
                            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, this Thing is already associated with another App in the same account.')

            # If it does not, create and assign the App and optionally the pool to this thing (if we are allowed to do so) 
            if not thing:

                # Check if creating this Thing is allowed
                total_devices = get_total_devices(app.user)
                if total_devices >= app.user.profile.plan_things_limit:
                    logger.info('LIMIT: reached devices limit for the account "{}" ({})'.format(app.user.email, app.user.username))
                    return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but you reached the device limit for your account! Please upgrade.')
                    
                # If we have the pool name, set it while checking if it exists, if not default
                #  on App's default pool, and otherwise use the App's default pool as weel.
                if pool_name:
                    try:
                        pool = Pool.objects.get(app=app, name=pool_name)
                    except Pool.DoesNotExist:
                        #return error404(caller=self, error_msg='Error: the pool named "{}" does not exist for this app'.format(pool_name))
                        pool = app.default_pool
                else:
                    pool = app.default_pool
            
                logger.critical('Creating Thing with TID="{}" on App with AID="{}" on Pool "{}")'.format(tid,aid,pool))
            
                # Create the thing
                thing = Thing.objects.create(tid=tid, app=app, pool=pool, app_set_via='register')
                logger.info('Created Thing with TID="{}" on App with AID="{}")'.format(tid,aid))


        #---------------------------------------
        # If we have been giving an Account AID 
        #---------------------------------------
        elif user:

            # Get the "NoneApp" for this user, and if it does not exist, create it.
            try:
                app = App.objects.get(user=user, aid='00000000-0000-0000-0000-000000000000')
            except App.DoesNotExist:
                app = create_app(name='NoneApp', user=user, aid='00000000-0000-0000-0000-000000000000',
                                 management_interval='5', worker_interval='300', pythings_version='factory',
                                 empty_app=True)
            
            # Does any of the apps in the user account has this TID?
            for this_app in App.objects.filter(user=app.user):
                for this_thing in Thing.objects.filter(app=this_app):
                    #logger.debug('{} vs {}'.format(this_thing.tid, tid))
                    if this_thing.tid == tid:
                        # Reassign the app
                        app = this_app

            # Does a thing with this TID on the app exist?
            try:
                thing = Thing.objects.get(tid=tid, app=app)
            except Thing.DoesNotExist:
                thing = None
            
            # If it does not, create and assign the NoneApp to this thing (if we are allowed to do so) 
            if not thing:
                
                # TOOD: we weill never get here if the app has been reassigned above, maybe change the structure?
                
                # Check if creating this Thing is allowed
                total_devices = get_total_devices(user)
                if total_devices >= user.profile.plan_things_limit:
                    logger.info('LIMIT: reached devices limit for the account "{}" ({})'.format(user.email, user.username))
                    return error401(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but you reached the device limit for your account! Please upgrade.')

                # Always use default pool in this case (that will be the "ubound" pool)
                pool = app.default_pool
                
                # Create a new Thing with the NoneApp in the "unbound" pool
                thing = Thing.objects.create(tid=tid, app=app, pool=pool, app_set_via='backend')
                logger.info('Created thing with TID="{}" (on None App with AID="{}")'.format(tid, app.aid))
   
            
        # If we got a consitency error
        else:
            raise Exception('Consistency error')

        # Update platform attribute if changed
        if platform != thing.platform:
            thing.platform = platform
            thing.save()
        
        # Update capabilities attribute if changed
        if capabilities != thing.capabilities:
            thing.capabilities = capabilities
            thing.save()

        # Update frozen attribute if changed
        if frozen_pythings != thing.frozen_os:
            thing.frozen_os = frozen_pythings
            thing.save()

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(thing=thing, active=True)
        for session in sessions:
            session.active=False
            session.save()
        
        # Create the toke if not given (after a pre-register)
        if not token:
            token = str(uuid.uuid4())
            logger.info('Creating session with token {}'.format(token))
            session = Session.objects.create(token=token, thing=thing, app_version=running_app_version, pythings_version=running_pythings_version, pool=thing.pool)

        else:
            logger.info('Using preregistered session with token {}'.format(token))
            # Obtain the session for this token
            try:
                session = Session.objects.get(token=token)
            except MultipleObjectsReturned:
                sessions = Session.objects.filter(token=token)
                for session in sessions:
                    logger.warning('Multiple sessions for {}: {}'.format(token, session))
                session = sessions[0]
            
            # Update already existent session
            session.thing=thing
            session.app_version=running_app_version
            session.pythings_version=running_pythings_version
            session.pool=thing.pool
            session.save()


        # Return (add 'backend': 'xx.yy.zz') to route traffic (i.e. round-robin or random)
        return ok200(caller=self, data={'token': session.token,  'epoch': int(time.time())})


#=========================
#  Update thing status 
#=========================

class api_things_report(publicAPI):
    '''Api for updating the session status'''

    def _post(self, request):
        
        # Get token 
        token  = request.data.get('token', None)
        
        # Obtain values
        what      = request.data.get('what', None)
        status    = request.data.get('status', None)
        message   = request.data.get('msg', None)

        # Sanity checks
        if not token:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: "token" is required.')
        if not what:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: "what" to report is required.')
        if not status:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Error: "status" to report is required.')
        
        if what not in ['worker','management','pythings']:
            return error400(caller=self, error_msg='Hi, Pythings Cloud here. Error: what to report is not recognized (got "{}").'.format(what))        

        # Try to get a session for this thing
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            session = sessions[0]
        else:
            return error401(caller=self, error_msg='Hi, Pythings Cloud here. Soory, could not find token.')

        modified=False
        if message:
            message_str = ': ' + str(message)
        else:
            message_str = ''
        if what == 'pythings':
            session.last_pythings_status  = status + message_str
            modified=True
        if what == 'worker':
            session.last_worker_status = status + message_str
            modified=True
        if what == 'management':
            if message:
                
                # The following check if message is status or management command data response
                # mid = Message ID
                # rep = Reply
                if 'mid' in message:
                    session.last_management_status  = status
                    mid = message['mid']
                    if not 'rep' in message:
                        rep = None
                    else:
                        rep = message['rep']
                    try:
                        #print 'UUID', mid, rep
                        msg_obj = ManagementMessage.objects.get(aid=session.thing.app.aid, tid=session.thing.tid, uuid=mid)
                    except Exception as e:
                        #print e
                        pass
                        # Create ad hoc? modify in management in pythings
                        #msg_obj = ManagementMessage.objects.create(aid=session.thing.app.aid, tid=session.thing.tid, msg='Empty', reply=rep)
                    else:
                        msg_obj.status='Received'
                        if rep is not None:
                            msg_obj.reply = rep
                        msg_obj.save()
                        # Increment total messages count
                        inc_total_messages(user=session.thing.app.user, management=1)
                else:
                    session.last_management_status  = status + message_str    
            else:
                session.last_management_status  = status

            modified=True

        # Overall                
        if modified:
            session.save()

        # Return
        return ok200(caller=self, data=None)


#=========================
#  Time epoch seconds
#=========================

class api_time_epoch_s(publicAPI):
    '''Api for getting epoch_s'''

    def _get(self, request):        
        return ok200(caller=self, data={'epoch_s': int(time.time())})



















