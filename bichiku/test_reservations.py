from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Conversation,
    Notification,
    Offer,
    Organization,
    PickupRecord,
    Profile,
    Reservation,
)
from .test_offers import login_as, make_lot, make_user
from .test_group import make_offer, pickup_text, reserve_data

User = get_user_model()
GROUP = Organization.AccountType.GROUP
R = Reservation.Status


def make_reservation(offer, group_org, quantity=3, status=R.PENDING):
    reservation = Reservation.objects.create(
        offer=offer,
        organization=group_org,
        reserved_quantity=quantity,
        requested_pickup_at=timezone.now() + timedelta(days=2),
        status=status,
    )
    Conversation.objects.create(reservation=reservation)
    return reservation


def url(name, pk):
    return reverse(f"bichiku:{name}", args=[pk])


class Base(TestCase):
    """企業 c / 団体 g と、募集(10個確保。ロットの在庫は 100 のまま)を用意する"""

    def setUp(self):
        self.company_user, self.company = make_user("c")
        self.group_user, self.group = make_user("g", GROUP)
        self.lot = make_lot(self.company, qty=100)
        self.offer = make_offer(self.company, self.lot, quantity=10)

    def lot_qty(self):
        self.lot.refresh_from_db()
        return self.lot.quantity

    def offer_state(self):
        self.offer.refresh_from_db()
        return self.offer.quantity, self.offer.status


class ListTests(Base):
    def test_anonymous_and_no_profile(self):
        self.assertEqual(self.client.get(reverse("bichiku:reservation_list")).status_code, 302)
        make_user("x", with_profile=False)
        login_as(self.client, "x")
        self.assertEqual(self.client.get(reverse("bichiku:reservation_list")).status_code, 403)

    def test_each_side_sees_only_own(self):
        mine = make_reservation(self.offer, self.group)
        _, other_group = make_user("g2", GROUP)
        _, other_company = make_user("c2")
        theirs = make_reservation(make_offer(other_company, make_lot(other_company, name="b")), other_group)

        login_as(self.client, "c")
        r = self.client.get(reverse("bichiku:reservation_list"))
        self.assertEqual(list(r.context["reservations"]), [mine])
        self.assertTrue(r.context["is_company"])

        login_as(self.client, "g")
        r = self.client.get(reverse("bichiku:reservation_list"))
        self.assertEqual(list(r.context["reservations"]), [mine])
        self.assertNotIn(theirs, r.context["reservations"])

        login_as(self.client, "g2")
        r = self.client.get(reverse("bichiku:reservation_list"))
        self.assertEqual(list(r.context["reservations"]), [theirs])

    def test_status_filter_and_search(self):
        make_reservation(self.offer, self.group, 1, R.PENDING)
        make_reservation(self.offer, self.group, 1, R.APPROVED)
        make_reservation(self.offer, self.group, 1, R.APPROVED)
        make_reservation(self.offer, self.group, 1, R.COMPLETED)
        make_reservation(self.offer, self.group, 1, R.CANCELLED)
        login_as(self.client, "c")
        url_ = reverse("bichiku:reservation_list")
        count = lambda **p: len(self.client.get(url_, p).context["reservations"])
        self.assertEqual(count(), 5)
        self.assertEqual(count(status="reserved"), 1)
        self.assertEqual(count(status="scheduled"), 2)
        self.assertEqual(count(status="completed"), 1)
        self.assertEqual(count(status="cancelled"), 1)
        self.assertEqual(count(status="でたらめ"), 5)
        self.assertEqual(count(q="水"), 5)       # 備蓄品名
        self.assertEqual(count(q="g"), 5)        # 予約した団体名
        self.assertEqual(count(q="存在しない"), 0)
        login_as(self.client, "g")
        self.assertEqual(count(q="c"), 5)        # 団体からは、提供企業名で探せる

    def test_page_uses_team_design_with_real_data(self):
        res = make_reservation(self.offer, self.group, 3)
        res.message = "ワゴン車で伺います"
        res.save()
        login_as(self.client, "c")
        r = self.client.get(reverse("bichiku:reservation_list"))
        self.assertTemplateUsed(r, "bichiku/reservations.html")
        self.assertContains(r, 'class="reservation-detail-trigger"')
        self.assertContains(r, 'class="reservation-detail-popover"')
        self.assertContains(r, f"res-{res.pk}")
        self.assertContains(r, "ワゴン車で伺います")
        self.assertContains(r, "g")  # 予約した団体名
        self.assertNotContains(r, "さくら子ども食堂")  # 見本のデータは、もう出ない

    def test_buttons_depend_on_role_and_status(self):
        res = make_reservation(self.offer, self.group)
        login_as(self.client, "c")
        r = self.client.get(reverse("bichiku:reservation_list"))
        self.assertContains(r, url("reservation_approve", res.pk))
        login_as(self.client, "g")
        r = self.client.get(reverse("bichiku:reservation_list"))
        self.assertNotContains(r, url("reservation_approve", res.pk))
        self.assertContains(r, url("reservation_cancel", res.pk))


class ApproveTests(Base):
    def test_approve_and_notify(self):
        res = make_reservation(self.offer, self.group)
        login_as(self.client, "c")
        self.client.post(url("reservation_approve", res.pk))
        res.refresh_from_db()
        self.assertEqual(res.status, R.APPROVED)
        self.assertEqual(self.offer_state(), (10, "recruiting"))  # 数量は変わらない
        n = Notification.objects.get()
        self.assertEqual(n.user, self.group_user)
        self.assertEqual(n.related_reservation, res)

    def test_only_pending_can_be_approved(self):
        res = make_reservation(self.offer, self.group, status=R.CANCELLED)
        login_as(self.client, "c")
        self.client.post(url("reservation_approve", res.pk))
        res.refresh_from_db()
        self.assertEqual(res.status, R.CANCELLED)

    def test_group_and_other_company_cannot_approve(self):
        res = make_reservation(self.offer, self.group)
        login_as(self.client, "g")
        self.assertEqual(self.client.post(url("reservation_approve", res.pk)).status_code, 403)
        make_user("c2")
        login_as(self.client, "c2")
        self.assertEqual(self.client.post(url("reservation_approve", res.pk)).status_code, 404)
        res.refresh_from_db()
        self.assertEqual(res.status, R.PENDING)

    def test_post_only(self):
        res = make_reservation(self.offer, self.group)
        login_as(self.client, "c")
        for name in ("reservation_approve", "reservation_cancel", "reservation_complete"):
            self.assertEqual(self.client.get(url(name, res.pk)).status_code, 405)


class CancelTests(Base):
    def test_company_reject_frees_the_offer_quantity(self):
        res = make_reservation(self.offer, self.group, 4)
        from .reservation_services import remaining_quantity
        self.assertEqual(remaining_quantity(self.offer), 6)
        login_as(self.client, "c")
        self.client.post(url("reservation_cancel", res.pk))
        res.refresh_from_db()
        self.assertEqual(res.status, R.CANCELLED)
        self.assertEqual(remaining_quantity(self.offer), 10)
        self.assertEqual(self.lot_qty(), 100)  # 募集中なら、在庫は変えない
        self.assertEqual(Notification.objects.get().user, self.group_user)
        self.assertIn("却下", Notification.objects.get().title)

    def test_group_cancel_pending_and_approved_notifies_company(self):
        for status in (R.PENDING, R.APPROVED):
            res = make_reservation(self.offer, self.group, 2, status)
            login_as(self.client, "g")
            self.client.post(url("reservation_cancel", res.pk))
            res.refresh_from_db()
            self.assertEqual(res.status, R.CANCELLED)
        self.assertEqual(set(Notification.objects.values_list("user_id", flat=True)), {self.company_user.pk})

    def test_cannot_cancel_completed_or_cancelled(self):
        for status in (R.COMPLETED, R.CANCELLED):
            res = make_reservation(self.offer, self.group, 1, status)
            login_as(self.client, "g")
            self.client.post(url("reservation_cancel", res.pk))
            res.refresh_from_db()
            self.assertEqual(res.status, status)

    def test_other_group_gets_404(self):
        res = make_reservation(self.offer, self.group)
        make_user("g2", GROUP)
        login_as(self.client, "g2")
        self.assertEqual(self.client.post(url("reservation_cancel", res.pk)).status_code, 404)

    def test_cancel_on_closed_offer_releases_hold(self):
        from .offer_services import close_offer
        res = make_reservation(self.offer, self.group, 4)
        close_offer(self.offer)  # 未予約の6個の確保が外れ、募集は4個だけ残る
        self.assertEqual(self.lot_qty(), 100)
        self.assertEqual(self.offer_state(), (4, "closed"))
        login_as(self.client, "g")
        self.client.post(url("reservation_cancel", res.pk))
        self.assertEqual(self.lot_qty(), 100)
        self.assertEqual(self.offer_state(), (0, "closed"))


class CompleteTests(Base):
    def test_complete_full(self):
        res = make_reservation(self.offer, self.group, 4, R.APPROVED)
        login_as(self.client, "c")
        self.client.post(url("reservation_complete", res.pk), {"received_quantity": 4})
        res.refresh_from_db()
        self.assertEqual(res.status, R.COMPLETED)
        record = PickupRecord.objects.get()
        self.assertEqual((record.received_quantity, record.pickup_status, record.user), (4, "completed", self.company_user))
        self.assertEqual(self.offer_state(), (6, "recruiting"))
        self.assertEqual(self.lot_qty(), 96)  # 受け取り完了で、初めて在庫が減る
        self.assertEqual(Notification.objects.get().user, self.group_user)

    def test_complete_partial_deducts_only_received(self):
        res = make_reservation(self.offer, self.group, 4, R.APPROVED)
        login_as(self.client, "c")
        self.client.post(url("reservation_complete", res.pk), {"received_quantity": 3})
        self.assertEqual(PickupRecord.objects.get().pickup_status, "partial")
        self.assertEqual(self.offer_state(), (6, "recruiting"))
        self.assertEqual(self.lot_qty(), 97)  # 受け取った3個だけ減る

    def test_invalid_quantities_rejected(self):
        res = make_reservation(self.offer, self.group, 4, R.APPROVED)
        login_as(self.client, "c")
        for bad in ("0", "5", "-1", "", "abc"):
            self.client.post(url("reservation_complete", res.pk), {"received_quantity": bad})
        res.refresh_from_db()
        self.assertEqual(res.status, R.APPROVED)
        self.assertEqual(PickupRecord.objects.count(), 0)
        self.assertEqual(self.offer_state(), (10, "recruiting"))

    def test_only_approved_can_complete_and_only_once(self):
        pending = make_reservation(self.offer, self.group, 1, R.PENDING)
        login_as(self.client, "c")
        self.client.post(url("reservation_complete", pending.pk), {"received_quantity": 1})
        self.assertEqual(PickupRecord.objects.count(), 0)
        res = make_reservation(self.offer, self.group, 2, R.APPROVED)
        self.client.post(url("reservation_complete", res.pk), {"received_quantity": 2})
        self.client.post(url("reservation_complete", res.pk), {"received_quantity": 2})
        self.assertEqual(PickupRecord.objects.count(), 1)
        self.assertEqual(self.offer_state(), (8, "recruiting"))

    def test_group_cannot_complete(self):
        res = make_reservation(self.offer, self.group, 2, R.APPROVED)
        login_as(self.client, "g")
        self.assertEqual(self.client.post(url("reservation_complete", res.pk), {"received_quantity": 2}).status_code, 403)

    def test_offer_closes_itself_when_everything_is_handed_over(self):
        offer = make_offer(self.company, make_lot(self.company, name="x"), quantity=4)
        res = make_reservation(offer, self.group, 4, R.APPROVED)
        login_as(self.client, "c")
        self.client.post(url("reservation_complete", res.pk), {"received_quantity": 4})
        offer.refresh_from_db()
        self.assertEqual((offer.quantity, offer.status), (0, "closed"))
        # 受け取りが終わった募集は、募集を探す画面から消える
        login_as(self.client, "g")
        r = self.client.get(reverse("bichiku:offer_browse"))
        self.assertNotIn(offer, r.context["offers"])


class FullFlowTests(TestCase):
    """募集の公開 → 予約 → 承認 → 受け取り完了 まで、数量が合うことを通しで確認する"""

    def test_end_to_end(self):
        company_user, company = make_user("c")
        make_user("g", GROUP)
        lot = make_lot(company, qty=100)

        login_as(self.client, "c")
        self.client.post(reverse("bichiku:offer_create"), {
            "lot": lot.pk, "title": "水", "quantity": 20, "pickup_location": "倉庫A",
            "prefecture": "東京都", "receiving_conditions": "", "description": "",
            "deadline": (timezone.localdate() + timedelta(days=5)).isoformat(), "action": "publish",
        })
        offer = Offer.objects.get()
        lot.refresh_from_db()
        self.assertEqual(lot.quantity, 100)  # 公開しても在庫は減らない

        login_as(self.client, "g")
        self.client.post(reverse("bichiku:offer_detail", args=[offer.pk]), reserve_data(5))
        reservation = Reservation.objects.get()

        login_as(self.client, "c")
        self.client.post(url("reservation_approve", reservation.pk))
        self.client.post(url("reservation_complete", reservation.pk), {"received_quantity": 5})

        offer.refresh_from_db()
        lot.refresh_from_db()
        self.assertEqual((lot.quantity, offer.quantity, offer.status), (95, 15, "recruiting"))
        # 募集を終了しても、在庫は変わらない(95のまま。確保が外れるだけ)
        self.client.post(reverse("bichiku:offer_close", args=[offer.pk]))
        lot.refresh_from_db()
        self.assertEqual(lot.quantity, 95)


class StockOnlyDropsOnCompletionTests(Base):
    """予約・承認・取り消しでは、在庫は減らない。企業の受け取り完了でだけ減る"""

    def test_reserve_approve_cancel_keep_stock(self):
        res = make_reservation(self.offer, self.group, 4)
        self.assertEqual(self.lot_qty(), 100)
        login_as(self.client, "c")
        self.client.post(url("reservation_approve", res.pk))
        self.assertEqual(self.lot_qty(), 100)
        self.client.post(url("reservation_cancel", res.pk))
        self.assertEqual(self.lot_qty(), 100)

    def test_group_cannot_complete_so_stock_stays(self):
        res = make_reservation(self.offer, self.group, 4, R.APPROVED)
        login_as(self.client, "g")
        self.client.post(url("reservation_complete", res.pk), {"received_quantity": 4})
        self.assertEqual(self.lot_qty(), 100)