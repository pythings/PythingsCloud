import json
from django.test import TestCase
from rest_framework.test import APIClient as Client
from django.test.client import MULTIPART_CONTENT
from rest_framework import status
from rest_framework.reverse import reverse
from django.contrib.auth.models import User

class APIClient(Client):

    def patch(self, path, data='', content_type=MULTIPART_CONTENT, follow=False, **extra):
        return self.generic('PATCH', path, data, content_type, **extra)

    def options(self, path, data='', content_type=MULTIPART_CONTENT, follow=False, **extra):
        return self.generic('OPTIONS', path, data, content_type, **extra)


class BaseAPITestCase(TestCase):

    """
        ###Custom Base Api Test Class for testing purposes###

        * _login: if no data is passed takes self.LOGIN_DATA

        * _logout: logs out a user and deletes cookies and auth

        * _register: if no data is passed takes self.REGISTRATION_DATA

        * post/get/put/delete: shorthand functions to basic CRUD operations, implements send_request

        * send_request: can set content_type, status_code and token in request, also checks response status_code
    """
 
    login_url  = '/api/v1/auth/login' 
    logout_url = '/api/v1/auth/logout' 
    
    LOGIN_DATA = {
        'username': 'admin',
        'password': 'admin'
    }

    def _login(self, data=None):
        if data is None:
            resp = self.post(self.login_url, data=self.LOGIN_DATA, status_code=status.HTTP_200_OK)
        else:
            resp = self.post(self.login_url, data=data, status_code=status.HTTP_200_OK)
        data = json.loads(resp.content)

    def _logout(self):
        self.post(self.logout_url, status_code=status.HTTP_200_OK)
        self.client.credentials()

    def _register(self, data=None):
        if data is None:
            self.post(self.register_url, data=self.REGISTRATION_DATA, status_code=status.HTTP_201_CREATED)
        else:
            self.post(self.register_url, data=data, status_code=status.HTTP_201_CREATED)

    def _generate_uid_and_token(self, user):

        result = {}
        from django.utils.encoding import force_bytes
        from django.contrib.auth.tokens import default_token_generator
        from django import VERSION
        if VERSION[1] == 5:
            from django.utils.http import int_to_base36
            result['uid'] = int_to_base36(user.pk)
        else:
            from django.utils.http import urlsafe_base64_encode
            result['uid'] = urlsafe_base64_encode(force_bytes(user.pk))
        result['token'] = default_token_generator.make_token(user)
        return result

    def setUp(self):
        pass

    def send_request(self, request_method, *args, **kwargs):

        request_func = getattr(self.client, request_method)
        status_code  = None

        if 'content_type' not in kwargs and request_method != 'get':
            kwargs['content_type'] = 'application/json'

        if 'data' in kwargs and request_method != 'get' and kwargs['content_type'] == 'application/json':
            data = kwargs.get('data', '')
            try:
                kwargs['data'] = json.dumps(data)  # , cls=CustomJSONEncoder
            except:
                pass

        if 'status_code' in kwargs:
            status_code = kwargs.pop('status_code')

        if hasattr(self, 'token'):
            kwargs['HTTP_AUTHORIZATION'] = 'Token %s' % self.token

        self.response = request_func(*args, **kwargs)

        # Parse response
        is_json = False

        if 'content-type' in self.response._headers:
            is_json = bool(filter(lambda x: 'json' in x, self.response._headers['content-type']))

        if is_json and self.response.content:
            self.response.json = json.loads(self.response.content)
        else:
            self.response.json = {}

        if status_code:
            if not self.response.status_code == status_code:
                raise Exception('Error with response:' + str(self.response))
        return self.response

    def post(self, *args, **kwargs):
        return self.send_request('post', *args, **kwargs)

    def get(self, *args, **kwargs):
        return self.send_request('get', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.send_request('put', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.send_request('delete', *args, **kwargs)

    def patch(self, *args, **kwargs):
        return self.send_request('patch', *args, **kwargs)

    def init(self):

        import os
        self.ext_testserver = None

        if "TESTSERVER" in os.environ:
            self.ext_testserver = os.environ.get('TESTSERVER')
            self.client = APIClient(SERVER_NAME=self.ext_testserver)
        else:
            self.client = APIClient()

    def assertRedirects(self, *args, **kwargs):

        if self.ext_testserver:
            kwargs['host'] = self.ext_testserver

        super(BaseAPITestCase, self).assertRedirects(*args, **kwargs)

    def verifyusers(self, users):

        from allauth.account.models import EmailAddress
        for user in users:
            email        = EmailAddress.objects.create(user=user, email=user.email, verified=True)
            email.save()

