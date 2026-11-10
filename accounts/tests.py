from django.test import TestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from bichiku.models import Organization


class AccountAuthenticationTests(TestCase):
    def test_signup_creates_user_and_logs_them_in(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "user_type": "company",
                "company_name": "サンプル団体",
                "email": "signup@example.com",
                "password": "test-password-123",
            },
        )

        self.assertRedirects(response, reverse("bichiku:dashboard"))
        user = get_user_model().objects.get(email="signup@example.com")
        self.assertEqual(user.username, "signup@example.com")
        self.assertEqual(user.first_name, "サンプル団体")
        self.assertTrue(user.check_password("test-password-123"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(user.profile.organization.name, "サンプル団体")
        self.assertEqual(
            user.profile.organization.account_type,
            Organization.AccountType.COMPANY,
        )

    def test_login_accepts_email_and_password(self):
        user = get_user_model().objects.create_user(
            username="login@example.com",
            email="login@example.com",
            password="test-password-123",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "user_type": "company",
                "email": "login@example.com",
                "password": "test-password-123",
            },
        )

        self.assertRedirects(response, reverse("bichiku:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_does_not_show_greeting_message(self):
        get_user_model().objects.create_user(
            username="login-message@example.com",
            email="login-message@example.com",
            password="test-password-123",
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "user_type": "company",
                "email": "login-message@example.com",
                "password": "test-password-123",
            },
            follow=True,
        )

        self.assertNotContains(response, "こんにちは")

    def test_signup_does_not_show_completion_message(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "user_type": "company",
                "company_name": "登録テスト団体",
                "email": "signup-message@example.com",
                "password": "test-password-123",
            },
            follow=True,
        )

        self.assertNotContains(response, "ユーザー登録が完了しました")

    def test_sidebar_auth_links_go_to_accounts_pages_when_logged_out(self):
        response = self.client.get(reverse("bichiku:dashboard"))

        self.assertContains(response, f'href="{reverse("accounts:login")}"')
        self.assertContains(response, f'href="{reverse("accounts:signup")}"')
        self.assertNotContains(response, 'action="/accounts/logout/"')

    def test_sidebar_shows_post_logout_button_when_logged_in(self):
        user = get_user_model().objects.create_user(
            username="logout@example.com",
            email="logout@example.com",
            password="test-password-123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("bichiku:dashboard"))

        self.assertContains(response, f'action="{reverse("accounts:logout")}"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, f'href="{reverse("accounts:signup")}"')

    def test_logout_clears_session_and_redirects_to_login(self):
        user = get_user_model().objects.create_user(
            username="logout@example.com",
            email="logout@example.com",
            password="test-password-123",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:logout"), follow=True)

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, "ログアウトしました")

    def test_logout_does_not_accept_get(self):
        user = get_user_model().objects.create_user(
            username="logout@example.com",
            email="logout@example.com",
            password="test-password-123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 405)
