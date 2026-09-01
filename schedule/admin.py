from django.contrib import admin

from schedule.models import TimeTable, Program


@admin.register(TimeTable)
class TimeTableAdmin(admin.ModelAdmin):
    list_display = ("Day", "Hour", "Subject", "Teacher")
    list_filter = ("Day",)
    filter_horizontal = ("student",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("day", "time_slot", "subject_name", "room", "teacher_name")
    list_filter = ("day", "grade", "section")
