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
        self.assertEqual(response.data["user"]["role"], "manager")

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
        """طلب api for students: GET /api/students/"""
        response = self.client.get("/api/students/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

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
        self.assertIn("DELETE", allow_methods)

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
        self.assertEqual(response.data["count"], 1)

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
            self.assertGreaterEqual(response.data["count"], 1, url)
            numbers = {str(row["special_number"]) for row in response.data["results"]}
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
