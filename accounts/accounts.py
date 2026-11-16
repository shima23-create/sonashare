from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bichiku.models import Organization, Profile

User = get_user_model()


def signup_data(**kw):
    data = {"user_type": "company", "company_name": "A社", "email": "a@example.com", "password": "pw12345678"}
    data.update(kw)
    return data


class SignUpTests(TestCase):
    def test_company_signup_creates_user_org_profile(self):
        r = self.client.post(reverse("accounts:signup"), signup_data())
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(email="a@example.com")
        org = user.profile.organization
        self.assertEqual(org.name, "A社")
        self.assertEqual(org.account_type, Organization.AccountType.COMPANY)
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(Profile.objects.count(), 1)

    def test_group_signup(self):
        self.client.post(reverse("accounts:signup"), signup_data(user_type="user", email="g@example.com"))
        org = User.objects.get(email="g@example.com").profile.organization
        self.assertEqual(org.account_type, Organization.AccountType.GROUP)

    def test_duplicate_email_rejected_case_insensitive(self):
        self.client.post(reverse("accounts:signup"), signup_data())
        self.client.logout()
        r = self.client.post(reverse("accounts:signup"), signup_data(email="A@Example.com"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Organization.objects.count(), 1)

    def test_signup_without_name_uses_email_local_part(self):
        self.client.post(reverse("accounts:signup"), signup_data(company_name=""))
        self.assertEqual(Organization.objects.get().name, "a")

    def test_signup_logs_in_and_company_screens_open(self):
        self.client.post(reverse("accounts:signup"), signup_data())
        self.assertEqual(self.client.get(reverse("bichiku:offer_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("bichiku:item_list")).status_code, 200)

    def test_group_cannot_open_company_screens(self):
        self.client.post(reverse("accounts:signup"), signup_data(user_type="user", email="g@example.com"))
        self.assertEqual(self.client.get(reverse("bichiku:offer_list")).status_code, 403)


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user(email="a@example.com", user_name="A社", password="pw12345678")

    def test_login_ok_and_wrong_password(self):
        data = {"user_type": "company", "email": "a@example.com", "password": "pw12345678"}
        r = self.client.post(reverse("accounts:login"), data)
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        r = self.client.post(reverse("accounts:login"), {**data, "password": "bad"})
        self.assertEqual(r.status_code, 200)

    def test_next_is_followed_but_external_is_not(self):
        data = {"user_type": "company", "email": "a@example.com", "password": "pw12345678"}
        r = self.client.post(reverse("accounts:login") + "?next=/offers/", {**data, "next": "/offers/"})
        self.assertEqual(r["Location"], "/offers/")
        self.client.logout()
        r = self.client.post(reverse("accounts:login"), {**data, "next": "https://evil.example/"})
        self.assertEqual(r["Location"], reverse("bichiku:dashboard"))

    def test_logout_is_post_only(self):
        self.client.login(username="a@example.com", password="pw12345678")
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("accounts:logout")).status_code, 302)


class AdminTests(TestCase):
    def test_superuser_and_admin_pages(self):
        admin_user = User.objects.create_superuser(email="root@example.com", user_name="root", password="pw12345678")
        self.assertTrue(admin_user.is_staff and admin_user.is_superuser)
        self.client.force_login(admin_user)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/accounts/user/").status_code, 200)
        self.assertEqual(self.client.get("/admin/accounts/user/add/").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/accounts/user/{admin_user.pk}/change/").status_code, 200)
        self.assertEqual(self.client.get("/admin/bichiku/organization/").status_code, 200)

    def test_normal_user_cannot_enter_admin(self):
        user = User.objects.create_user(email="u@example.com", user_name="u", password="pw12345678")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/admin/").status_code, 302)