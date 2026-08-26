"""لوحة إدارة الأكاديميات."""
from django.contrib import admin

from academics.models import Stage, Subject, Section, Teacher, Student


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "stage")
    list_filter = ("stage",)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "special_number", "expertise")
    search_fields = ("special_number", "first_name", "last_name")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "special_number", "student_class", "is_payer")
    list_filter = ("is_payer", "student_class")
    search_fields = ("special_number", "first_name", "last_name")
    filter_horizontal = ("subjects",)
