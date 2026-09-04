from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", verbosity=0)


def drop_cache_table(apps, schema_editor):
    table = schema_editor.quote_name("django_cache")
    schema_editor.execute(f"DROP TABLE IF EXISTS {table}")


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
