from django.db import migrations, models


def _fill_subject_from_lessons(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    TimeTable = apps.get_model("schedule", "TimeTable")
    for row in Attendance.objects.filter(subject=""):
        lesson = (
            TimeTable.objects.filter(student=row.student, Day=row.Date)
            .order_by("-Hour")
            .first()
        )
        if lesson is None or not (lesson.Subject or "").strip():
            continue
        row.subject = str(lesson.Subject).strip()[:30]
        row.save(update_fields=["subject"])


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0001_initial"),
        ("schedule", "0002_timetable_teacher_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="subject",
            field=models.CharField(blank=True, default="", max_length=30, verbose_name="المادة"),
        ),
        migrations.RunPython(_fill_subject_from_lessons, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="attendance",
            unique_together={("student", "Date", "subject")},
        ),
        migrations.AlterModelOptions(
            name="attendance",
            options={
                "ordering": ("-Date", "subject"),
                "verbose_name": "حضور",
                "verbose_name_plural": "الحضور",
            },
        ),
    ]
