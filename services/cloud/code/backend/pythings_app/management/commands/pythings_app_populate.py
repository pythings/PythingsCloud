from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from ...common import create_app
from ...models import Profile

class Command(BaseCommand):

    def handle(self, *args, **kwargs):
 
        email = 'testuser@pythings.local'
 
        if not User.objects.filter(email=email).exists():

            # Create test user
            print('Creating demo user with mail={}'.format(email))
            from backend.pythings_app.common import random_string
            testuser = User.objects.create_user(random_string(), password='testpass', email=email)
            testuser.save()
            
            # Create the profile as well
            Profile.objects.create(user=testuser)
            
            # Creating demo App for testuser user
            print ('Creating demo app for demouser...')
            create_app(name="Simple Sensor App", user=testuser, aid='af408519-0387-44f8-a4e2-f87b9aac8d8e')
            print ('Ok, created.')
   
        else:
            print('Django user for testuser already exists, skipping populate...')
    








                