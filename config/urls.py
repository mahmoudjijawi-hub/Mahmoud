"""جذر روابط المشروع: لوحة الإدارة العشوائية ثم الـ API المطابقة للـ Postman."""
# استيراد المسارات
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import CustomTokenObtainPairView, ManagerViewSet
from academics.views import TeacherViewSet, StudentViewSet
from grades.views import ExamViewSet
from schedule.views import TimeTableViewSet, ProgramViewSet
from payments.views import PaymentViewSet
from attendance.views import AttendanceViewSet

# موجّه DRF يعطي GET /api/ قائمة بكل الموارد (طلب all api في الـ Collection)
router = DefaultRouter()
# مورد المديرين: /api/managers/
router.register(r"managers", ManagerViewSet, basename="managers")
# مورد الأساتذة: /api/teachers/
router.register(r"teachers", TeacherViewSet, basename="teachers")
# مورد الطلاب: /api/students/
router.register(r"students", StudentViewSet, basename="students")
# مورد المذاكرات/الامتحانات: /api/exams/
router.register(r"exams", ExamViewSet, basename="exams")
# مورد الجدول الزمني: /api/time_table/
router.register(r"time_table", TimeTableViewSet, basename="time_table")
# مورد البرنامج الدراسي: /api/programs/
router.register(r"programs", ProgramViewSet, basename="programs")
# مورد الدفعات: /api/payments/
router.register(r"payments", PaymentViewSet, basename="payments")
# مورد الحضور (غير موجود بالـ Collection؛ أُضيف بنفس نمط REST دون كسر المسارات الأخرى)
router.register(r"attendance", AttendanceViewSet, basename="attendance")

urlpatterns = [
    # لوحة Django Admin بمسار غير متوقع من متغير البيئة
    path(settings.ADMIN_URL, admin.site.urls),
    # POST /api/token/ — مطابق لاسم الطلب token في الـ Collection
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    # POST /api/token/refresh/ — مطابق لاسم الطلب refresh
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # بقية موارد الـ API تحت /api/
    path("api/", include(router.urls)),
]

# في التطوير فقط: خدمة ملفات الوسائط للتجربة المحلية (الإنتاج عبر nginx + صلاحيات)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
