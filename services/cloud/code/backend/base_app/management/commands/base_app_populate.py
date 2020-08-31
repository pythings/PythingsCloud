from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings

class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        if not User.objects.filter(username='admin').exists():
            print('Creating default admin: user=admin, pass=admin. Change it!!')
            admin = User.objects.create_superuser('admin', 'admin@pythings.local', 'admin')
            admin.save()
        else:
            print('Django default admin already exists, skipping populate...')


