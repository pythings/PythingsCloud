import json
import logging
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
from ..common.utils import format_exception
from ..common.time import dt_from_s
from ..common.returns import ok200thing, error400thing, error401thing, error404thing, error500thing
from .models import WorkerMessageHandler, ManagementMessage, App, Thing, Session, Pool, Commit
from .helpers import get_total_messages, get_total_devices, inc_total_messages, create_app, settings_to_dict

# Crypto PoC imports
from .crypto_rsa import Srsa
from .crypto_aes import Aes128ecb

# Setup Logging
logger = logging.getLogger(__name__)





#=========================
#  Base Thing API class
#=========================
class ThingAPI(APIView):
    '''Base Thing API class'''

    def post(self, request):
        try:
            # Can we handle the data?
            try:
                # This will trigger the REST framework to parse the data and raise if errors
                # TODO: what if the payload is in wrong format but encrypted?
                len(request.data)
            except Exception:
                return error400thing(caller=None, error_msg='Wrong data format')
            
            # logger.debug(' ** IN ** - Received data: {}'.format(request.data))
            self.payload_encrypter = None
            
            # Handle the case of encrypted data
            encrypted = request.data.get('encrypted', None)
            if encrypted:
                token = request.data.get('token', None)
                if not token:
                    return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: token is missing.')
                
                # Obtain the key for this token
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
            return error500thing(caller=None, error_msg='Hi, Pythings Cloud here. It seems like we are experiencing a problem, please try again later.')

    def get(self, request):
        try:

            # TODO: Do we want payload-encrypted GETs?
            # logger.debug(' ** IN ** - Received data: {}'.format(request.data))
            # self.payload_encrypter = None
            # # Handle the case of encrypted data
            # encrypted = request.data.get('encrypted', False)
            # if encrypted:
            #     token = request.data.get('token', None)
            #     if not token:
            #         return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Erro: token is missing.')
            #      
            #     # Obtain the key for this token
            #     session = Session.objects.get(token=token)
            #       
            #     # Set crypto engine
            #     from crypto_aes import Aes128ecb
            #     aes128ecb = Aes128ecb(key=int(session.key), comp_mode=True)
            #     self.payload_encrypter = aes128ecb
    
            return self._get(request)
        except Exception as e:
            logger.error(format_exception(e))
            return error500thing(caller=None, error_msg='Hi, Pythings Cloud here. It seems like we are experiencing a problem, please try again later.')


    def log(self, level, msg, *strings):
        logger.log(level, self.__class__.__name__ + ': ' + msg, *strings)


#=========================
#  Time epoch API
#=========================

class api_time_epoch_s(ThingAPI):
    '''API for getting the epoch. Called at PythingsOS startup to sync the internal clock.'''

    def _get(self, request):        
        return ok200thing(caller=self, data={'epoch_s': int(time.time())})




#=========================
#  Message upload API
#=========================

class api_msg_drop(ThingAPI):
    '''API for dropping a message from the worker task'''

    def _post(self, request):

        # Get token 
        token  = request.data.get('token', None)

        # Obtain values
        msg  = request.data.get('msg', None)
        ts  = request.data.get('ts', None)

        # Sanity checks
        if not token:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     
        if not msg:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "msg".')
        
        # Handle timestamp
        if ts is not None:
            try:
                ts = dt_from_s(ts)
            except Exception as e:
                logger.error(e)
                return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I cannot handle this timestamp (got "{}").'.format(ts))
 
        # Try to get a session for this thing
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
        else:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        # Get the app for this thing
        if not thing.app.aid:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but this thing is not registered to any AID. This should never happen, please report to the support.')

        # Check data consumption
        total_messages, _, _, = get_total_messages(thing.app.user)
        
        if total_messages >= thing.app.user.profile.plan_messages_limit:
            logger.info('LIMIT: reached messages limit for the account "{}" ({})'.format(thing.app.user.email, thing.app.user.username))
            return error401thing(caller=self, error_msg='Sorry, but you reached the messages limit for your account!')
        
        # Check message size
        msg_len = len(json.dumps(msg))
        if msg_len > 512:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: message too long ({} chars, maximum is 512)'.format(msg_len))

        # Store message
        logger.info('Storing message with aid="{}", tid="{}", ts="{}", msg="{}...")'. format(thing.app.aid, thing.tid, ts, str(msg)[0:50]))

        if ts is not None:
            WorkerMessageHandler.put(aid=thing.app.aid, tid=thing.tid, ts=ts, msg=msg)
        else:
            WorkerMessageHandler.put(aid=thing.app.aid, tid=thing.tid, msg=msg)
        inc_total_messages(user=thing.app.user, worker=1)

        logger.info('Received and stored message dropped from TID={}'.format(thing.tid))
        
        return ok200thing(caller=self, data=None)


#=========================
#  Management API
#=========================

class api_apps_management(ThingAPI):
    '''API for the management task'''

    def _post(self, request):

        # Get token 
        token  = request.data.get('token', None)

        # Sanity checks
        if not token:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     

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
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found (managemet api).')

        # Get the app for this thing
        if not thing.app:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but this thing is not registered to any App. This should never happen, please report to the support.')

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
        return ok200thing(caller=self, data=management_message)


#=========================
#  App code API
#=========================

class api_apps_get(ThingAPI):
    '''API for getting the code of an App'''

    def _post(self, request):
        
        # Get token 
        token  = request.data.get('token', None)
        
        # Version and action (list or get specific file_name)
        version   = request.data.get('version', None)
        list      = request.data.get('list', False)
        file_name = request.data.get('file_name', None)
        
        # Sanity checks
        if not token:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            sessions[0].save()
        else:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        if list:
            # Return files for the app
            files_list=[]
    
            # Get the commit #TOOD: fixme! cannot use thisa hybrid approach with timestamps and epoches..   
            commit = Commit.objects.get(app=thing.app, cid=version)
    
          
            for file in commit.files.all():
                files_list.append(file.name)
            
            return ok200thing(caller=self, data=files_list)
        
        else:

            # Get the app for this thing
            if not thing.app:
                return error401thing(caller=self, error_msg='Error: This thing is not registered to any App or Account. This should never happen, please report to the support.')
    
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
                    return ok200thing(caller=self, data=content, raw=True)
                
                else: 
                    # Old behavior
                    
                    # GET files for this version, and paste them together (for now)
                    content  = 'import logger\n'
                    for file in commit.files.all():
                        content += file.content
                    
                    # Include also app version
                    content += '\nversion=\'{}\''.format(commit.cid)
        
                    logger.info('Sending application code  to TID={}'.format(thing.tid))
                    return ok200thing(caller=self, data=content, raw=True)
    
            except Commit.DoesNotExist:
                return error404thing('No commit found for the specified version')            


    def _get(self, request):
        
        # This is a GET request for getting the files (still here for back-compatibility, mainly)

        # Obtain values
        token     = request.GET.get('token', None)
        version   = request.GET.get('version', None)
        file_name = request.GET.get('file', None)

        # Sanity checks
        if not token:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     
        if not version:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "version".') 

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            sessions[0].save()
        else:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        # Get the app for this thing
        if not thing.app:
            return error401thing(caller=self, error_msg='Error: This thing is not registered to any App or Account. This should never happen, please report to the support.')

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
            return error404thing('No commit found for the specified version')
            


#=========================
#  Update PythingsOS API
#=========================

class api_pythings_get(ThingAPI):
    '''API for getting the code of PythingsOS'''

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
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but I got an empty "token".')     

        # Sanity checks
        if not version or not platform:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Please tell me which platform and version.')     

        # Try to get a session for this thing, and delete it if exists
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            thing = sessions[0].thing
            # Update last contact 
            sessions[0].last_contact=timezone.now()
            sessions[0].save()
        else:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: token not found.')

        if list:
            
            # Return files for the given version and platform
            tree='/opt/PythingsOS-dist/PythingsOS/{}/{}'.format(version,platform)
            files_txt = tree+'/files.txt'
            logger.info('Opening {}'.format(files_txt))
            try:
                with open(files_txt) as f:
                    content = f.read()
            except:
                return error404thing(caller=self, error_msg='Hi, Pythings Cloud here. Could not find platform \''+platform+'\' or version \''+version+'\'.')
            
            files_list = {}
            for line in content.split('\n'):
                #print ('line', line)
                try:
                    _, size, file_name = line.split(':')
                    files_list[file_name]=size
                except:
                    pass
            
            # Naive, simple  check
            if 'version.py' not in files_list:
                return error404thing(caller=self, error_msg='Hi, Pythings Cloud here. Could not find platform \''+platform+'\' or version \''+version+'\'.')

            return ok200thing(caller=self, data=files_list)
        
        else:

            # Get the App for this Thing
            if not thing.app:
                return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. This thing is not registered to any App or Account. This should never happen, please report to the support.')

            file_path='/opt/PythingsOS-dist/PythingsOS//{}/{}/{}'.format(version,platform,file_name)            
            logger.info('Opening {}'.format(file_path))
            try:
                with open(file_path) as f:
                    content = f.read()
            except:
                return error404thing(caller=self, error_msg='Hi, Pythings Cloud here. Could not find platform \''+platform+'\' or version \''+version+'\'.')

            return ok200thing(caller=self, data=content, raw=True)

            
#=========================
# Pre-register Thing API
#=========================

class api_things_preregister(ThingAPI):
    '''API for pre-registering a Thing. It basically just starts an encrypted session.'''

    def _post(self, request):

        # Key and Key type
        key  = request.data.get('key', None)
        kty  = request.data.get('kty', None)
        ken  = request.data.get('ken', None)
        
        # Sanity checks
        if not key or not kty or not ken: 
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: key/kty/ken are all required.')
        
        if ken not in ['srsa1']: 
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, only srsa encryption is supported.')
        
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
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, got error in decrypting public-key encrypted text.')

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
            return error500thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, something went wrong. Please report this error.')
        
        # Prerpare data
        data = {'token': token}

        # Return
        return ok200thing(caller=self, data=data)


#=========================
#  Register Thing API 
#=========================

class api_things_register(ThingAPI):
    '''API for registering a Thing. Starts a session and returns a token.'''

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
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: "tid" is required.')
        if not aid:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: "aid" is required.')

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
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: AID "{}" is not valid.'.format(aid))

        # If our thing communicated an account ID, and therefore we have the user,
        # check if we have an app installed via the backend.
        
        # If we were given an App AID
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
                            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, this Thing is already associated with another App in the same account.')

            # If it does not, create and assign the App and optionally the pool to this thing (if we are allowed to do so) 
            if not thing:

                # Check if creating this Thing is allowed
                total_devices = get_total_devices(app.user)
                if total_devices >= app.user.profile.plan_things_limit:
                    logger.info('LIMIT: reached devices limit for the account "{}" ({})'.format(app.user.email, app.user.username))
                    return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but you reached the device limit for your account!')
                    
                # If we have the pool name, set it while checking if it exists, if not default
                # on App's default pool, and otherwise use the App's default pool as weel.
                if pool_name:
                    try:
                        pool = Pool.objects.get(app=app, name=pool_name)
                    except Pool.DoesNotExist:
                        #return error404thing(caller=self, error_msg='Error: the pool named "{}" does not exist for this app'.format(pool_name))
                        pool = app.default_pool
                else:
                    pool = app.default_pool
            
                logger.critical('Creating Thing with TID="{}" on App with AID="{}" on Pool "{}")'.format(tid,aid,pool))
            
                # Create the thing
                thing = Thing.objects.create(tid=tid, app=app, pool=pool, app_set_via='register')
                logger.info('Created Thing with TID="{}" on App with AID="{}")'.format(tid,aid))

        # If we were given an Account AID 
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
                        # Reassign the App
                        app = this_app

            # Does a thing with this TID on the app exist?
            try:
                thing = Thing.objects.get(tid=tid, app=app)
            except Thing.DoesNotExist:
                thing = None
            
            # If it does not, create and assign the NoneApp to this thing (if we are allowed to do so) 
            if not thing:
                
                # TOOD: we weill never get here if the App has been reassigned above, maybe change the structure?
                
                # Check if creating this Thing is allowed
                total_devices = get_total_devices(user)
                if total_devices >= user.profile.plan_things_limit:
                    logger.info('LIMIT: reached devices limit for the account "{}" ({})'.format(user.email, user.username))
                    return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Sorry, but you reached the device limit for your account!')

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
        return ok200thing(caller=self, data={'token': session.token,  'epoch': int(time.time())})


#=========================
# Update Thing status API
#=========================

class api_things_report(ThingAPI):
    '''API for updating the session status'''

    def _post(self, request):
        
        # Get token 
        token  = request.data.get('token', None)
        
        # Obtain values
        what      = request.data.get('what', None)
        status    = request.data.get('status', None)
        message   = request.data.get('msg', None)

        # Sanity checks
        if not token:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: "token" is required.')
        if not what:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: "what" to report is required.')
        if not status:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: "status" to report is required.')
        
        if what not in ['worker','management','pythings']:
            return error400thing(caller=self, error_msg='Hi, Pythings Cloud here. Error: what to report is not recognized (got "{}").'.format(what))        

        # Try to get a session for this thing
        sessions = Session.objects.filter(token=token, active=True)
        if sessions:
            session = sessions[0]
        else:
            return error401thing(caller=self, error_msg='Hi, Pythings Cloud here. Soory, could not find token.')

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
                        msg_obj = ManagementMessage.objects.get(aid=session.thing.app.aid, tid=session.thing.tid, uuid=mid)
                    except Exception as e:
                        # TODO: handle this
                        pass
                    else:
                        msg_obj.status='Received'
                        if rep is not None:
                            msg_obj.reply = rep
                        msg_obj.save()
                        # Increment total messages counter
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
        return ok200thing(caller=self, data=None)

