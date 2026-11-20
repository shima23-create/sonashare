from django.test import TestCase
from django.urls import reverse

from .models import Notification, Offer, Reservation
from .test_group import make_offer, reserve_data
from .test_offers import login_as, make_lot, make_user, offer_data
from .test_reservations import GROUP, R, make_reservation, url


class NotificationFlowTests(TestCase):
    def setUp(self):
        self.company_user, self.company = make_user("c")
        self.group_user, self.group = make_user("g", GROUP)
        self.lot = make_lot(self.company, qty=100)
        self.offer = make_offer(self.company, self.lot, quantity=10)

    def titles(self, user):
        return list(Notification.objects.filter(user=user).order_by("id").values_list("title", flat=True))

    def test_new_reservation_notifies_company(self):
        login_as(self.client, "g")
        self.client.post(reverse("bichiku:offer_detail", args=[self.offer.pk]), reserve_data(2))
        self.assertEqual(self.titles(self.company_user), ["新しい予約が入りました"])
        self.assertEqual(self.titles(self.group_user), [])

    def test_approve_reject_complete_notify_group(self):
        a = make_reservation(self.offer, self.group, 2)
        b = make_reservation(self.offer, self.group, 2)
        login_as(self.client, "c")
        self.client.post(url("reservation_approve", a.pk))
        self.client.post(url("reservation_cancel", b.pk))  # 却下
        self.client.post(url("reservation_complete", a.pk), {"received_quantity": 2})
        self.assertEqual(
            self.titles(self.group_user),
            ["予約が承認されました", "予約が却下されました", "受け取りが完了しました"],
        )

    def test_group_cancel_notifies_company(self):
        res = make_reservation(self.offer, self.group, 2)
        login_as(self.client, "g")
        self.client.post(url("reservation_cancel", res.pk))
        self.assertEqual(self.titles(self.company_user), ["予約がキャンセルされました"])


class NotificationScreenTests(TestCase):
    def setUp(self):
        self.user, self.org = make_user("c")
        self.other, _ = make_user("o")
        self.mine = Notification.objects.create(user=self.user, title="自分宛", content="x", type="system")
        self.theirs = Notification.objects.create(user=self.other, title="他人宛", content="y", type="system")
        login_as(self.client, "c")

    def test_bell_shows_unread_count_on_every_page(self):
        r = self.client.get(reverse("bichiku:notification_list"))
        self.assertContains(r, 'class="notice-badge">1<')
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertContains(r, 'class="notice-badge">1<')

    def test_list_shows_only_own(self):
        r = self.client.get(reverse("bichiku:notification_list"))
        self.assertContains(r, "自分宛")
        self.assertNotContains(r, "他人宛")

    def test_open_marks_read_and_cannot_open_others(self):
        self.client.post(reverse("bichiku:notification_open", args=[self.mine.pk]))
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_read)
        r = self.client.post(reverse("bichiku:notification_open", args=[self.theirs.pk]))
        self.assertEqual(r.status_code, 404)
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_read_all_only_touches_own(self):
        self.client.post(reverse("bichiku:notification_read_all"))
        self.mine.refresh_from_db(); self.theirs.refresh_from_db()
        self.assertTrue(self.mine.is_read)
        self.assertFalse(self.theirs.is_read)

    def test_anonymous_is_redirected_and_get_is_rejected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("bichiku:notification_list")).status_code, 302)
        login_as(self.client, "c")
        self.assertEqual(self.client.get(reverse("bichiku:notification_open", args=[self.mine.pk])).status_code, 405)


class ZeroQuantityTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")
        self.lot = make_lot(self.org, qty=100)
        login_as(self.client, "c")

    def test_zero_offer_rejected_for_draft_and_publish(self):
        for action in ("save", "publish"):
            r = self.client.post(reverse("bichiku:offer_create"), offer_data(self.lot, quantity=0, action=action))
            self.assertIn("quantity", r.context["form"].errors)
        self.assertEqual(Offer.objects.count(), 0)


class NotificationDropdownTests(TestCase):
    def setUp(self):
        self.user, self.org = make_user("c")
        self.other, _ = make_user("o")
        login_as(self.client, "c")

    def test_dropdown_shows_latest_five_own_with_all_link(self):
        for i in range(7):
            Notification.objects.create(user=self.user, title=f"通知{i}", content="x", type="system")
        Notification.objects.create(user=self.other, title="他人の通知", content="y", type="system")
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertContains(r, 'data-notice-menu')
        self.assertContains(r, "通知6")
        self.assertContains(r, "通知2")
        self.assertNotContains(r, "通知1<")      # 古い2件は、プルダウンに出ない
        self.assertNotContains(r, "他人の通知")
        self.assertContains(r, "すべて見る")
        self.assertContains(r, 'class="notice-badge">7<')

    def test_empty_dropdown_and_no_menu_when_logged_out(self):
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertContains(r, "通知はまだありません")
        self.client.logout()
        r = self.client.get(reverse("accounts:login"))
        self.assertNotContains(r, "data-notice-menu")


class MessageNotificationTests(TestCase):
    def setUp(self):
        from .models import Conversation, Message
        self.Message = Message
        self.company_user, self.company = make_user("c")
        self.group_user, self.group = make_user("g", GROUP)
        self.offer = make_offer(self.company, make_lot(self.company, qty=100), quantity=10)
        self.res = make_reservation(self.offer, self.group, 2)
        self.conversation = Conversation.objects.get(reservation=self.res)

    def test_message_notifies_only_the_other_side(self):
        from .message_notifications import notify_new_message
        m = self.Message.objects.create(conversation=self.conversation, sender=self.group_user, content="こんにちは")
        self.assertEqual(notify_new_message(m), 1)
        n = Notification.objects.get()
        self.assertEqual((n.user, n.type, n.related_reservation), (self.company_user, "message", self.res))
        self.assertIn("こんにちは", n.content)

        m2 = self.Message.objects.create(conversation=self.conversation, sender=self.company_user, content="了解です")
        notify_new_message(m2)
        self.assertEqual(Notification.objects.filter(user=self.group_user, type="message").count(), 1)

    def test_opening_a_message_notification_goes_to_the_conversation(self):
        n = Notification.objects.create(
            user=self.company_user, title="新しいメッセージ", content="x",
            type="message", related_reservation=self.res,
        )
        login_as(self.client, "c")
        r = self.client.post(reverse("bichiku:notification_open", args=[n.pk]))
        self.assertRedirects(
            r, reverse("bichiku:conversation_detail", args=[self.conversation.pk]),
            fetch_redirect_response=False,
        )