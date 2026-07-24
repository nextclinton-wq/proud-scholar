import os
import json
import django
from django.test import Client
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()
User = get_user_model()
username = 'clinton'
email = 'clinton@example.com'
user, created = User.objects.get_or_create(username=username, defaults={'email':email, 'tenant':'60cbeaea-7f9f-41df-afbf-369058ac445b', 'is_staff': True, 'is_superuser': True})
if not created:
    user.email = email
    user.tenant = '60cbeaea-7f9f-41df-afbf-369058ac445b'
    user.is_staff = True
    user.is_superuser = True
user.password = make_password('Clints256')
user.save()

client = Client()
login = client.post('/api/v1/auth/login', data=json.dumps({'username': username, 'password': 'Clints256'}), content_type='application/json', HTTP_HOST='127.0.0.1')
print('LOGIN', login.status_code)
print(login.content.decode())
setup = client.post('/api/v1/auth/mfa/setup', data=json.dumps({'username': username, 'password': 'Clints256', 'device_name': 'Google Authenticator'}), content_type='application/json', HTTP_HOST='127.0.0.1')
print('SETUP', setup.status_code)
print(setup.content.decode())
