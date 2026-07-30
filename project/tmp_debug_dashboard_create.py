import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
os.chdir(os.path.dirname(__file__))
sys.path.insert(0, os.getcwd())
import django
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.urls import reverse

django.setup()
User = get_user_model()
user, created = User.objects.get_or_create(
    username='tempadmin123',
    defaults={'email': 'tempadmin123@example.com', 'tenant': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'is_superuser': True, 'is_staff': True},
)
if created:
    user.set_password('TempPass123!')
    user.save()
client = APIClient()
client.force_authenticate(user=user)
response = client.post(reverse('dashboard-list'), {'dashboard_name':'Head Teacher','role_name':'Head Teacher','description':'Head teacher workspace'}, format='json')
print('status', response.status_code)
print('data', response.data)
print('content', response.content.decode())
