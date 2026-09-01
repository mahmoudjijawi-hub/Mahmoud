from django.contrib import admin

from grades.models import Exam


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("Nameofexam", "Subject_name", "Date", "Mark", "Full_mark")
    search_fields = ("Nameofexam", "special_number")
    filter_horizontal = ("student",)
