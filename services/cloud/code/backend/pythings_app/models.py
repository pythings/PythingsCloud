import uuid
import time
import json
import logging

# Django imports
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.postgres.fields import JSONField

# Setup logging
logger = logging.getLogger(__name__) 

# TODO: consider ValidateModelMixin (https://github.com/ComSSA/keydist/blob/master/theoffice/ValidateModelMixin.py)
# REMINDER: to use foreign keys before defining the models, use commas: models.ForeignKey('YourModel', related_name='+')
# REMINDER: to link against a model before its class declaration, use apexes: 'MyLinedModelClass' 


#=========================
#  App
#=========================

class App(models.Model):
    
    aid  = models.CharField('App ID', max_length=36, blank=False, null=False)
    name = models.CharField('Pythings Version', max_length=36, blank=False, null=False)
    user = models.ForeignKey(User, related_name='+')
    default_pool = models.ForeignKey("Pool", related_name='+', blank=True, null=True)
    hidden  = models.BooleanField(default=False)

    def __str__(self):
        return str('App "{}" with AID "{}" of user "{}"'.format(self.name, self.aid, self.user.email))



#=========================
#  File, Commit, Branch
#=========================

class File(models.Model):

    name      = models.CharField('File name', max_length=36, blank=False, null=False)
    path      = models.CharField('File path', max_length=256, default='/')
    content   = models.TextField('File contents', default='')
    app       = models.ForeignKey(App, related_name='+')
    ts        = models.DateTimeField('Creation timestamp', default=timezone.now)
    committed  = models.BooleanField(default=False)
    
    def __str__(self):
        return str(self.name) + ' (id=' + str(self.id) + ') @ App "' + str(self.app.name) + '" of user ' + str(self.app.user.email)
    

class Commit(models.Model):
    
    app    = models.ForeignKey(App, related_name='+') # This is basically like the repo name
    cid    = models.CharField('Commit id', max_length=36, default=None)
    ts     = models.DateTimeField('Creation timestamp', default=timezone.now)
    tag    = models.CharField('Tag', max_length=36, blank=True, null=True)
    files  = models.ManyToManyField(File)
    valid  = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.cid:
            self.cid = str(int(time.mktime(self.ts.timetuple())))
        super(Commit, self).save(*args, **kwargs)
    
    def epoch(self):
        return int(time.mktime(self.ts.timetuple()))

    def ts_str(self):
        from .common import timezonize # Leave it here or circular dependency. TODO: add it to backend common
        return str(self.ts.astimezone(timezonize(self.app.user.profile.timezone))).split('+')[0].split('.')[0]

    @property
    def name(self):
        if self.tag:
            return '{} [{}]'.format(self.cid, self.tag)
        else:
            return '{}'.format(self.cid)

    def __str__(self):
        from .common import timezonize # Leave it here or circular dependency. TODO: add it to backend common
        ts_str = str(self.ts.astimezone(timezonize(self.app.user.profile.timezone))).split('+')[0].split('.')[0]
        if self.tag:
            return 'Commit {} [{}] @ {} of App {} of user {}'.format(self.cid, self.tag, ts_str, self.app.name, self.app.user.email)
        else:
            return 'Commit {} @ {} of App {} of user {}'.format(self.cid, ts_str, self.app.name, self.app.user.email)

        

#=========================
#  Settings an Pool
#=========================

class Settings(models.Model):
    pythings_version    = models.CharField('Pythings Version', max_length=36, blank=False, null=False)
    backend             = models.CharField('Backend', max_length=36, blank=True, null=True)
    app_version         = models.CharField('App version', max_length=36, blank=False, null=False)
    app_tag             = models.CharField('App tag', max_length=36, blank=True, null=True)
    management_interval = models.CharField('Management interval', max_length=36, blank=False, null=False)
    #management_sync     = models.BooleanField('Sync management execution', default=False)
    worker_interval     = models.CharField('Worker interval', max_length=36, blank=False, null=False)
    #worker_sync         = models.BooleanField('Sync worker execution', default=False)
    ssl                 = models.BooleanField('Use SSL', default=True)
    payload_encryption  = models.BooleanField('Use Payload encryption', default=False)
    battery_operated    = models.BooleanField('Battery operated', default=False)
    setup_timeout       = models.IntegerField('Setup timeout', default=60)
    edited              = models.DateTimeField('Edited timestamp', default=timezone.now)

    def save(self, *args, **kwargs):
        self.edited = timezone.now() 
        super(Settings, self).save(*args, **kwargs)

    def __str__(self):
        return str('Settings with id "{}"'.format(self.id))


class Pool(models.Model):
    app      = models.ForeignKey(App, related_name='+')
    name     = models.CharField('Pythings Version', max_length=36, blank=True, null=True)
    settings = models.ForeignKey(Settings, related_name='+')
    
    # Lock to tags
    use_latest_pythings_version = models.BooleanField(default=False)
    use_latest_app_version      = models.BooleanField(default=False) 
    
    # Pool macro types (i.e. if not development, versions cannot be locked to last)
    development = models.BooleanField(default=False)
    staging     = models.BooleanField(default=False)
    production  = models.BooleanField(default=False)
    
    def __str__(self):
        return str('Pool "{}" of App "{}" of user "{}" with settings id "{}"'.format(self.name,self.app.name,self.app.user.email, self.settings.id))



#=========================
#  Thing 
#=========================
    
class Thing(models.Model):
    
    # Thing unique identifier. Usually te MAC address.
    tid  = models.CharField('Thing ID', max_length=36, blank=False, null=False)
    
    # Thing name
    name  = models.CharField('Name', max_length=36, blank=True, null=True)

    # App and pool
    app  = models.ForeignKey(App, related_name='+')
    pool = models.ForeignKey(Pool, related_name='+')

    # Thing custom settings
    settings = models.ForeignKey(Settings, related_name='+', blank=True, null=True)
    use_custom_settings = models.BooleanField(default=False)
    frozen_os = models.BooleanField(default=False)

    # Plaftorm and capabilities
    platform      = models.CharField('Platform', max_length=36, blank=True, null=True)    
    capabilities  = models.CharField('Capabilities', max_length=36, blank=True, null=True)
    app_set_via   = models.CharField('App set via', max_length=36, blank=True, null=True)

    @property
    def name_short(self):
        if not self.name:
            return self.tid
        if len(self.name) > 21:
            return self.name[0:17]+'...'
        else:
            return self.name 

    def __str__(self):
        return str('Thing with TID "{}" of App "{}", pool "{}" of user "{}"'.format(self.tid, self.app.name, self.pool.name, self.app.user.email))



#=========================
#  Sessions (Things)
#=========================

class Session(models.Model):
    
    # Session logic
    token   = models.CharField('Session Token', max_length=36, primary_key=True)
    thing   = models.ForeignKey(Thing, related_name='+', null=True)
    started = models.DateTimeField('Session start timestamp', default=timezone.now)
    active  = models.BooleanField(default=True)
    
    # Versions
    pythings_version = models.CharField('Pythings OS version', max_length=36, blank=True, null=True)
    app_version = models.CharField('Session Token', max_length=36, blank=True, null=True)
    
    # Last contact and statuses
    last_contact = models.DateTimeField('Session last contact timestamp', default=timezone.now)
    last_pythings_status   = models.TextField('Last reported Pythings status', default='Ok: session started') 
    last_worker_status     = models.TextField('Last reported worker status', default='Unknown') 
    last_management_status = models.TextField('Last reported management status', default='Unknown')
    
    # Pool for keeping track of changes
    pool = models.ForeignKey("Pool", related_name='+', null=True)

    # Keys
    key   = models.CharField('Key', max_length=512, blank=True, null=True)   #512 chars, NOT bits!!!
    kty   = models.CharField('Key type', max_length=36, blank=True, null=True)

    def __str__(self):
        if self.thing:
            return str('Session with token "{}" of Thing with TID "{}" on App "{}", pool "{}" of user "{}". Last contact on {}'.format(self.token, self.thing.tid, self.thing.app.name, self.pool.name, self.thing.app.user.email, self.last_contact))
        else:
            return str('Session with token "{}" of Thing with TID "{}" on App "{}", pool "{}" of user "{}". Last contact on {}'.format(self.token, self.thing, self.thing, self.pool, self.thing, self.last_contact))
            


#=========================
# Messages 
#=========================

class WorkerMessage(models.Model): # TODO: rename to WorkerMessageHandler
    aid  = models.CharField('App ID', max_length=36, blank=False, null=False)
    tid  = models.CharField('Thing ID', max_length=36, blank=False, null=False)
    ts   = models.DateTimeField('Message timestamp', default=timezone.now, blank=True)
    data = JSONField(blank=True, null=True)

    class Meta:
        unique_together = (("aid", "tid", "ts"),)

    def __str__(self):
        return str('Message from Thing with TID "{}" on App with AID "{}" received at {}'.format(self.tid, self.aid, self.ts))

class WorkerMessageHandler(object):

    # TODO: remove me and just use WorkerMessage
    
    @classmethod
    def put(cls, aid, tid, msg, ts=None):
        
        # Set time if not set
        if ts is None:
            ts=timezone.now()
        
        # Convert the message into JSON, This should never fail as the message is sent via REST which is well.. JSON. But test here before passing it to the DB
        json.dumps(msg)

        WorkerMessage.objects.create(aid=aid, tid=tid, ts=ts, data=msg)

    @classmethod    
    def get(cls, aid=None, tid=None, from_dt=None, to_dt=None, last=None, timeSpan='1s'):

        if aid is None and tid is None and from_dt is None and to_dt is None and last is None:
            return WorkerMessage.objects.all()
        elif last:
            if aid is None:
                raise Exception('Need "aid" with last')
            if tid is None:
                raise Exception('Need "tid" with last')
            return WorkerMessage.objects.filter(aid=aid, tid=tid).order_by('-ts')[0:last]
        else:        
            if aid is None:
                raise Exception('Need "aid" (or no arguments at all)')
            elif tid is None:
                raise Exception('Need "tid" (or no arguments at all)')
            elif from_dt is None and to_dt is None:
                return WorkerMessage.objects.filter(aid=aid, tid=tid).order_by('ts')
            elif from_dt is None and to_dt is not None:
                return WorkerMessage.objects.filter(aid=aid, tid=tid, ts__lte=to_dt).order_by('ts')
            elif from_dt is not None and to_dt is None:
                return WorkerMessage.objects.filter(aid=aid, tid=tid, ts__gte=from_dt).order_by('ts')
            else:
                return WorkerMessage.objects.filter(aid=aid, tid=tid, ts__gte=from_dt, ts__lte=to_dt).order_by('ts')

    @classmethod    
    def delete(cls, aid, tid, from_dt=None, to_dt=None):

        if from_dt is not None or to_dt is not None:
            raise NotImplementedError('Deleting from-to not yet implemented')
        WorkerMessage.objects.filter(aid=aid, tid=tid).delete()


class ManagementMessage(models.Model): # TODO: rename to ManagementMessages 
    aid      = models.CharField('App ID', max_length=36, blank=False, null=False)
    tid      = models.CharField('Thing ID', max_length=36, blank=False, null=False)
    ts       = models.DateTimeField('Message timestamp', default=timezone.now, blank=True)
    uuid     = models.CharField('Message uuid', max_length=36)
    status   = models.CharField('Message status', max_length=36, default='Queued')
    type     = models.CharField('Message status', max_length=36, default='APP')
    thing    = models.ForeignKey(Thing, null=True) # Used only for CMD management messages. Remvoe me?
    data     = JSONField(blank=True, null=True)
    reply    = JSONField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.uuid:
            self.uuid = str(uuid.uuid4())
        super(ManagementMessage, self).save(*args, **kwargs)
 
    class Meta:
        unique_together = (("tid", "uuid"),)  

    def __str__(self):
        return str('Message from Thing with TID "{}" on App with AID "{}" received at {}'.format(self.tid, self.aid, self.ts))



#=========================
# Profile and msg counter 
#=========================

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    timezone = models.CharField('User Timezone', max_length=36, default='UTC')
    apikey = models.CharField('User API key', max_length=36, blank=True, null=True)
    plan = models.CharField('User plan', max_length=36, blank=False, null=False, default='Betatester')
    plan_messages_limit = models.IntegerField('plan_messages_limit', default=100000)
    plan_things_limit  = models.IntegerField('plan_things_limit', default=5)
    type    = models.CharField('Profile type', max_length=36, blank=False, null=False, default='Standard') # Advanced | Developer | Hacker ...
    type_id = models.IntegerField('Profile Type ID', default=10)
    email_updates = models.BooleanField(default=False)
    last_accepted_terms = models.FloatField('Last accepted TOS', default=0)


    def save(self, *args, **kwargs):
        if not self.apikey:
            self.apikey = str(uuid.uuid4())
        super(Profile, self).save(*args, **kwargs)

    def __str__(self):
        return str('Profile of user "{}" on timezone "{}"'.format(self.user.email, self.timezone))


class MessageCounter(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    total = models.IntegerField('total', default=0)
    worker = models.IntegerField('worker', default=0)
    management = models.IntegerField('management', default=0)

    def __str__(self):
        return str('MessageCounter of user "{}", worker={}, management={}, total={}'.format(self.user.email, self.worker, self.management, self.total))






