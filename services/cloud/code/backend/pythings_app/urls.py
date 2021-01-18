
# Django imports
from django.conf.urls import url
from django.views.generic.base import RedirectView

# Backend imports
from . import views
from . import apis_web_v1
from . import apis_v1

urlpatterns = [

    #===========================
    #  Views 
    #===========================

    # Public views
    url(r'^$', views.main, name='main'),
    url(r'^terms/$', views.terms, name='terms'),
    url(r'^privacy/$', views.privacy, name='privacy'),

    # User account, profile and login/logout
    url(r'^login/$', views.user_login, name='login'),
    url(r'^postlogin/$', views.postlogin, name='postlogin'),
    url(r'^logout/$', views.user_logout, name='logout'),
    url(r'^account/$', views.account, name='account'),
    url(r'^register/$', views.register, name='register'),

    # App and Thing views
    url(r'^dashboard/$', views.dashboard, name='dashboard'),
    url(r'^dashboard_app/$', views.dashboard_app, name='dashboard_app'),
    url(r'^dashboard_app_code_editor/$', views.dashboard_app_code_editor, name='dashboard_app_code_editor'),
    url(r'^dashboard_app_code_editor_embed/$', views.dashboard_app_code_editor_embed, name='dashboard_app_code_editor_embed'),
    url(r'^dashboard_thing/$', views.dashboard_thing, name='dashboard_thing'),
    url(r'^dashboard_thing_sessions/$', views.dashboard_thing_sessions, name='dashboard_thing_sessions'),
    url(r'^dashboard_thing_messages/$', views.dashboard_thing_messages, name='dashboard_thing_messages'),
    url(r'^dashboard_thing_shell/$', views.dashboard_thing_shell, name='dashboard_thing_shell'),   
    url(r'^new_app/$', views.new_app, name='new_app'),
    url(r'^list_apps/$', views.list_apps, name='list_apps'),
    url(r'^new_thing/$', views.new_thing, name='new_thing'),

    # Websetup
    url(r'^websetup/$', views.websetup, name='websetup'),


    #===========================
    #  APIs (web) v1
    #===========================

    # Code editor IDE
    url(r'^api/web/v1/code_editor/uploadfile$', apis_web_v1.api_code_editor_uploadfile.as_view(), name='api_code_editor_uploadfile'),
    
    # Messages
    url(r'^api/web/v1/msg/worker/get$', apis_web_v1.api_msg_worker_get.as_view(), name='api_web_msg_worker_get'),
    url(r'^api/web/v1/msg/management/new$', apis_web_v1.api_msg_management_new.as_view(), name='api_web_msg_management_new'),
    url(r'^api/web/v1/msg/management/get$', apis_web_v1.api_msg_management_get.as_view(), name='api_web_msg_management_get'),


    #===========================
    #  APIs (things) v1.x.x 
    #===========================
  
    # Things
    url(r'^api/v1/things/preregister/$', apis_v1.api_things_preregister.as_view(), name='api_things_preregister'),
    url(r'^api/v1/things/register/$', apis_v1.api_things_register.as_view(), name='api_things_register'),
    url(r'^api/v1/things/report', apis_v1.api_things_report.as_view(), name='api_things_report'),

    # Apps
    url(r'^api/v1/apps/worker', apis_v1.api_msg_drop.as_view(), name='api_apps_worker'),
    url(r'^api/v1/apps/management', apis_v1.api_apps_management.as_view(), name='api_apps_management'),
    url(r'^api/v1/apps/get', apis_v1.api_apps_get.as_view(), name='api_apps_get'),

    # Pythings
    url(r'^api/v1/pythings/get', apis_v1.api_pythings_get.as_view(), name='api_pythings_get'),

    # Time (public)
    url(r'^api/v1/time/epoch_s/$', apis_v1.api_time_epoch_s.as_view(), name='api_time_epoch_s'),


    #===========================
    #  Extra 
    #===========================



]
