from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def signup(client, user_type, email):
    client.post(
        reverse("accounts:signup"),
        {"user_type": user_type, "company_name": "テスト", "email": email, "password": "pw12345678"},
    )
    client.logout()


def do_login(client, user_type, email, **extra):
    return client.post(
        reverse("accounts:login"),
        {"user_type": user_type, "email": email, "password": "pw12345678", **extra},
    )


class LoginRedirectTests(TestCase):
    def setUp(self):
        signup(self.client, "company", "c@example.com")
        signup(self.client, "user", "g@example.com")

    def test_group_goes_to_browse(self):
        r = do_login(self.client, "user", "g@example.com")
        self.assertRedirects(r, reverse("bichiku:offer_browse"), fetch_redirect_response=False)

    def test_company_goes_to_dashboard(self):
        r = do_login(self.client, "company", "c@example.com")
        self.assertRedirects(r, reverse("bichiku:dashboard"), fetch_redirect_response=False)

    def test_next_still_wins(self):
        r = do_login(self.client, "user", "g@example.com", next="/browse/")
        self.assertEqual(r["Location"], "/browse/")

    def test_wrong_user_type_is_rejected(self):
        for user_type, email in (("company", "g@example.com"), ("user", "c@example.com")):
            r = do_login(self.client, user_type, email)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "種別")  # 画面ではなく、エラーの有無だけを見る
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_redirects_by_type(self):
        self.client.logout()
        r = self.client.post(reverse("accounts:signup"),
            {"user_type": "user", "company_name": "新団体", "email": "new-g@example.com", "password": "pw12345678"})
        self.assertRedirects(r, reverse("bichiku:offer_browse"), fetch_redirect_response=False)
        self.client.logout()
        r = self.client.post(reverse("accounts:signup"),
            {"user_type": "company", "company_name": "新企業", "email": "new-c@example.com", "password": "pw12345678"})
        self.assertRedirects(r, reverse("bichiku:dashboard"), fetch_redirect_response=False)

    def test_already_logged_in_group_is_sent_to_browse(self):
        do_login(self.client, "user", "g@example.com")
        r = self.client.get(reverse("accounts:login"))
        self.assertRedirects(r, reverse("bichiku:offer_browse"), fetch_redirect_response=False)