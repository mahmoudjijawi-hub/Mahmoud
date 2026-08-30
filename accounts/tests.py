"""اختبارات تكامل تطابق طلبات ملف Postman Collection واحداً واحداً."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Manager
from academics.models import Teacher, Student
from core.models import Subscription
from grades.models import Exam
from payments.models import Payment, PaymentTransaction
from schedule.models import TimeTable, Program

User = get_user_model()


class PostmanAPITests(TestCase):
    """كل طلب في الـ Collection له اختبار مطابق واحد على الأقل."""

    def setUp(self):
        # تفريغ الذاكرة المؤقتة حتى لا يتجمّع حد الـ throttling بين الاختبارات
        cache.clear()
        # اشتراك ساري حتى لا يقطع الوسطاء الاختبارات
        Subscription.objects.create(expiry_date=date.today() + timedelta(days=365), is_active=True)
        # مدير مطابق لحقول POST managers مع اسم مستخدم الـ Collection
        self.user = User.objects.filter(username="ammar").first()
        if self.user is None:
            self.user = User.objects.create_user(
                username="ammar",
                password="ammar12345ammar",
                first_name="Ammar",
                last_name="Admin",
                special_number="7788990",
                role=User.ROLE_MANAGER,
                user_type="1",
            )
        else:
            # إن زُرع المستخدم بالهجرة نضمن كلمة مرور الاختبار
            self.user.set_password("ammar12345ammar")
            self.user.role = User.ROLE_MANAGER
            self.user.is_active = True
            self.user.save()
        self.manager = getattr(self.user, "manager_profile", None)
        if self.manager is None:
            self.manager = Manager.objects.create(
                user=self.user,
                first_name="Ammar",
                last_name="Admin",
                special_number=str(self.user.special_number)[:7],
                user_type="1",
            )
        self.client = APIClient()
        # POST /api/token/ كما في طلب token
        response = self.client.post(
            "/api/token/",
            {"username": "ammar", "password": "ammar12345ammar"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.access = response.data["access"]
        self.refresh = response.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def test_token_request(self):
        """طلب token: POST /api/token/"""
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"username": "ammar", "password": "ammar12345ammar"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        # الواجهة تحتاج الدور في الجسم لتوجيه المدير بعد صفحة كلمة المرور
        self.assertEqual(response.data["role"], "manager")
        self.assertEqual(response.data["user_type"], "1")
        self.assertEqual(response.data["username"], "ammar")
        self.assertEqual(response.data["token"], response.data["access"])
        self.assertEqual(response.data["accessToken"], response.data["access"])
        self.assertEqual(response.data["user"]["role"], "manager")

    def test_session_idle_timeout_is_one_hour_and_slides_on_activity(self):
        """الجلسة تُغلق بعد ساعة خمول وتتجدد مع كل طلب."""
        from datetime import timedelta

        from django.conf import settings
        from django.utils import timezone

        self.assertEqual(settings.SESSION_IDLE_SECONDS, 3600)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 3600)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertEqual(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], timedelta(days=7))

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_activity)

        ok = self.client.get("/api/managers/")
        self.assertEqual(ok.status_code, 200)

        self.user.last_activity = timezone.now() - timedelta(hours=1, minutes=1)
        self.user.save(update_fields=["last_activity"])
        idle = self.client.get("/api/managers/")
        self.assertEqual(idle.status_code, 401)

        self.user.last_activity = timezone.now() - timedelta(minutes=10)
        self.user.save(update_fields=["last_activity"])
        active = self.client.get("/api/managers/")
        self.assertEqual(active.status_code, 200)
        self.user.refresh_from_db()
        self.assertLess((timezone.now() - self.user.last_activity).total_seconds(), 30)

        self.user.last_activity = timezone.now() - timedelta(hours=1, minutes=1)
        self.user.save(update_fields=["last_activity"])
        client = APIClient()
        refresh_idle = client.post(
            "/api/token/refresh/", {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(refresh_idle.status_code, 401)

    def test_manager_special_number_routes_to_password_page(self):
        """الرقم المميز للمدير يعيد 200 مع requires_password حتى ينتقل الفرونت لصفحة المرور."""
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"special_number": "7788990"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["requires_password"])
        self.assertEqual(response.data["role"], "manager")
        self.assertEqual(response.data["code"], "manager_password_required")
        self.assertNotIn("access", response.data)

    def test_cors_allows_arbitrary_localhost_port_in_debug(self):
        """أصول localhost بأي منفذ تُقبل عبر CORS_ALLOWED_ORIGIN_REGEXES."""
        from django.conf import settings

        self.assertTrue(settings.CORS_ALLOWED_ORIGIN_REGEXES)
        response = self.client.post(
            "/api/token/",
            {"username": "ammar", "password": "ammar12345ammar"},
            format="json",
            HTTP_ORIGIN="http://localhost:5999",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5999")
        preflight = self.client.options(
            "/api/token/",
            HTTP_ORIGIN="http://127.0.0.1:5999",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        self.assertIn(preflight.status_code, (200, 204))
        self.assertEqual(preflight["Access-Control-Allow-Origin"], "http://127.0.0.1:5999")

    def test_cors_allow_all_origins_reflects_any_frontend(self):
        """مع CORS_ALLOW_ALL_ORIGINS=True يُعكس أي Origin فرونت في الاستجابة."""
        from django.conf import settings

        self.assertTrue(settings.CORS_ALLOW_ALL_ORIGINS)
        origin = "https://frontend-preview.example.net"
        response = self.client.post(
            "/api/token/",
            {"username": "ammar", "password": "ammar12345ammar"},
            format="json",
            HTTP_ORIGIN=origin,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)

    def test_token_rejects_bad_password(self):
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"username": "ammar", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_credentials")
        self.assertIn("detail", response.data)

    def test_self_heal_admin_login_when_password_hash_broken(self):
        """إن تلفت كلمة مرور المدير تُصلح تلقائياً عند إدخال بيانات البوستمان."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(username="ammar")
        # محاكاة هاش تالف كما كانت الهجرة القديمة
        user.password = "!"
        user.save(update_fields=["password"])
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"username": "ammar", "password": "ammar12345ammar"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "manager")
        user.refresh_from_db()
        self.assertTrue(user.check_password("ammar12345ammar"))

    def test_login_accepts_frontend_field_aliases(self):
        """قبول أسماء حقول شائعة يرسلها الفرونت بدل username/password فقط."""
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"userName": "ammar", "Password": "ammar12345ammar"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "manager")

    def test_migration_sets_usable_admin_password(self):
        """بعد الهجرات يجب أن تنجح بيانات المدير الافتراضية من الإعدادات."""
        from django.conf import settings
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(username=settings.ADMIN_USERNAME)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password(settings.ADMIN_PASSWORD))
        client = APIClient()
        response = client.post(
            "/api/token/",
            {
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "manager")

    def test_api_for_manager(self):
        """طلب api for manager: GET /api/managers/"""
        response = self.client.get("/api/managers/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) >= 1)

    def test_all_api(self):
        """طلب all api: GET /api/"""
        response = self.client.get("/api/")
        self.assertEqual(response.status_code, 200)
        for key in ("managers", "teachers", "students", "exams", "payments", "time_table", "programs"):
            self.assertIn(key, response.data)

    def test_api_for_teachers(self):
        """طلب api for teachers: GET /api/teachers/"""
        response = self.client.get("/api/teachers/")
        self.assertEqual(response.status_code, 200)

    def test_api_for_exams(self):
        """طلب api for exams: GET /api/exams/"""
        response = self.client.get("/api/exams/")
        self.assertEqual(response.status_code, 200)

    def test_api_for_time_table(self):
        """طلب api for time table: GET /api/time_table/"""
        response = self.client.get("/api/time_table/")
        self.assertEqual(response.status_code, 200)

    def test_payments_get(self):
        """طلب payments: GET /api/payments/"""
        response = self.client.get("/api/payments/")
        self.assertEqual(response.status_code, 200)

    def test_api_for_students(self):
        """طلب api for students: GET /api/students/ — الواجهة تتوقع مصفوفة."""
        response = self.client.get("/api/students/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list, response.data)

    def test_add_teacher_and_patch(self):
        """طلب add teacher ثم patch tetcher."""
        create = self.client.post(
            "/api/teachers/",
            {
                "first_name": "عمار",
                "last_name": "القدور",
                "special_number": 1233,
                "gender": True,
                "teacher_number": "2323422",
                "expertise": "رياضيات",
                "cv": "خبرة تدريس طويلة...",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        teacher_id = create.data["id"]
        patch = self.client.patch(
            f"/api/teachers/{teacher_id}/",
            {
                "user": create.data["user"],
                "first_name": "djoser",
                "last_name": "jwt",
                "special_number": "3",
                "gender": "Yes",
                "teacher_number": "0987654343",
                "expertise": "dhtfgjhjk",
                "cv": "z.dkvns.kdvb.adnsvwvsdvb.vb",
            },
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.data["first_name"], "djoser")

    def test_student_token_can_list_teachers_for_portal(self):
        """شاشة أساتذة الطالب: GET /api/teachers/ مع StudentToken يعيد مصفوفة الأساتذة."""
        self._make_teacher("8101")
        student = self._make_student("8102")
        login = APIClient().post(
            "/api/student-login/",
            {"special_number": student.special_number},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        token = login.data["access"]
        client = APIClient()
        listing = client.get(
            "/api/teachers/",
            HTTP_AUTHORIZATION=f"StudentToken {token}",
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        teachers = listing.data["results"] if isinstance(listing.data, dict) else listing.data
        self.assertIsInstance(teachers, list, listing.data)
        self.assertGreaterEqual(len(teachers), 1)
        row = next(
            (item for item in teachers if item.get("first_name") == "أستاذ"),
            teachers[0],
        )
        self.assertIn("first_name", row)
        self.assertIn("last_name", row)
        self.assertIn("expertise", row)
        self.assertIn("cv", row)
        self.assertIn("teacher_number", row)
        self.assertIn("profile_image", row)

        create_attempt = client.post(
            "/api/teachers/",
            {
                "first_name": "ممنوع",
                "last_name": "طالب",
                "special_number": "8103",
                "gender": True,
                "teacher_number": "0999999999",
                "expertise": "كيمياء",
                "cv": "لا",
            },
            format="json",
            HTTP_AUTHORIZATION=f"StudentToken {token}",
        )
        self.assertEqual(create_attempt.status_code, 403)

    def test_add_student_patch_and_delete(self):
        """طلبات add student و patch students و delete student."""
        create = self.client.post(
            "/api/students/",
            {
                "first_name": "أحمد",
                "last_name": "العلي",
                "special_number": 2024001,
                "student_class": 10,
                "parent_number": "0933111222",
                "student_number": "5544",
                "address": "اللاذقية المشروع",
                "personal_notes": "طالب مجتهد",
                "is_payer": False,
                "class1": "رياضيات",
                "class2": "فيزياء",
                "class3": "كيمياء",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        student_id = create.data["id"]
        patch = self.client.patch(
            f"/api/students/{student_id}/",
            {
                "first_name": "djoser",
                "last_name": "adsfdgfh",
                "special_number": "112",
                "student_class": "1",
                "parent_number": "1234567890",
                "student_number": "0987654321",
                "address": "zc",
                "personal_notes": "xcv",
                "is_payer": True,
                "class1": "cghfgdsfdghhbd",
                "class2": "sdfgndsadvbgfd",
                "class3": "sdfghjgfdsdfghd",
            },
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        delete = self.client.delete(f"/api/students/{student_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Student.objects.filter(pk=student_id).exists())
        # الحذف نهائي: حساب المستخدم يُحذف أيضاً ولا يبقى شطب ناعم
        self.assertFalse(User.objects.filter(special_number="112").exists())

    def test_student_can_register_multiple_subjects(self):
        """الواجهة قد ترسل المواد كمصفوفة أو تسجّل نفس الطالب مرة ثانية لمادة جديدة."""
        from academics.models import Subject

        create = self.client.post(
            "/api/students/",
            {
                "first_name": "سامي",
                "last_name": "حسن",
                "special_number": "6601",
                "student_class": "10",
                "parent_number": "0933111222",
                "student_number": "5544",
                "address": "اللاذقية",
                "personal_notes": "أكثر من مادة",
                "is_payer": False,
                "class1": ["رياضيات", "فيزياء", "كيمياء", "عربي"],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        self.assertIn("رياضيات", create.data["subjects"])
        self.assertIn("فيزياء", create.data["subjects"])
        self.assertIn("كيمياء", create.data["subjects"])
        self.assertIn("عربي", create.data["subjects"])
        student_id = create.data["id"]
        self.assertEqual(Subject.objects.filter(students__id=student_id).count(), 4)

        again = self.client.post(
            "/api/students/",
            {
                "first_name": "سامي",
                "last_name": "حسن",
                "special_number": "6601",
                "student_class": "10",
                "parent_number": "0933111222",
                "student_number": "5544",
                "address": "اللاذقية",
                "personal_notes": "مادة خامسة",
                "is_payer": False,
                "subjects": ["تاريخ"],
            },
            format="json",
        )
        self.assertIn(again.status_code, (200, 201), again.data)
        self.assertEqual(again.data["id"], student_id)
        self.assertIn("تاريخ", again.data["subjects"])
        self.assertIn("رياضيات", again.data["subjects"])
        self.assertEqual(Student.objects.filter(special_number="6601").count(), 1)

        listed = self.client.post(
            "/api/students/",
            {
                "first_name": "ليلى",
                "last_name": "خالد",
                "special_number": "6602",
                "student_class": "11",
                "parent_number": "0933111333",
                "student_number": "5566",
                "address": "دمشق",
                "is_payer": False,
                "subjects": ["وطنية", "فلسفة", "انكليزي"],
            },
            format="json",
        )
        self.assertEqual(listed.status_code, 201, listed.data)
        self.assertEqual(set(listed.data["subjects"]), {"وطنية", "فلسفة", "انكليزي"})

        path_student = self.client.post(
            "/api/students/",
            {
                "first_name": "هناء",
                "last_name": "علي",
                "special_number": "6603",
                "student_class": "بكالوريا",
                "parent_number": "0933111444",
                "student_number": "5577",
                "address": "حمص",
                "is_payer": False,
                "class1": "بكالوريا",
                "class2": "علمي",
                "class3": "الشعبة الأولى",
                "subjects": ["رياضيات"],
            },
            format="json",
        )
        self.assertEqual(path_student.status_code, 201, path_student.data)
        self.assertIn("بكالوريا", path_student.data["class1"])
        self.assertIn("علمي", path_student.data["class1"])
        self.assertEqual(path_student.data["class3"], "الشعبة الأولى")
        listing = self.client.get("/api/students/")
        self.assertIsInstance(listing.data, list)
        row = next(item for item in listing.data if item["id"] == path_student.data["id"])
        self.assertIn("بكالوريا", row["class1"])
        self.assertIn("علمي", row["class1"])

    def test_student_edit_post_path_and_subjects_list(self):
        """شاشة تعديل المسار: POST /api/students/edit-post/{id}/ مع subjects_list."""
        student = self._make_student("6701")
        payload = {
            "class1": "بكالوريا، علمي",
            "class2": "عربي، انكليزي، فرنسي، علوم، فيزياء، كيمياء، رياضيات، وطنية، ديانة",
            "class3": "الشعبة الأولى",
            "student_class": "1",
            "subjects_list": [
                "عربي",
                "انكليزي",
                "فرنسي",
                "علوم",
                "فيزياء",
                "كيمياء",
                "رياضيات",
                "وطنية",
                "ديانة",
            ],
        }
        response = self.client.post(
            f"/api/students/edit-post/{student.id}/", payload, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["class1"], "بكالوريا، علمي")
        self.assertIn("رياضيات", response.data["class2"])
        self.assertEqual(response.data["class3"], "الشعبة الأولى")
        self.assertIn("رياضيات", response.data["subjects_list"])
        self.assertEqual(len(response.data["subjects_list"]), 9)
        student.refresh_from_db()
        self.assertEqual(student.subjects.count(), 9)
        self.assertEqual(student.student_class, "1")

    def test_delete_student_is_permanent_everywhere(self):
        """الحذف يزيل الطالب وحسابه ودفعاته من قاعدة البيانات نهائياً."""
        student = self._make_student("9099")
        pay = self.client.post(
            "/api/payments/",
            {"student": "9099", "FullAmount": "500"},
            format="json",
        )
        self.assertIn(pay.status_code, (200, 201), pay.data)
        self.assertTrue(Payment.objects.filter(student=student).exists())

        delete = self.client.delete(f"/api/students/{student.id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Student.objects.filter(pk=student.id).exists())
        self.assertFalse(User.objects.filter(special_number="9099").exists())
        self.assertFalse(Payment.objects.filter(student_id=student.id).exists())
        # الرقم متاح فوراً لطالب جديد
        recreate = self._make_student("9099")
        self.assertIsNotNone(recreate.pk)

    def test_database_engine_stays_postgresql(self):
        """قاعدة المشروع PostgreSQL — أي تحول صامت إلى SQLite يجب أن يفشل الاختبار."""
        from django.conf import settings

        engine = settings.DATABASES["default"]["ENGINE"]
        self.assertEqual(engine, "django.db.backends.postgresql", engine)
        self.assertNotIn("sqlite", engine)

    def test_cors_preflight_allows_authorization_header(self):
        """
        preflight يجب أن يذكر Authorization صراحة؛ البدل "*" مرفوض من المتصفح
        مع Allow-Credentials فيبدو زر الدفع وكأنه لا يعمل.
        """
        response = self.client.options(
            "/api/payments/",
            HTTP_ORIGIN="https://frontend.example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        self.assertEqual(response.status_code, 200)
        allow_headers = response["access-control-allow-headers"].lower()
        allow_methods = response["access-control-allow-methods"].upper()
        self.assertNotEqual(allow_headers.strip(), "*")
        self.assertIn("authorization", allow_headers)
        self.assertIn("content-type", allow_headers)
        self.assertIn("POST", allow_methods)
        self.assertIn("PUT", allow_methods)
        self.assertIn("PATCH", allow_methods)
        self.assertIn("DELETE", allow_methods)

        put_preflight = self.client.options(
            "/api/students/00000000-0000-0000-0000-000000000001/",
            HTTP_ORIGIN="https://frontend.example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="PUT",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type,ngrok-skip-browser-warning",
        )
        self.assertEqual(put_preflight.status_code, 200)
        put_headers = put_preflight["access-control-allow-headers"].lower()
        put_methods = put_preflight["access-control-allow-methods"].upper()
        self.assertIn("authorization", put_headers)
        self.assertIn("ngrok-skip-browser-warning", put_headers)
        self.assertIn("PUT", put_methods)

    def test_reuse_special_number_after_hard_delete(self):
        """بعد حذف طالب نهائياً برقم 22 يمكن إنشاء طالب جديد بنفس الرقم."""
        create = self.client.post(
            "/api/students/",
            {
                "first_name": "قديم",
                "last_name": "محذوف",
                "special_number": 22,
                "student_class": 10,
                "parent_number": "0933111222",
                "student_number": "5544",
                "address": "عنوان قديم",
                "personal_notes": "قديم",
                "is_payer": False,
                "class1": "رياضيات",
                "class2": "فيزياء",
                "class3": "كيمياء",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        old_id = create.data["id"]
        delete = self.client.delete(f"/api/students/{old_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Student.objects.filter(pk=old_id).exists())
        recreate = self.client.post(
            "/api/students/",
            {
                "first_name": "جديد",
                "last_name": "طالب",
                "special_number": 22,
                "student_class": 10,
                "parent_number": "0933111333",
                "student_number": "5566",
                "address": "عنوان جديد",
                "personal_notes": "جديد",
                "is_payer": False,
                "class1": "رياضيات",
                "class2": "فيزياء",
                "class3": "كيمياء",
            },
            format="json",
        )
        self.assertEqual(recreate.status_code, 201, recreate.data)
        self.assertEqual(str(recreate.data["special_number"]), "22")
        self.assertNotEqual(recreate.data["id"], old_id)

    def test_post_patch_delete_manager(self):
        """طلبات post manager و patch manager و delete user."""
        create = self.client.post(
            "/api/managers/",
            {
                "username": "ammar_manager_99",
                "password": "password123",
                "first_name": "Ammar",
                "last_name": "Admin",
                "special_number": "99",
                "user_type": "1",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        manager_id = create.data["id"]
        patch = self.client.patch(
            f"/api/managers/{manager_id}/",
            {"first_name": "Ammar"},
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        delete = self.client.delete(f"/api/managers/{manager_id}/")
        self.assertEqual(delete.status_code, 204)

    def test_exams_post_patch_delete(self):
        """طلبات exams post و patch exams و delete exams."""
        student = self._make_student("555")
        create = self.client.post(
            "/api/exams/",
            {
                "student": [str(student.id)],
                "special_number": "3",
                "Nameofexam": "math infinity",
                "Subject_name": "math",
                "Date": "2026-03-10",
                "Itsnote": "yes",
                "Mark": 90,
                "Full_mark": 100,
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)

        frontend = self.client.post(
            "/api/exams/",
            {
                "student": str(student.id),
                "nameofexam": "مذاكرة 1",
                "subject_name": "رياضيات",
                "date": "2026-08-22",
                "mark": "17.5",
                "full_mark": "20",
                "class1": "بكالوريا",
                "class2": "علمي",
                "class3": "الشعبة الأولى",
                "itsnote": "جيد",
            },
            format="json",
        )
        self.assertEqual(frontend.status_code, 201, frontend.data)
        self.assertEqual(frontend.data["Nameofexam"], "مذاكرة 1")
        self.assertEqual(frontend.data["Mark"], 18)
        self.assertEqual(frontend.data["special_number"], student.special_number)

        exam_id = create.data["id"]
        patch = self.client.patch(
            f"/api/exams/{exam_id}/",
            {
                "student": [str(student.id)],
                "special_number": "1234567",
                "Nameofexam": "math infinity",
                "Subject_name": "math",
                "Date": "2026-03-10",
                "Itsnote": "yes",
                "Mark": 90,
                "Full_mark": 100,
            },
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        delete = self.client.delete(f"/api/exams/{exam_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Exam.objects.filter(pk=exam_id).exists())

    def test_pay_post_patch_delete(self):
        """طلبات pay post و pay patch و pay delete."""
        student = self._make_student("556")
        create = self.client.post(
            "/api/payments/",
            {
                "student": str(student.id),
                "FullAmount": "1000.00",
                "PaidAmount": "750.00",
                "Paymentresult": "250.00",
            },
            format="json",
        )
        self.assertIn(create.status_code, (200, 201))
        self.assertEqual(Decimal(create.data["Paymentresult"]), Decimal("250.00"))
        self.assertTrue(PaymentTransaction.objects.filter(payment_id=create.data["id"]).exists())
        pay_id = create.data["id"]
        patch = self.client.patch(
            f"/api/payments/{pay_id}/",
            {
                "student": str(student.id),
                "FullAmount": 1200.00,
                "PaidAmount": 500.00,
            },
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        delete = self.client.delete(f"/api/payments/{pay_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Payment.objects.filter(pk=pay_id).exists())

    def test_installment_manager_appends_rows_and_filters_by_student(self):
        """شاشة الأقساط: كل دفعة صف جديد، والقائمة تُفلتر بـ ?student=."""
        student = self._make_student("9901")
        other = self._make_student("9902")
        self.client.post(
            "/api/payments/",
            {
                "student": str(other.id),
                "FullAmount": "999.00",
                "PaidAmount": "999.00",
                "Paymentresult": "0.00",
            },
            format="json",
        )

        first = self.client.post(
            "/api/payments/",
            {
                "student": str(student.id),
                "FullAmount": "5000.00",
                "PaidAmount": "1000.00",
                "Paymentresult": "4000.00",
            },
            format="json",
        )
        self.assertIn(first.status_code, (200, 201), first.data)
        self.assertEqual(Decimal(first.data["PaidAmount"]), Decimal("1000.00"))
        self.assertEqual(Decimal(first.data["Paymentresult"]), Decimal("4000.00"))

        second = self.client.post(
            "/api/payments/",
            {
                "student": str(student.id),
                "FullAmount": "5000.00",
                "PaidAmount": "1000.00",
                "Paymentresult": "3000.00",
            },
            format="json",
        )
        self.assertIn(second.status_code, (200, 201), second.data)
        self.assertNotEqual(first.data["id"], second.data["id"])
        self.assertEqual(Decimal(second.data["PaidAmount"]), Decimal("1000.00"))
        self.assertEqual(Decimal(second.data["Paymentresult"]), Decimal("3000.00"))
        self.assertEqual(Payment.objects.filter(student=student).count(), 2)

        listing = self.client.get(f"/api/payments/?student={student.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertIsInstance(listing.data, list, listing.data)
        self.assertEqual(len(listing.data), 2)
        self.assertTrue(all(str(row["student"]) == str(student.id) for row in listing.data))
        total_paid = sum(Decimal(row["PaidAmount"]) for row in listing.data)
        self.assertEqual(total_paid, Decimal("2000.00"))
        self.assertEqual(Decimal(listing.data[-1]["FullAmount"]), Decimal("5000.00"))
        self.assertEqual(str(listing.data[0]["id"]), str(first.data["id"]))
        self.assertEqual(str(listing.data[1]["id"]), str(second.data["id"]))

        last = self.client.post(
            "/api/payments/",
            {
                "student": str(student.id),
                "FullAmount": "5000.00",
                "PaidAmount": "3000.00",
                "Paymentresult": "0.00",
            },
            format="json",
        )
        self.assertIn(last.status_code, (200, 201), last.data)
        self.assertEqual(Decimal(last.data["Paymentresult"]), Decimal("0.00"))
        self.assertEqual(Payment.objects.filter(student=student).count(), 3)

        mark_paid = self.client.patch(
            f"/api/students/{student.id}/",
            {"is_payer": True},
            format="json",
        )
        self.assertEqual(mark_paid.status_code, 200, mark_paid.data)
        student.refresh_from_db()
        self.assertTrue(student.is_payer)

        for pay in Payment.objects.filter(student=student):
            deleted = self.client.delete(f"/api/payments/{pay.id}/")
            self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Payment.objects.filter(student=student).exists())

        # تحديث القسط الكلي بدون دفعة لا يمحو المدفوع السابق
        other_student = self._make_student("9903")
        self.client.post(
            "/api/payments/",
            {
                "student": str(other_student.id),
                "FullAmount": "4000.00",
                "PaidAmount": "1000.00",
                "Paymentresult": "3000.00",
            },
            format="json",
        )
        bump = self.client.post(
            "/api/payments/",
            {
                "student": str(other_student.id),
                "FullAmount": "6000.00",
                "PaidAmount": "0.00",
                "Paymentresult": "5000.00",
            },
            format="json",
        )
        self.assertIn(bump.status_code, (200, 201), bump.data)
        self.assertEqual(Payment.objects.filter(student=other_student).count(), 1)
        row = Payment.objects.get(student=other_student)
        self.assertEqual(row.PaidAmount, Decimal("1000.00"))
        self.assertEqual(row.FullAmount, Decimal("6000.00"))
        self.assertEqual(row.Paymentresult, Decimal("5000.00"))

    def test_full_payment_button_patterns(self):
        """زر دفعة كاملة يعمل بعدة أشكال طلب من الفرونت."""
        student = self._make_student("778")

        # 1) payment_type=full بدون PaidAmount
        create = self.client.post(
            "/api/payments/",
            {
                "student": str(student.id),
                "FullAmount": "1000.00",
                "payment_type": "full",
            },
            format="json",
        )
        self.assertIn(create.status_code, (200, 201), create.data)
        self.assertEqual(Decimal(create.data["PaidAmount"]), Decimal("1000.00"))
        self.assertEqual(Decimal(create.data["Paymentresult"]), Decimal("0.00"))
        self.assertEqual(create.data["payment_type"], "full")
        student.refresh_from_db()
        self.assertTrue(student.is_payer)

        # 2) مسار /api/payments/full/ مع special_number
        other = self._make_student("779")
        full_endpoint = self.client.post(
            "/api/payments/full/",
            {
                "special_number": "779",
                "FullAmount": "500",
            },
            format="json",
        )
        self.assertIn(full_endpoint.status_code, (200, 201), full_endpoint.data)
        self.assertEqual(Decimal(full_endpoint.data["PaidAmount"]), Decimal("500.00"))
        self.assertEqual(Decimal(full_endpoint.data["Paymentresult"]), Decimal("0.00"))

        # 3) إكمال دفعة موجودة
        installment = self.client.post(
            "/api/payments/",
            {
                "student": str(other.id),
                "FullAmount": "800",
                "PaidAmount": "200",
            },
            format="json",
        )
        self.assertIn(installment.status_code, (200, 201))
        pay_id = installment.data["id"]
        finish = self.client.post(f"/api/payments/{pay_id}/pay-full/", {}, format="json")
        self.assertEqual(finish.status_code, 200, finish.data)
        self.assertEqual(Decimal(finish.data["PaidAmount"]), Decimal("800.00"))
        self.assertEqual(Decimal(finish.data["Paymentresult"]), Decimal("0.00"))

        # 4) الشكل الأشيع من الفرونت: student=الرقم المميز + FullAmount فقط
        third = self._make_student("780")
        by_special = self.client.post(
            "/api/payments/",
            {"student": "780", "FullAmount": "300"},
            format="json",
        )
        self.assertIn(by_special.status_code, (200, 201), by_special.data)
        self.assertEqual(Decimal(by_special.data["PaidAmount"]), Decimal("300.00"))
        self.assertEqual(Decimal(by_special.data["Paymentresult"]), Decimal("0.00"))

        # 5) كائن طالب متداخل
        fourth = self._make_student("781")
        nested = self.client.post(
            "/api/payments/",
            {"student": {"special_number": "781"}, "FullAmount": 450},
            format="json",
        )
        self.assertIn(nested.status_code, (200, 201), nested.data)
        self.assertEqual(Decimal(nested.data["PaidAmount"]), Decimal("450.00"))

        # 6) بدون شرطة مائلة أخيرة — كان يضيع جسم POST
        fifth = self._make_student("782")
        no_slash = self.client.post(
            "/api/payments",
            {"student": "782", "FullAmount": "250"},
            format="json",
        )
        self.assertIn(no_slash.status_code, (200, 201), no_slash.data)
        self.assertTrue(no_slash.data.get("success"))

        # 7) مرادف /api/pay/
        sixth = self._make_student("783")
        alias = self.client.post(
            "/api/pay/",
            {"student": str(sixth.id), "FullAmount": "150"},
            format="json",
        )
        self.assertIn(alias.status_code, (200, 201), alias.data)

        # 8) زر الدفع من بطاقة الطالب
        seventh = self._make_student("784")
        student_pay = self.client.post(
            f"/api/students/{seventh.special_number}/pay/",
            {"FullAmount": "900"},
            format="json",
        )
        self.assertIn(student_pay.status_code, (200, 201), student_pay.data)
        seventh.refresh_from_db()
        self.assertTrue(seventh.is_payer)

        # 9) PATCH isPayer camelCase + مبلغ
        eighth = self._make_student("785")
        patch_payer = self.client.patch(
            f"/api/students/{eighth.id}/",
            {"isPayer": True, "FullAmount": "400"},
            format="json",
        )
        self.assertEqual(patch_payer.status_code, 200, patch_payer.data)
        eighth.refresh_from_db()
        self.assertTrue(eighth.is_payer)
        self.assertTrue(Payment.objects.filter(student=eighth, Paymentresult=0).exists())

        # 10) PaidAmount فارغ كنص — خطأ شائع من نماذج الفرونت
        ninth = self._make_student("786")
        empty_paid = self.client.post(
            "/api/payments/",
            {
                "student": "786",
                "FullAmount": "600",
                "PaidAmount": "",
                "Paymentresult": "",
                "payment_type": "full",
            },
            format="json",
        )
        self.assertIn(empty_paid.status_code, (200, 201), empty_paid.data)
        self.assertEqual(Decimal(empty_paid.data["PaidAmount"]), Decimal("600.00"))

    def test_payment_lookup_by_special_number_fills_student_fields(self):
        """إدخال الرقم المميز في شاشة المدفوعات يعيد بقية معلومات الطالب."""
        student = self._make_student("4501")
        lookup = self.client.get("/api/payments/lookup/?special_number=4501")
        self.assertEqual(lookup.status_code, 200, lookup.data)
        self.assertTrue(lookup.data["found"])
        self.assertEqual(lookup.data["special_number"], "4501")
        self.assertEqual(lookup.data["student_name"], "طالب تجربة")
        self.assertEqual(lookup.data["student_class"], "10")
        self.assertEqual(lookup.data["parent_number"], "1234567890")
        # حتى بلا دفعات سابقة تظهر البيانات بأصفار بدل قائمة فارغة
        self.assertEqual(lookup.data["payments_count"], 0)
        self.assertEqual(lookup.data["Paymentresult"], "0.00")

        # بعد الدفع يعكس الملخّص المبالغ الحقيقية
        self.client.post(
            "/api/payments/", {"special_number": "4501", "FullAmount": "700"}, format="json"
        )
        after = self.client.get("/api/payments/lookup/?special_number=4501")
        self.assertEqual(after.data["PaidAmount"], "700.00")
        self.assertEqual(after.data["total_remaining"], "0.00")
        self.assertTrue(after.data["is_payer"])

        # نفس البيانات عبر مسار الطالب
        via_student = self.client.get(f"/api/students/{student.special_number}/payments/")
        self.assertEqual(via_student.status_code, 200)
        self.assertEqual(via_student.data["student_name"], "طالب تجربة")

        # رقم غير موجود يعطي 404 واضحاً بدل قائمة فارغة
        missing = self.client.get("/api/payments/lookup/?special_number=999999")
        self.assertEqual(missing.status_code, 404)
        self.assertFalse(missing.data["found"])

    def test_payment_response_carries_student_details(self):
        """استجابة الدفع تحمل اسم الطالب وصفه حتى تملأ الواجهة الحقول."""
        self._make_student("4502")
        pay = self.client.post(
            "/api/payments/full/",
            {"special_number": "4502", "FullAmount": "300"},
            format="json",
        )
        self.assertIn(pay.status_code, (200, 201), pay.data)
        self.assertEqual(pay.data["student_name"], "طالب تجربة")
        self.assertEqual(pay.data["student_class"], "10")
        self.assertEqual(pay.data["special_number"], "4502")
        self.assertIn("student_details", pay.data)

    def test_full_payment_button_with_only_special_number(self):
        """زر دفعة كاملة بالرقم المميز وحده: يسدّد المتبقي ولا يكرر الدفع."""
        student = self._make_student("4503")
        self.client.post(
            "/api/payments/",
            {"special_number": "4503", "FullAmount": "900", "PaidAmount": "300"},
            format="json",
        )
        # الضغط بالرقم المميز فقط يكمل المتبقي
        full = self.client.post("/api/payments/full/", {"special_number": "4503"}, format="json")
        self.assertEqual(full.status_code, 200, full.data)
        self.assertEqual(Decimal(full.data["PaidAmount"]), Decimal("900.00"))
        self.assertEqual(Decimal(full.data["Paymentresult"]), Decimal("0.00"))
        student.refresh_from_db()
        self.assertTrue(student.is_payer)

        # ضغطة ثانية لا تُنشئ دفعة جديدة ولا تُرجع خطأ
        again = self.client.post("/api/payments/full/", {"special_number": "4503"}, format="json")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertTrue(again.data.get("already_paid"))
        self.assertEqual(Payment.objects.filter(student=student).count(), 1)

    def test_reset_payment_button(self):
        """زر تصفير الدفع يُرجع المدفوع إلى صفر ويلغي حالة السداد."""
        student = self._make_student("4504")
        self.client.post(
            "/api/payments/full/",
            {"special_number": "4504", "FullAmount": "500"},
            format="json",
        )
        student.refresh_from_db()
        self.assertTrue(student.is_payer)

        reset = self.client.post("/api/payments/reset/", {"special_number": "4504"}, format="json")
        self.assertEqual(reset.status_code, 200, reset.data)
        self.assertEqual(reset.data["reset_count"], 1)

        student.refresh_from_db()
        self.assertFalse(student.is_payer)
        payment = Payment.objects.get(student=student)
        self.assertEqual(payment.PaidAmount, Decimal("0.00"))
        # القسط الكلي يبقى كما هو والمتبقي يعود كاملاً
        self.assertEqual(payment.FullAmount, Decimal("500.00"))
        self.assertEqual(payment.Paymentresult, Decimal("500.00"))
        # حركة مالية عكسية للتدقيق
        self.assertTrue(
            PaymentTransaction.objects.filter(payment=payment, note="تصفير الدفع").exists()
        )

        # المسارات البديلة تعمل أيضاً
        self.client.post("/api/payments/full/", {"special_number": "4504"}, format="json")
        by_number = self.client.post("/api/payments/4504/reset/", {}, format="json")
        self.assertEqual(by_number.status_code, 200, by_number.data)
        self.client.post("/api/payments/full/", {"special_number": "4504"}, format="json")
        by_student = self.client.post(f"/api/students/4504/reset-payment/", {}, format="json")
        self.assertEqual(by_student.status_code, 200, by_student.data)
        student.refresh_from_db()
        self.assertFalse(student.is_payer)

    def test_payment_post_not_redirected_when_https_flag_set(self):
        """خلف Render: IS_HTTPS لا يجب أن يحوّل POST الدفع إلى 301."""
        from django.test import override_settings

        student = self._make_student("787")
        with override_settings(DEBUG=False, IS_HTTPS=True, SECURE_SSL_REDIRECT=True):
            response = self.client.post(
                "/api/payments/",
                {"student": "787", "FullAmount": "100", "PaidAmount": ""},
                format="json",
                secure=False,
            )
        self.assertNotEqual(response.status_code, 301, response.get("Location"))
        self.assertIn(response.status_code, (200, 201), getattr(response, "data", response.content))

    def test_frontend_confirm_payment_and_reset_put(self):
        """يطابق كود الواجهة حرفياً: search ثم confirm-payment، وPUT is_payer=false."""
        student = self._make_student("8801")
        other = self._make_student("8802")
        self.client.post(
            "/api/payments/",
            {"special_number": "8801", "FullAmount": "400", "PaidAmount": "100"},
            format="json",
        )

        search = self.client.get("/api/students/?search=8801")
        self.assertEqual(search.status_code, 200)
        self.assertIsInstance(search.data, list, search.data)
        self.assertGreaterEqual(len(search.data), 1)
        self.assertEqual(str(search.data[0]["special_number"]), "8801")
        found_id = search.data[0]["id"]

        confirm = self.client.post(f"/api/students/{found_id}/confirm-payment/", {}, format="json")
        self.assertEqual(confirm.status_code, 200, confirm.data)
        student.refresh_from_db()
        self.assertTrue(student.is_payer)

        listing = self.client.get("/api/students/")
        self.assertEqual(listing.status_code, 200)
        self.assertIsInstance(listing.data, list, listing.data)
        self.assertGreaterEqual(len(listing.data), 2)

        reset_put = self.client.put(
            f"/api/students/{found_id}/",
            {
                "is_payer": False,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "special_number": student.special_number,
                "student_class": student.student_class,
            },
            format="json",
        )
        self.assertEqual(reset_put.status_code, 200, reset_put.data)
        student.refresh_from_db()
        self.assertFalse(student.is_payer)

        student.is_payer = True
        student.save(update_fields=["is_payer"])
        bulk = self.client.post("/api/students/reset-all-payments/", {}, format="json")
        self.assertEqual(bulk.status_code, 200, bulk.data)
        student.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(student.is_payer)
        self.assertFalse(other.is_payer)

        # جسم فارغ لطالب بلا قسط مسجّل — الواجهة ترسل POST {} فقط
        confirm_empty = self.client.post(
            f"/api/students/{other.id}/confirm-payment/", {}, format="json"
        )
        self.assertEqual(confirm_empty.status_code, 200, confirm_empty.data)
        other.refresh_from_db()
        self.assertTrue(other.is_payer)

        paged = self.client.get("/api/students/?page=1")
        self.assertEqual(paged.status_code, 200)
        self.assertIn("results", paged.data)

    def test_time_table_post_patch_delete(self):
        """طلبات time table post و time table putch و time table delete."""
        student = self._make_student("557")
        teacher = self._make_teacher("888")
        payload = {
            "student": [str(student.id)],
            "Day": "2026-03-06",
            "Hour": "17:50:51",
            "Subject": "Mathematics",
            "Teacher": str(teacher.id),
        }
        create = self.client.post("/api/time_table/", payload, format="json")
        self.assertEqual(create.status_code, 201)
        row_id = create.data["id"]
        patch = self.client.patch(f"/api/time_table/{row_id}/", payload, format="json")
        self.assertEqual(patch.status_code, 200)
        delete = self.client.delete(f"/api/time_table/{row_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(TimeTable.objects.filter(pk=row_id).exists())

        from attendance.models import Attendance

        student = self._make_student("558")
        teacher = self._make_teacher("887")
        frontend = self.client.post(
            "/api/time_table/",
            {
                "student": [str(student.id)],
                "day": "2026-08-24",
                "hour": "14:30:45",
                "subject": "رياضيات",
                "teacher": str(teacher.id),
            },
            format="json",
        )
        self.assertEqual(frontend.status_code, 201, frontend.data)
        self.assertEqual(frontend.data["Subject"], "رياضيات")
        self.assertTrue(
            Attendance.objects.filter(
                student=student, Date="2026-08-24", Status=Attendance.STATUS_PRESENT
            ).exists()
        )

        no_teacher = self.client.post(
            "/api/time_table/",
            {
                "student": [str(student.id)],
                "day": "2026-08-25",
                "hour": "9:05:01 AM",
                "subject": "فيزياء",
            },
            format="json",
        )
        self.assertEqual(no_teacher.status_code, 201, no_teacher.data)

    def test_admin_attendance_saves_present_and_absent_students(self):
        """شاشة تحضير المدير: POST /api/time_table/ بـ present_students و absent_students."""
        from attendance.models import Attendance
        from academics.subjects import apply_subjects

        present = self._make_student("5601")
        absent = self._make_student("5602")
        other = self._make_student("5603")
        present.class1 = "بكالوريا علمي"
        present.class3 = "الشعبة الأولى"
        present.save(update_fields=["class1", "class3"])
        apply_subjects(present, ["رياضيات"], merge=False)
        absent.class1 = "بكالوريا علمي"
        absent.class3 = "الشعبة الأولى"
        absent.save(update_fields=["class1", "class3"])
        apply_subjects(absent, ["رياضيات"], merge=False)
        other.class1 = "بكالوريا علمي"
        other.class3 = "الشعبة الثانية"
        other.save(update_fields=["class1", "class3"])
        teacher = self._make_teacher("5604")

        listing = self.client.get("/api/students/")
        self.assertEqual(listing.status_code, 200, listing.data)
        rows = listing.data["results"] if isinstance(listing.data, dict) else listing.data
        present_row = next(item for item in rows if str(item["id"]) == str(present.id))
        self.assertIn("رياضيات", present_row["subjects"])
        self.assertIn("رياضيات", present_row["registered_subjects"])
        self.assertIn("رياضيات", present_row["subject_names"])
        self.assertIn("بكالوريا", present_row["class1"])
        self.assertEqual(present_row["class3"], "الشعبة الأولى")

        payload = {
            "present_students": [str(present.id)],
            "absent_students": [str(absent.id)],
            "day": "2026-08-30",
            "hour": "14:32:05",
            "subject": "رياضيات",
            "level": "بكالوريا",
            "section": "الشعبة الأولى",
            "teacher": str(teacher.id),
        }
        saved = self.client.post("/api/time_table/", payload, format="json")
        self.assertIn(saved.status_code, (200, 201), saved.data)
        self.assertEqual(
            Attendance.objects.get(student=present, Date="2026-08-30").Status,
            Attendance.STATUS_PRESENT,
        )
        self.assertEqual(
            Attendance.objects.get(student=absent, Date="2026-08-30").Status,
            Attendance.STATUS_ABSENT,
        )
        self.assertFalse(
            Attendance.objects.filter(student=other, Date="2026-08-30").exists()
        )

        flipped = dict(payload)
        flipped["present_students"] = [str(absent.id)]
        flipped["absent_students"] = [str(present.id)]
        again = self.client.post("/api/time_table/", flipped, format="json")
        self.assertIn(again.status_code, (200, 201), again.data)
        self.assertEqual(TimeTable.objects.filter(Day="2026-08-30", Subject="رياضيات").count(), 1)
        self.assertEqual(
            Attendance.objects.get(student=present, Date="2026-08-30").Status,
            Attendance.STATUS_ABSENT,
        )
        self.assertEqual(
            Attendance.objects.get(student=absent, Date="2026-08-30").Status,
            Attendance.STATUS_PRESENT,
        )

        everyone_absent = dict(payload)
        everyone_absent["present_students"] = []
        everyone_absent["absent_students"] = [str(present.id), str(absent.id)]
        all_out = self.client.post("/api/time_table/", everyone_absent, format="json")
        self.assertIn(all_out.status_code, (200, 201), all_out.data)
        self.assertEqual(
            Attendance.objects.filter(Date="2026-08-30", Status=Attendance.STATUS_ABSENT).count(),
            2,
        )

    def test_student_time_table_list_matches_attendance_page(self):
        """شاشة حضور الطالب: GET /api/time_table/?student_id= مع Date و Status."""
        from attendance.models import Attendance

        present = self._make_student("5611")
        absent = self._make_student("5612")
        teacher = self._make_teacher("5613")
        saved = self.client.post(
            "/api/time_table/",
            {
                "present_students": [str(present.id)],
                "absent_students": [str(absent.id)],
                "day": "2026-08-30",
                "hour": "14:32:05",
                "subject": "math",
                "teacher": str(teacher.id),
            },
            format="json",
        )
        self.assertIn(saved.status_code, (200, 201), saved.data)

        only_absent = self.client.post(
            "/api/attendance/",
            {
                "student": str(present.id),
                "Date": "2026-08-31",
                "Status": "غياب",
            },
            format="json",
        )
        self.assertEqual(only_absent.status_code, 201, only_absent.data)

        login = APIClient().post(
            "/api/student-login/",
            {"special_number": present.special_number},
            format="json",
        )
        client = APIClient()
        listing = client.get(
            f"/api/time_table/?student_id={present.id}",
            HTTP_AUTHORIZATION=f"StudentToken {login.data['access']}",
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertIsInstance(listing.data, list, listing.data)
        by_date = {row["Date"]: row for row in listing.data}
        self.assertEqual(by_date["2026-08-30"]["Status"], Attendance.STATUS_PRESENT)
        self.assertEqual(by_date["2026-08-30"]["status"], "حضور")
        self.assertTrue(by_date["2026-08-30"]["is_present"])
        self.assertEqual(by_date["2026-08-30"]["subject"], "رياضيات")
        self.assertEqual(by_date["2026-08-30"]["Subject"], "رياضيات")
        self.assertEqual(by_date["2026-08-31"]["Status"], Attendance.STATUS_ABSENT)
        self.assertFalse(by_date["2026-08-31"]["is_present"])

        absent_login = APIClient().post(
            "/api/student-login/",
            {"special_number": absent.special_number},
            format="json",
        )
        absent_list = APIClient().get(
            f"/api/time_table/?student_id={absent.id}",
            HTTP_AUTHORIZATION=f"StudentToken {absent_login.data['access']}",
        )
        self.assertEqual(absent_list.status_code, 200, absent_list.data)
        absent_row = next(row for row in absent_list.data if row["Date"] == "2026-08-30")
        self.assertEqual(absent_row["Status"], "غياب")
        self.assertFalse(absent_row["is_present"])
        self.assertEqual(absent_row["subject"], "رياضيات")

    def test_student_attendance_list_uses_status_and_date(self):
        """شاشة حضور الطالب: GET /api/attendance/ يعيد Status و Date ومرادفات الفرونت."""
        from attendance.models import Attendance

        student = self._make_student("5591")
        teacher = self._make_teacher("5592")
        present = self.client.post(
            "/api/time_table/",
            {
                "student": [str(student.id)],
                "day": "2026-08-20",
                "hour": "10:00:00",
                "subject": "رياضيات",
                "teacher": str(teacher.id),
            },
            format="json",
        )
        self.assertEqual(present.status_code, 201, present.data)
        absent = self.client.post(
            "/api/attendance/",
            {
                "student": str(student.id),
                "Date": "2026-08-21",
                "Status": "غياب",
            },
            format="json",
        )
        self.assertEqual(absent.status_code, 201, absent.data)

        login = APIClient().post(
            "/api/student-login/",
            {"special_number": student.special_number},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        client = APIClient()
        listing = client.get(
            f"/api/attendance/?student_id={student.id}",
            HTTP_AUTHORIZATION=f"StudentToken {login.data['access']}",
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertIsInstance(listing.data, list, listing.data)
        rows = listing.data
        by_date = {row["Date"]: row for row in rows}
        self.assertIn("2026-08-20", by_date)
        self.assertIn("2026-08-21", by_date)
        self.assertEqual(by_date["2026-08-20"]["Status"], Attendance.STATUS_PRESENT)
        self.assertEqual(by_date["2026-08-20"]["status"], "حضور")
        self.assertEqual(by_date["2026-08-20"]["attendance_status"], "حضور")
        self.assertTrue(by_date["2026-08-20"]["is_present"])
        self.assertEqual(by_date["2026-08-20"]["subject"], "رياضيات")
        self.assertEqual(by_date["2026-08-20"]["subject_name"], "رياضيات")
        self.assertEqual(by_date["2026-08-20"]["Subject"], "رياضيات")
        self.assertEqual(by_date["2026-08-20"]["date"], "2026-08-20")
        self.assertEqual(by_date["2026-08-20"]["day"], "2026-08-20")
        self.assertEqual(by_date["2026-08-20"]["session_date"], "2026-08-20")
        self.assertEqual(by_date["2026-08-21"]["Status"], Attendance.STATUS_ABSENT)
        self.assertEqual(by_date["2026-08-21"]["status"], "غياب")
        self.assertFalse(by_date["2026-08-21"]["is_present"])
        self.assertGreaterEqual(rows[0]["Date"], rows[-1]["Date"])

        table = client.get(
            "/api/time_table/",
            HTTP_AUTHORIZATION=f"StudentToken {login.data['access']}",
        )
        self.assertEqual(table.status_code, 200, table.data)
        lessons = table.data["results"] if isinstance(table.data, dict) else table.data
        math = next(row for row in lessons if row.get("Subject") == "رياضيات")
        self.assertEqual(math["Status"], "حضور")
        self.assertEqual(math["status"], "حضور")
        self.assertTrue(math["is_present"])

    def test_student_attendance_syncs_old_time_table_rows(self):
        """حصة time_table بلا سجل حضور تظهر بعد GET /api/attendance/?student_id=."""
        from datetime import time

        from attendance.models import Attendance
        from schedule.models import TimeTable

        student = self._make_student("5593")
        lesson = TimeTable.objects.create(
            Day="2026-08-22",
            Hour=time(11, 0),
            Subject="عربي",
        )
        lesson.student.add(student)
        self.assertFalse(
            Attendance.objects.filter(student=student, Date="2026-08-22").exists()
        )

        login = APIClient().post(
            "/api/student-login/",
            {"special_number": student.special_number},
            format="json",
        )
        client = APIClient()
        listing = client.get(
            f"/api/attendance/?student_id={student.id}",
            HTTP_AUTHORIZATION=f"StudentToken {login.data['access']}",
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertIsInstance(listing.data, list, listing.data)
        row = next(item for item in listing.data if item["Date"] == "2026-08-22")
        self.assertEqual(row["Status"], "حضور")
        self.assertTrue(row["is_present"])
        self.assertEqual(row["Subject"], "عربي")
        self.assertTrue(
            Attendance.objects.filter(
                student=student, Date="2026-08-22", Status=Attendance.STATUS_PRESENT
            ).exists()
        )

    def test_program_get_and_create(self):
        """طلب program: GET /api/programs/ مع إمكانية الإنشاء بنفس الحقول."""
        teacher = self._make_teacher("889")
        create = self.client.post(
            "/api/programs/",
            {
                "certificate_type": "baccalaureate",
                "grade": "علمي",
                "section": "الشعبة الأولى",
                "day": "الأحد",
                "time_slot": "08:00",
                "room": "القاعة 101",
                "subject_name": "الفيزياء",
                "teacher_name": str(teacher.id),
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        listing = self.client.get("/api/programs/")
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(Program.objects.filter(pk=create.data["id"]).exists())

    def test_admin_program_editor_patch_delete_and_upsert(self):
        """شاشة وضع البرنامج: PATCH وDELETE وإعادة POST لنفس حصة الأحد تُثبَّت."""
        teacher = self._make_teacher("9011")
        payload = {
            "certificate_type": "baccalaureate",
            "grade": "علمي",
            "section": "الشعبة الأولى",
            "day": "الأحد",
            "time_slot": "08:00",
            "room": "",
            "subject_name": "فيزياء",
            "teacher_name": str(teacher.id),
        }
        first = self.client.post("/api/programs/", payload, format="json")
        self.assertIn(first.status_code, (200, 201), first.data)
        program_id = first.data["id"]

        again = self.client.post(
            "/api/programs/",
            {**payload, "time_slot": "8:00", "subject_name": "كيمياء", "room": ""},
            format="json",
        )
        self.assertIn(again.status_code, (200, 201), again.data)
        self.assertEqual(str(again.data["id"]), str(program_id))
        self.assertEqual(Program.objects.filter(day="الأحد", section="الشعبة الأولى").count(), 1)

        patch = self.client.patch(
            f"/api/programs/{program_id}/",
            {**payload, "subject_name": "رياضيات", "teacher_name": None, "room": ""},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.data)
        self.assertEqual(patch.data["subject_name"], "رياضيات")
        self.assertEqual(patch.data["time_slot"], "08:00")
        self.assertEqual(patch.data["day"], "الأحد")

        listing = self.client.get("/api/programs/")
        self.assertIsInstance(listing.data, list, listing.data)
        sunday = [
            row
            for row in listing.data
            if row["day"] == "الأحد" and row["time_slot"] == "08:00"
        ]
        self.assertEqual(len(sunday), 1)
        self.assertEqual(sunday[0]["subject_name"], "رياضيات")

        deleted = self.client.delete(f"/api/programs/{program_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Program.objects.filter(pk=program_id).exists())

    def test_sunday_8am_slot_clears_all_hour_spellings(self):
        """حصة الأحد الساعة 8 تُحذف حتى لو حُفظت 8 و 8:00 و 08:00 معاً."""
        teacher = self._make_teacher("9012")
        shared = {
            "certificate_type": "baccalaureate",
            "grade": "علمي",
            "section": "الشعبة الأولى",
            "day": "الأحد",
            "subject_name": "فيزياء",
            "teacher_name": teacher,
            "room": "",
        }
        first = Program.objects.create(**shared, time_slot="8")
        Program.objects.create(**shared, time_slot="8:00")
        Program.objects.create(**shared, time_slot="08:00")
        Program.objects.create(**{**shared, "day": "الاحد", "time_slot": "08:00:00"})

        listing = self.client.get("/api/programs/")
        sunday_eight = [
            row
            for row in listing.data
            if row["day"] == "الأحد" and row["time_slot"] == "08:00"
        ]
        self.assertEqual(len(sunday_eight), 1, listing.data)
        slot_id = sunday_eight[0]["id"]

        patch = self.client.patch(
            f"/api/programs/{slot_id}/",
            {"subject_name": "رياضيات", "room": ""},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.data)
        self.assertEqual(patch.data["subject_name"], "رياضيات")
        self.assertEqual(Program.objects.filter(subject_name="فيزياء").count(), 0)

        deleted = self.client.delete(f"/api/programs/{slot_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(
            Program.objects.filter(section="الشعبة الأولى", subject_name="رياضيات").exists()
        )

    def test_student_schedule_lists_programs_by_student_id(self):
        """شاشة برنامج الطالب: GET /api/programs/?student_id= حصص شعبته فقط."""
        teacher = self._make_teacher("8891")
        own = self.client.post(
            "/api/programs/",
            {
                "certificate_type": "baccalaureate",
                "grade": "علمي",
                "section": "الشعبة الأولى",
                "day": "الأحد",
                "time_slot": "8:00",
                "room": "القاعة 101",
                "subject_name": "الفيزياء",
                "teacher_name": str(teacher.id),
            },
            format="json",
        )
        self.assertIn(own.status_code, (200, 201), own.data)
        other = self.client.post(
            "/api/programs/",
            {
                "certificate_type": "baccalaureate",
                "grade": "علمي",
                "section": "الشعبة الثانية",
                "day": "الأحد",
                "time_slot": "9:00",
                "room": "القاعة 202",
                "subject_name": "الكيمياء",
                "teacher_name": str(teacher.id),
            },
            format="json",
        )
        self.assertIn(other.status_code, (200, 201), other.data)
        literary = self.client.post(
            "/api/programs/",
            {
                "certificate_type": "baccalaureate",
                "grade": "أدبي",
                "section": "الشعبة الأولى",
                "day": "الاثنين",
                "time_slot": "10:00",
                "room": "القاعة 303",
                "subject_name": "فلسفة",
            },
            format="json",
        )
        self.assertIn(literary.status_code, (200, 201), literary.data)

        student = self._make_student("8892")
        student.class1 = "بكالوريا علمي"
        student.class3 = "الشعبة الأولى"
        student.save(update_fields=["class1", "class3"])
        login = APIClient().post(
            "/api/student-login/",
            {"special_number": student.special_number},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(login.data["class1"], "بكالوريا علمي")
        self.assertEqual(login.data["class3"], "الشعبة الأولى")
        self.assertEqual(login.data["studentGrade"], "بكالوريا علمي")
        self.assertEqual(login.data["studentSection"], "الشعبة الأولى")
        token = login.data["access"]
        student_id = login.data["student_id"]
        client = APIClient()
        listing = client.get(
            f"/api/programs/?student_id={student_id}",
            HTTP_AUTHORIZATION=f"StudentToken {token}",
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        rows = listing.data["results"] if isinstance(listing.data, dict) else listing.data
        self.assertIsInstance(rows, list, listing.data)
        subjects = {row.get("subject_name") for row in rows}
        self.assertEqual(subjects, {"الفيزياء"})
        lesson = rows[0]
        self.assertEqual(lesson["day"], "الأحد")
        self.assertTrue(str(lesson["time_slot"]).startswith("08:00"))
        self.assertEqual(lesson["class1"], "بكالوريا علمي")
        self.assertEqual(lesson["class3"], "الشعبة الأولى")
        self.assertEqual(lesson["section"], "الشعبة الأولى")
        self.assertEqual(lesson["teacher_name"], "أستاذ تجربة")

        create_attempt = client.post(
            "/api/programs/",
            {
                "certificate_type": "x",
                "grade": "y",
                "section": "z",
                "day": "الاثنين",
                "time_slot": "09:00",
                "room": "1",
                "subject_name": "كيمياء",
            },
            format="json",
            HTTP_AUTHORIZATION=f"StudentToken {token}",
        )
        self.assertEqual(create_attempt.status_code, 403)

    def test_refresh(self):
        """طلب refresh: POST /api/token/refresh/"""
        client = APIClient()
        response = client.post("/api/token/refresh/", {"refresh": self.refresh}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_unauthenticated_managers_forbidden(self):
        client = APIClient()
        response = client.get("/api/managers/")
        self.assertEqual(response.status_code, 401)

    def test_student_cannot_read_other_student(self):
        first = self._make_student("111")
        second = self._make_student("222")
        token = self._token_for_special(first.special_number)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        own = client.get(f"/api/students/{first.id}/")
        self.assertEqual(own.status_code, 200)
        other = client.get(f"/api/students/{second.id}/")
        self.assertIn(other.status_code, (403, 404))

    def test_student_special_number_opens_profile_via_student_detail(self):
        """شاشة الطالب: الرقم المميز → studentId/studentToken ثم GET /api/student-detail/."""
        student = self._make_student("4401")
        student.is_payer = True
        student.save(update_fields=["is_payer"])

        login = APIClient().post(
            "/api/token/",
            {"special_number": "4401"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(login.data["role"], "student")
        self.assertEqual(str(login.data["studentId"]), str(student.id))
        self.assertEqual(login.data["studentToken"], login.data["access"])
        self.assertEqual(login.data["first_name"], "طالب")
        self.assertEqual(login.data["last_name"], "تجربة")
        self.assertTrue(login.data["is_payer"])

        student_id = login.data["studentId"]
        student_token = login.data["studentToken"]
        client = APIClient()
        profile = client.get(
            f"/api/student-detail/{student_id}/",
            HTTP_AUTHORIZATION=f"StudentToken {student_token}",
        )
        self.assertEqual(profile.status_code, 200, profile.data)
        self.assertEqual(profile.data["first_name"], "طالب")
        self.assertEqual(profile.data["last_name"], "تجربة")
        self.assertTrue(profile.data["is_payer"])

        by_number = client.get(
            "/api/student-detail/4401/",
            HTTP_AUTHORIZATION=f"StudentToken {student_token}",
        )
        self.assertEqual(by_number.status_code, 200, by_number.data)
        self.assertEqual(str(by_number.data["id"]), str(student.id))

        by_user = client.get(
            f"/api/student-detail/{student.user_id}/",
            HTTP_AUTHORIZATION=f"StudentToken {student_token}",
        )
        self.assertEqual(by_user.status_code, 200, by_user.data)

        portal_login = APIClient().post(
            "/api/student-detail/",
            {"special_number": "4401"},
            format="json",
        )
        self.assertEqual(portal_login.status_code, 200, portal_login.data)
        self.assertEqual(str(portal_login.data["studentId"]), str(student.id))
        self.assertIn("studentToken", portal_login.data)

        other = self._make_student("4402")
        other_profile = client.get(
            f"/api/student-detail/{other.id}/",
            HTTP_AUTHORIZATION=f"StudentToken {student_token}",
        )
        self.assertEqual(other_profile.status_code, 404)

        missing_auth = APIClient().get(f"/api/student-detail/{student_id}/")
        self.assertEqual(missing_auth.status_code, 401)

    def test_student_login_endpoint_matches_frontend(self):
        """POST /api/student-login/ كما في شاشة الرقم المميز: status و student_id و access."""
        student = self._make_student("5501")
        login = APIClient().post(
            "/api/student-login/",
            {"special_number": "5501"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(login.data["status"], "success")
        self.assertEqual(str(login.data["student_id"]), str(student.id))
        self.assertTrue(login.data.get("access"))
        self.assertEqual(login.data["access"], login.data["studentToken"])
        self.assertIn("class1", login.data)
        self.assertIn("class3", login.data)
        self.assertIn("studentGrade", login.data)
        self.assertIn("studentSection", login.data)

        missing = APIClient().post(
            "/api/student-login/",
            {"special_number": "9999999"},
            format="json",
        )
        self.assertEqual(missing.status_code, 404)
        self.assertTrue(missing.data.get("error"))

        teacher = self._make_teacher("5502")
        as_teacher = APIClient().post(
            "/api/student-login/",
            {"special_number": teacher.special_number},
            format="json",
        )
        self.assertEqual(as_teacher.status_code, 404)
        self.assertTrue(as_teacher.data.get("error"))

    def test_teacher_token_cannot_create_student(self):
        teacher = self._make_teacher("777")
        token = self._token_for_special(teacher.special_number)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post(
            "/api/students/",
            {
                "first_name": "تجربة",
                "last_name": "ممنوع",
                "special_number": "333",
                "student_class": "1",
                "parent_number": "1234567890",
                "student_number": "1234567890",
                "address": "عنوان",
                "personal_notes": "لا",
                "is_payer": False,
                "class1": "أ",
                "class2": "ب",
                "class3": "ج",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_subscription_blocks_api(self):
        Subscription.objects.all().update(expiry_date=date.today() - timedelta(days=1))
        response = self.client.get("/api/managers/")
        self.assertEqual(response.status_code, 403)
        self.assertIn("اشتراك", response.json()["detail"])

    def test_search_students_by_special_number(self):
        self._make_student("1010")
        response = self.client.get("/api/students/?special_number=1010")
        self.assertEqual(response.status_code, 200)
        payload = response.data
        if isinstance(payload, dict) and "results" in payload:
            self.assertEqual(payload["count"], 1)
        else:
            self.assertEqual(len(payload), 1)

    def test_search_student_by_all_frontend_patterns(self):
        """البحث بالرقم المميز يعمل بكل أنماط الفرونت الشائعة."""
        self._make_student("22")
        self._make_student("220")

        cases = [
            "/api/students/?special_number=22",
            "/api/students/?specialNumber=22",
            "/api/students/?number=22",
            "/api/students/?search=22",
            "/api/students/?q=22",
            "/api/students/search/?special_number=22",
            "/api/students/search/?q=22",
        ]
        for url in cases:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            payload = response.data
            if isinstance(payload, dict) and "results" in payload:
                rows = payload["results"]
                self.assertGreaterEqual(payload["count"], 1, url)
            else:
                rows = payload
                self.assertGreaterEqual(len(rows), 1, url)
            numbers = {str(row["special_number"]) for row in rows}
            self.assertIn("22", numbers, url)

        detail = self.client.get("/api/students/22/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(str(detail.data["special_number"]), "22")
        self.assertEqual(detail.data["first_name"], "طالب")

    def test_field_max_length_arabic_error(self):
        response = self.client.post(
            "/api/teachers/",
            {
                "first_name": "اسمأطولمنخمسةعشرحرفاًجدا",
                "last_name": "ب",
                "special_number": "12345",
                "gender": True,
                "teacher_number": "1234567890",
                "expertise": "رياضيات",
                "cv": "سيرة",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_student_reclaims_inactive_numbers_and_arabic_digits(self):
        """
        أرقام مثل 1 و333 المحجوزة لطلاب محذوفين ناعماً يجب أن تُحرَّر.
        الأرقام العربية ٣٣٣ تُقبل وتُحفظ لاتينياً.
        """
        # محاكاة بقايا حسابات معطّلة كما في Neon
        for num in ("1", "333"):
            stale_user = User.objects.create_user(
                username=f"s{num}",
                special_number=num,
                role=User.ROLE_STUDENT,
                user_type="3",
                first_name="قديم",
                last_name="محذوف",
            )
            stale_user.is_active = False
            stale_user.save(update_fields=["is_active"])

        payload = {
            "first_name": "جديد",
            "last_name": "طالب",
            "special_number": "1",
            "student_class": "1",
            "parent_number": "0933111222",
            "student_number": "5544",
            "address": "اللاذقية - المشروع الأول",
            "personal_notes": "ملاحظة",
            "is_payer": False,
            "class1": "رياضيات",
            "class2": "فيزياء",
            "class3": "كيمياء",
        }
        create_one = self.client.post("/api/students/", payload, format="json")
        self.assertEqual(create_one.status_code, 201, create_one.data)
        self.assertEqual(str(create_one.data["special_number"]), "1")

        payload["special_number"] = "٣٣٣"
        create_arabic = self.client.post("/api/students/", payload, format="json")
        self.assertEqual(create_arabic.status_code, 201, create_arabic.data)
        self.assertEqual(str(create_arabic.data["special_number"]), "333")

        # رقم نشط مستخدم → 400 واضح لا 500
        self._make_student("2")
        payload["special_number"] = "2"
        conflict = self.client.post("/api/students/", payload, format="json")
        self.assertEqual(conflict.status_code, 400, conflict.data)
        self.assertIn("special_number", conflict.data)

    def _make_student(self, special):
        user = User.objects.create_user(
            username=f"s{special}"[:25],
            special_number=str(special),
            role=User.ROLE_STUDENT,
            user_type="3",
            first_name="طالب",
            last_name="تجربة",
        )
        return Student.objects.create(
            user=user,
            first_name="طالب",
            last_name="تجربة",
            special_number=str(special),
            student_class="10",
            parent_number="1234567890",
            student_number="0987654321",
            address="عنوان",
            personal_notes="ملاحظة",
            is_payer=False,
        )

    def _make_teacher(self, special):
        user = User.objects.create_user(
            username=f"t{special}"[:25],
            special_number=str(special),
            role=User.ROLE_TEACHER,
            user_type="2",
            first_name="أستاذ",
            last_name="تجربة",
        )
        return Teacher.objects.create(
            user=user,
            first_name="أستاذ",
            last_name="تجربة",
            special_number=str(special),
            gender="true",
            teacher_number="1234567890",
            expertise="رياضيات",
            cv="سيرة",
        )

    def _token_for_special(self, special):
        client = APIClient()
        response = client.post("/api/token/", {"special_number": special}, format="json")
        self.assertEqual(response.status_code, 200)
        return response.data["access"]
