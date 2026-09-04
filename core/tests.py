"""اختبارات قفل دخول لوحة Django Admin."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from core.admin_login_limit import LOCK_MESSAGE, LIMIT
from core.models import Subscription

User = get_user_model()


class AdminLoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        from datetime import date, timedelta

        Subscription.objects.create(expiry_date=date.today() + timedelta(days=365), is_active=True)
        self.login_url = "/" + settings.ADMIN_URL + "login/"
        self.staff = User.objects.create_superuser(
            username="staffadmin",
            password="StaffPass123!",
            special_number="5551111",
        )

    def _post_login(self, username, password, **extra):
        return self.client.post(
            self.login_url,
            {"username": username, "password": password},
            **extra,
        )

    def test_five_failed_admin_logins_return_429_with_arabic_message(self):
        for index in range(4):
            response = self._post_login("wrong-name", f"bad-{index}")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response["X-RateLimit-Limit"], "5")
            self.assertEqual(response["X-RateLimit-Remaining"], str(LIMIT - (index + 1)))
            self.assertEqual(response["X-RateLimit-Reset"], "0")

        blocked = self._post_login("wrong-name", "bad-last")
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, LOCK_MESSAGE, status_code=429)
        self.assertEqual(blocked["X-RateLimit-Limit"], "5")
        self.assertEqual(blocked["X-RateLimit-Remaining"], "0")
        self.assertGreaterEqual(int(blocked["X-RateLimit-Reset"]), 1)
        self.assertLessEqual(int(blocked["X-RateLimit-Reset"]), 120)
        self.assertEqual(blocked["Retry-After"], blocked["X-RateLimit-Reset"])

        still_blocked = self._post_login("staffadmin", "StaffPass123!")
        self.assertEqual(still_blocked.status_code, 429)
        self.assertContains(still_blocked, LOCK_MESSAGE, status_code=429)

    def test_lockout_resets_after_expiry_and_allows_success(self):
        for _ in range(5):
            self._post_login("wrong", "wrong")
        from core.admin_login_limit import cache_keys

        class _Req:
            META = {"REMOTE_ADDR": "127.0.0.1"}
            POST = {}

        cache.delete(cache_keys(_Req())["lock"])
        ok = self._post_login("staffadmin", "StaffPass123!")
        self.assertIn(ok.status_code, (302, 303))
        self.assertEqual(ok["X-RateLimit-Remaining"], "5")

    def test_successful_login_resets_failure_counter(self):
        for _ in range(3):
            response = self._post_login("wrong", "wrong")
            self.assertEqual(response.status_code, 200)
        ok = self._post_login("staffadmin", "StaffPass123!")
        self.assertIn(ok.status_code, (302, 303))
        self.client.logout()
        for _ in range(4):
            response = self._post_login("wrong", "wrong")
            self.assertEqual(response.status_code, 200)
        blocked = self._post_login("wrong", "wrong")
        self.assertEqual(blocked.status_code, 429)

    def test_json_accept_returns_429_json_body(self):
        for _ in range(5):
            self._post_login("wrong", "wrong")
        blocked = self.client.post(
            self.login_url,
            {"username": "wrong", "password": "wrong"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked["Content-Type"].split(";")[0], "application/json")
        payload = blocked.json()
        self.assertEqual(payload["detail"], LOCK_MESSAGE)
        self.assertEqual(payload["code"], "too_many_requests")
        self.assertEqual(payload["wait"], int(blocked["X-RateLimit-Reset"]))

    def test_api_token_login_is_not_affected(self):
        client = APIClient()
        for _ in range(6):
            response = client.post(
                "/api/token/",
                {"username": "nobody", "password": "nobody"},
                format="json",
            )
            self.assertNotEqual(response.status_code, 429)
