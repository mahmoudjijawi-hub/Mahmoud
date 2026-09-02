from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_last_activity"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManagerLoginGuard",
            fields=[
                ("ident", models.CharField(max_length=190, primary_key=True, serialize=False)),
                ("attempts", models.JSONField(blank=True, default=list)),
                ("locked_until", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "قفل دخول المدير",
                "verbose_name_plural": "أقفال دخول المدير",
            },
        ),
    ]
