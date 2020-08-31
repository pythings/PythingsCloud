import json
import logging
import random
  
from backend.pythings_app.tests.common import BaseAPITestCase
from django.contrib.auth.models import User
from backend.pythings_app.models import WorkerMessage, ManagementMessage, App, Thing, Pool, Settings, Profile, WorkerMessageHandler
from backend.pythings_app import apis_web_v1 as apis 

# Logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("backend")


class ApiTests(BaseAPITestCase):

    def setUp(self):
        pass

    def test_WorkerMessage(self):        

        self.assertEqual(1,1) 
        dict_data = {'label_1': 56.7, 'label_2': 12.9}
        
        WorkerMessage.objects.create(aid='A1', tid='T1', data=dict_data)
        
        entry =  WorkerMessage.objects.all()[0]
        
        self.assertEqual(entry.data, dict_data)

    
    def test_WorkerMessageHandler_json(self):        

        self.assertEqual(1,1) 
        dict_data = {'label_1': 56.7, 'label_2': 12.9}
        
        # Create a WorkerMessage
        WorkerMessageHandler.put(aid='A1', tid='T1', msg=dict_data)
        
        # Get back the WorkerMessage
        entries = WorkerMessageHandler.get()
        
        # Test insert
        self.assertEqual(len(entries), 1)
        
        # Test data (json field) behavior
        self.assertEqual(type(entries[0].data), dict)        
        self.assertEqual(entries[0].data, dict_data)


    def test_WorkerMessageHandler_text(self):        
 
        self.assertEqual(1,1) 
        string_data = 'Some data returned by a Thing'
         
        # Create a WorkerMessage
        WorkerMessageHandler.put(aid='A1', tid='T1', msg=string_data)
         
        # Get back the WorkerMessage
        entries = WorkerMessageHandler.get()
     
        # Test insert
        self.assertEqual(len(entries), 1)

        # Test data (json field) behavior
        self.assertEqual(type(entries[0].data), str)        
        self.assertEqual(entries[0].data, string_data)
        
        