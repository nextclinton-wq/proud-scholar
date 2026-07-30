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
    username='tempteacher',
    defaults={'email': 'tempteacher@example.com', 'tenant': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'is_superuser': False, 'is_staff': False},
)
if created:
    user.set_password('TeacherPass123!')
    user.save()
service = DashboardService(request=None)
try:
    result = service.get_dashboard_menu(user)
    print('SUCCESS', result)
except Exception as exc:
    import traceback
    traceback.print_exc()
