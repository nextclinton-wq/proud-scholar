from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0006_user_avatar_user_notifications_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="department",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
