from django.contrib import admin

from attendance.models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "Date", "Status")
    list_filter = ("Status", "Date")
