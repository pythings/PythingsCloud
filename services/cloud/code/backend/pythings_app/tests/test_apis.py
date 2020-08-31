import json
import logging
import random
from datetime import timedelta
        
from backend.pythings_app.tests.common import BaseAPITestCase
from django.contrib.auth.models import User
from backend.pythings_app.models import WorkerMessage, ManagementMessage, App, Thing, Pool, Settings, Profile, WorkerMessageHandler, MessageCounter
from backend.pythings_app import apis_web_v1 as apis 
from ..common import dt

# Logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("backend")


class TestApi(BaseAPITestCase):

    def setUp(self):
        
        # Create test users
        self.user = User.objects.create_user('testuser', password='testpass')
        self.anotheruser = User.objects.create_user('anotheruser', password='anotherpass')

        # Create test profile and message counter object
        Profile.objects.create(user=self.user, apikey='rci3ggr3i2gic2i')
        MessageCounter.objects.create(user=self.user)

        # Create test Apps
        self.app = App.objects.create(aid='rh398rh20cr9h209rh2r2092j1d39f27ex',
                                      name='Test App',
                                      user=self.user)


        self.anotherapp = App.objects.create(aid='hwiuhqhxeuhu3ygf63kjc8q33px8f7',
                                                  name='Another Test App',
                                                  user=self.anotheruser)

        # Create test Settings (User and App independent)
        
        self.settings = Settings.objects.create(pythings_version='v0.1',
                                                app_version='v0.4',
                                                management_interval='300',
                                                worker_interval='60')
        
        # Create test Pool (User and App independent)
        self.pool = Pool.objects.create(app=self.app,
                                        settings=self.settings)
        
        # Set App default Pool
        self.app.default_pool = self.pool
        self.app.save()

        # Create test Things
        self.thing = Thing.objects.create(tid='112233445566',
                                          app=self.app,
                                          pool=self.pool)

        self.anotherthing = Thing.objects.create(tid='223344556677',
                                                 app=self.anotherapp,
                                                 pool=self.pool) 


    def test_api_web_auth(self):
        '''Test auth using management api''' 
        
        # msg/management ->  
        #  -> get  {'tid': '86rg2877', from=None, to=None, status='queued/sent/received'} TODO: change received in processed?
        #  -> post {'tid': '86rg2877', from=None, to=None, metric=None, aggregation=None, 
        
        # msg/worker
        # -> get {'tid': '86rg2877', from=None, to=None, metric=None, aggregation=None}

        # No user at all
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test auth #1'})
        self.assertEqual(json.loads(resp.content), {"detail": "This is a private API. Login or provide username/password or apikey"})

        # Wrong user
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test auth #1', 'username':'wronguser', 'password':'testpass'})
        self.assertEqual(json.loads(resp.content), {"detail": "Wrong username/password"})

        # Wrong pass
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test auth #1', 'username':'testuser', 'password':'wrongpass'})
        self.assertEqual(json.loads(resp.content), {"detail": "Wrong username/password"})

        # Correct user not existent thing
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': 'xxxxxxxxxxx', 'msg':'test auth #1', 'username': 'testuser', 'password':'testpass'})
        self.assertEqual(json.loads(resp.content), {"detail": "Not existent Thing or no access rights"})
                
        # Correct user wrong thing
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '223344556677', 'msg':'test auth #1', 'username': 'testuser', 'password':'testpass'})
        self.assertEqual(json.loads(resp.content), {"detail": "Not existent Thing or no access rights"})
        
        # Correct user correct thing
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test auth #1', 'username': 'testuser', 'password':'testpass'})
        self.assertEqual(resp.status_code, 200)
        
        # Test API key auth with wrong key
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test auth #2', 'apikey': 'None'})
        self.assertEqual(json.loads(resp.content), {"detail": "Wrong API key"})

        # Test also API key auth with correct key
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test auth #2', 'apikey': 'rci3ggr3i2gic2i'})
        self.assertEqual(resp.status_code, 200)

        
    def test_api_web_msg_management(self):        
        
        # Post a management message
        resp = self.post('/api/web/v1/msg/management/new', data={'tid': '112233445566', 'msg':'test', 'username': 'testuser', 'password':'testpass'})        
        self.assertEqual(resp.status_code, 200)       
        content_dict = json.loads(resp.content)
        
        # Save mid
        mid = content_dict['mid']
        
        # Check correct API logic
        all_management_messages = ManagementMessage.objects.all()
        self.assertEqual(len(all_management_messages), 1)    
        self.assertEqual(all_management_messages[0].tid, '112233445566')
        self.assertEqual(all_management_messages[0].aid, 'rh398rh20cr9h209rh2r2092j1d39f27ex')
        self.assertEqual(all_management_messages[0].data, 'test')
        self.assertEqual(all_management_messages[0].reply, None)
        self.assertEqual(all_management_messages[0].status, 'Queued')
        self.assertEqual(all_management_messages[0].uuid, mid)

        # Get a specific management message
        resp = self.post('/api/web/v1/msg/management/get', data={'mid': mid, 'username': 'testuser', 'password':'testpass'})
        self.assertEqual(resp.status_code, 200)       
        content_dict = json.loads(resp.content)         
        self.assertEqual(content_dict['status'], 'Queued')
        self.assertEqual(content_dict['reply'], None)


 
    def test_api_web_worker(self):        
        
        # Create sample worker messages, for about a month of hour-data.         
        from_dt = dt(2016,10,29,15,0,0, tz='UTC')
        to_dt = dt(2016,12,2,7,0,0, tz='UTC')
        msg = {'temperature_C': 20.5}
        
        total = 0
        ts = from_dt
        while True:
            WorkerMessageHandler.put(aid='rh398rh20cr9h209rh2r2092j1d39f27ex', tid='112233445566', ts=ts, msg=msg)
            total += 1
            ts = ts + timedelta(hours=1)
            if ts  > to_dt:
                break

        # Check messages correctly stored (before even check the APIs)
        all_worker_messages = WorkerMessageHandler.get(timeSpan=None)
        self.assertEqual(len(all_worker_messages), total)    
        self.assertEqual(all_worker_messages[0].tid, '112233445566')
        self.assertEqual(all_worker_messages[0].aid, 'rh398rh20cr9h209rh2r2092j1d39f27ex')
        self.assertEqual(all_worker_messages[0].ts, from_dt)

        # Set from/to with a 4-hours timeslot
        from_s = 1479049200 # Sun, 13 Nov 2016 15:00:00 GMT
        to_s   = 1479049200 + 60*60*4 # plus 4 hours -> Sun, 13 Nov 2016 19:00:00 GMT

        # Not existent thing
        resp = self.post('/api/web/v1/msg/worker/get', data={'tid': 'nonenonenone', 'username': 'testuser', 'password':'testpass', 'from':from_s, 'to':to_s})
        self.assertEqual(json.loads(resp.content), {"detail": "Not existent Thing or no access rights"})
        
        # No access rights for thing
        resp = self.post('/api/web/v1/msg/worker/get', data={'tid': '112233445566', 'username': 'anotheruser', 'password':'anotherpass', 'from':from_s, 'to':to_s})
        self.assertEqual(json.loads(resp.content), {"detail": "Not existent Thing or no access rights"})

        # Error if no from/to set
        resp = self.post('/api/web/v1/msg/worker/get', data={'tid': '112233445566', 'username': 'testuser', 'password':'testpass'})
        self.assertEqual(json.loads(resp.content), {"detail": "No from set"})

        resp = self.post('/api/web/v1/msg/worker/get', data={'tid': '112233445566', 'username': 'testuser', 'password':'testpass', 'from':from_s})
        self.assertEqual(json.loads(resp.content), {"detail": "No to set"})

        resp = self.post('/api/web/v1/msg/worker/get', data={'tid': '112233445566', 'username': 'testuser', 'password':'testpass', 'to':to_s})
        self.assertEqual(json.loads(resp.content), {"detail": "No from set"})
        
        # Correctly get messages
        resp = self.post('/api/web/v1/msg/worker/get', data={'tid': '112233445566', 'username': 'testuser', 'password':'testpass', 'from':from_s, 'to':to_s})

        # Message list to cmapre with
        msg_cfr = [ {'ts':'2016-11-13T15:00:00Z', 'data': {'temperature_C': 20.5}},
                    {'ts':'2016-11-13T16:00:00Z', 'data': {'temperature_C': 20.5}},
                    {'ts':'2016-11-13T17:00:00Z', 'data': {'temperature_C': 20.5}},
                    {'ts':'2016-11-13T18:00:00Z', 'data': {'temperature_C': 20.5}},
                    {'ts':'2016-11-13T19:00:00Z', 'data': {'temperature_C': 20.5}} ]

        total = 0
        for i, msg in enumerate(json.loads(resp.content)):
            
            # Compare 
            self.assertEqual(msg, msg_cfr[i])
            
            # Keep the counter
            total += 1 

        # Check fot total
        self.assertEqual(total, 5)

    
    def test_api_PythingsOS(self):
        
        # Register the Thing (this is already registered, and does not count in term sof device limits)
        resp = self.post('/api/v1/things/register/', data={'tid': '112233445566', 'aid': 'rh398rh20cr9h209rh2r2092j1d39f27ex'})
        self.assertEqual(resp.status_code, 200)
        resp_content_json = json.loads(resp.content)
        token = resp_content_json['token']
        
        # Post a worker message
        resp = self.post('/api/v1/apps/worker/', data={'token': token, 'msg': {'label_one': 13.56}})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'')
          
        # Get the message back and delete it
        worker_messages = WorkerMessageHandler.get(tid = '112233445566', aid = 'rh398rh20cr9h209rh2r2092j1d39f27ex')
        self.assertEqual(len(worker_messages), 1)
        self.assertEqual(type(worker_messages[0].data), dict)
        self.assertEqual(worker_messages[0].data['label_one'], 13.56)
        WorkerMessageHandler.delete(tid = '112233445566', aid = 'rh398rh20cr9h209rh2r2092j1d39f27ex')
         
        # Post another worker message, binary data this time, won't work
        resp = self.post('/api/v1/apps/worker/', data={'token': token, 'msg': {'l1':b'\x00\x0F'}})
        self.assertEqual(resp.status_code, 400)
 
        # Post yet another worker message, string data now
        resp = self.post('/api/v1/apps/worker/', data={'token': token, 'msg': 'Hello world!'})
        self.assertEqual(resp.status_code, 200)
        worker_messages = WorkerMessageHandler.get(tid = '112233445566', aid = 'rh398rh20cr9h209rh2r2092j1d39f27ex')
        #print(worker_messages[0].data)
        self.assertEqual(type(worker_messages[0].data), str)
        self.assertEqual(worker_messages[0].data, 'Hello world!')

        # Post a worker message too big, won't work
        big_msg = {}
        for i in range(0,100):
            big_msg['label_'+str(i)] = i/10.0
        resp = self.post('/api/v1/apps/worker/', data={'token': token, 'msg': big_msg})
        self.assertEqual(resp.status_code, 400)

        # Set plan Things limit to 1
        #self.user.profile.plan_things_limit = 1
        #self.user.profile.save()

        # Register another Thing, won't work as device limit is hit
        #resp = self.post('/api/v1/things/register/', data={'tid': '223344556611', 'aid': 'rh398rh20cr9h209rh2r2092j1d39f27ex'})
        #self.assertEqual(resp.status_code, 401)




