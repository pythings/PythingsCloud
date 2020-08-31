from django.contrib import admin

from .models import *

admin.site.register(Thing)
admin.site.register(App)
admin.site.register(Session)
admin.site.register(Settings)
admin.site.register(Pool)
admin.site.register(File)
admin.site.register(Commit)
admin.site.register(Profile)
admin.site.register(WorkerMessage)
admin.site.register(ManagementMessage)
admin.site.register(MessageCounter)
