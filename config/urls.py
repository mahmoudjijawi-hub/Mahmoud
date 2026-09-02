"""جذر روابط المشروع: لوحة الإدارة العشوائية ثم الـ API المطابقة للـ Postman."""
# استيراد المسارات
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import CustomTokenObtainPairView, ManagerViewSet
from academics.views import TeacherViewSet, StudentViewSet, StudentPortalView, StudentLoginView
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
# مرادفات شائعة قد يستدعيها الفرونت لزر الدفع
router.register(r"payment", PaymentViewSet, basename="payment")
router.register(r"pay", PaymentViewSet, basename="pay")
# مورد الحضور (غير موجود بالـ Collection؛ أُضيف بنفس نمط REST دون كسر المسارات الأخرى)
router.register(r"attendance", AttendanceViewSet, basename="attendance")

urlpatterns = [
    # لوحة Django Admin بمسار غير متوقع من متغير البيئة
    path(settings.ADMIN_URL, admin.site.urls),
    # POST /api/token/ — مطابق لاسم الطلب token في الـ Collection
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/login/", CustomTokenObtainPairView.as_view(), name="token_login_alias"),
    # POST /api/token/refresh/ — مطابق لاسم الطلب refresh
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # شاشة الرقم المميز: POST /api/student-login/
    path("api/student-login/", StudentLoginView.as_view(), name="student-login"),
    path("api/student_login/", StudentLoginView.as_view(), name="student-login-underscore"),
    # شاشة بروفايل الطالب: GET /api/student-detail/{id}/ مع StudentToken
    path("api/student-detail/", StudentPortalView.as_view(), name="student-detail"),
    path("api/student-detail/<str:pk>/", StudentPortalView.as_view(), name="student-detail-pk"),
    path("api/student_detail/", StudentPortalView.as_view(), name="student-detail-underscore"),
    path(
        "api/student_detail/<str:pk>/",
        StudentPortalView.as_view(),
        name="student-detail-underscore-pk",
    ),
    # شاشة تعديل المسار تستخدم هذا الشكل حرفياً
    path(
        "api/students/edit-post/<uuid:pk>/",
        StudentViewSet.as_view({"post": "edit_post", "put": "edit_post", "patch": "edit_post"}),
        name="student-edit-post",
    ),
    # بقية موارد الـ API تحت /api/
    path("api/", include(router.urls)),
]

# في التطوير فقط: خدمة ملفات الوسائط للتجربة المحلية (الإنتاج عبر nginx + صلاحيات)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
