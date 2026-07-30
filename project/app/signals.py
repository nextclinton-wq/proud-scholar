from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Dashboard, Role
from .services import DashboardService


@receiver(post_save, sender=Role)
def ensure_role_dashboard(sender, instance: Role, created: bool, **kwargs):
    if not created or instance.is_deleted:
        return

    service = DashboardService(request=None)
    service._ensure_dashboard_for_role(instance, user=None)
