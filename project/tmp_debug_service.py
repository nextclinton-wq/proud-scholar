import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
os.chdir(os.path.dirname(__file__))
sys.path.insert(0, os.getcwd())
import django
django.setup()
from django.contrib.auth import get_user_model
from app.services import DashboardService

User = get_user_model()
user, created = User.objects.get_or_create(
    username='tempadmin123',
    defaults={
        'email': 'tempadmin123@example.com',
        'tenant': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'is_superuser': True,
        'is_staff': True,
    },
)
if created:
    user.set_password('TempPass123!')
    user.save()
service = DashboardService(request=None)
try:
    result = service.create_dashboard(user, {
        'dashboard_name': 'Head Teacher',
        'role_name': 'Head Teacher',
        'description': 'Head teacher workspace',
    })
    print('SUCCESS', result)
except Exception as exc:
    import traceback
    traceback.print_exc()
