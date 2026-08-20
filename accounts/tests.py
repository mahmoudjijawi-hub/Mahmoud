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

    def test_token_rejects_bad_password(self):
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"username": "ammar", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

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
        student = Student.objects.get(pk=student_id)
        self.assertFalse(student.is_active)

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
        self.assertEqual(create.status_code, 201)
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
