"""زرع المراحل والمواد الافتراضية القابلة للإدارة."""
from django.db import migrations


STAGES = (
    "بكالوريا",
    "حادي عشر",
    "انتقالي",
    "علمي",
    "أدبي",
    "عاشر",
    "تاسع",
    "ثامن",
    "سابع",
)

SUBJECTS = (
    "رياضيات",
    "علوم",
    "فيزياء",
    "كيمياء",
    "عربي",
    "وطنية",
    "ديانة",
    "انكليزي",
    "فرنسي",
    "جغرافيا",
    "تاريخ",
    "فلسفة",
)


def seed_catalog(apps, schema_editor):
    Stage = apps.get_model("academics", "Stage")
    Subject = apps.get_model("academics", "Subject")
    Section = apps.get_model("academics", "Section")
    for name in STAGES:
        Stage.objects.get_or_create(name=name)
    for name in SUBJECTS:
        Subject.objects.get_or_create(name=name)
    bac = Stage.objects.filter(name="بكالوريا").first()
    if bac:
        for section_name in (
            "الشعبة الأولى",
            "الشعبة الثانية",
            "الشعبة الثالثة",
            "الشعبة الرابعة",
            "الشعبة الخامسة",
        ):
            Section.objects.get_or_create(name=section_name, stage=bac)


def unseed_catalog(apps, schema_editor):
    Stage = apps.get_model("academics", "Stage")
    Subject = apps.get_model("academics", "Subject")
    Stage.objects.filter(name__in=STAGES).delete()
    Subject.objects.filter(name__in=SUBJECTS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0002_initial"),
    ]
    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
