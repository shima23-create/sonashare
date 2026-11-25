from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Conversation,
    StockItem,
    Message,
    Notification,
    Offer,
    Organization,
    Reservation,
)
from .test_offers import USERS, login_as, make_lot, make_user

User = get_user_model()
GROUP = Organization.AccountType.GROUP


def make_offer(org, lot, quantity=10, status=Offer.Status.RECRUITING, deadline_days=5, title="水を提供します", prefecture="東京都"):
    """予約テスト用に、募集を直接作る(数量の引き算は、ここでは行わない)"""
    return Offer.objects.create(
        lot=lot,
        organization=org,
        title=title,
        quantity=quantity,
        pickup_location="倉庫A",
        prefecture=prefecture,
        status=status,
        deadline=timezone.localdate() + timedelta(days=deadline_days),
    )


def pickup_text(days=2):
    return (timezone.localtime() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


def reserve_data(quantity=3, **kw):
    data = {"quantity": quantity, "requested_pickup_at": pickup_text(), "message": ""}
    data.update(kw)
    return data


class AccessTests(TestCase):
    def test_anonymous_redirected(self):
        r = self.client.get(reverse("bichiku:offer_browse"))
        self.assertEqual(r.status_code, 302)

    def test_company_forbidden(self):
        make_user("c")
        login_as(self.client, "c")
        self.assertEqual(self.client.get(reverse("bichiku:offer_browse")).status_code, 403)

    def test_no_profile_forbidden(self):
        make_user("x", with_profile=False)
        login_as(self.client, "x")
        self.assertEqual(self.client.get(reverse("bichiku:offer_browse")).status_code, 403)

    def test_group_cannot_open_company_screens(self):
        make_user("g", GROUP)
        login_as(self.client, "g")
        self.assertEqual(self.client.get(reverse("bichiku:offer_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("bichiku:item_list")).status_code, 403)

    def test_menu_differs_by_account_type(self):
        make_user("g", GROUP)
        login_as(self.client, "g")
        r = self.client.get(reverse("bichiku:offer_browse"))
        self.assertContains(r, "募集を探す")
        self.assertNotContains(r, f'href="{reverse("bichiku:item_list")}"')
        self.assertContains(r, "団体メニュー")

        make_user("c")
        login_as(self.client, "c")
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertContains(r, f'href="{reverse("bichiku:item_list")}"')
        self.assertContains(r, "企業メニュー")


class BrowseTests(TestCase):
    def setUp(self):
        _, self.company = make_user("c")
        make_user("g", GROUP)
        login_as(self.client, "g")
        self.url = reverse("bichiku:offer_browse")

    def titles(self, **params):
        r = self.client.get(self.url, params)
        return [o.title for o in r.context["offers"]]

    def test_only_open_offers_are_listed(self):
        lot = make_lot(self.company, qty=100)
        make_offer(self.company, lot, title="募集中")
        make_offer(self.company, lot, status=Offer.Status.DRAFT, title="下書き")
        make_offer(self.company, lot, status=Offer.Status.CLOSED, title="終了")
        make_offer(self.company, lot, deadline_days=-1, title="締切後")
        make_offer(self.company, make_lot(self.company, days=-1, name="古い"), title="期限切れ")
        self.assertEqual(self.titles(), ["募集中"])

    def test_fully_reserved_offer_is_hidden(self):
        offer = make_offer(self.company, make_lot(self.company), quantity=5, title="満員")
        _, other = make_user("g2", GROUP)
        Reservation.objects.create(
            offer=offer, organization=other, reserved_quantity=5,
            requested_pickup_at=timezone.now(),
        )
        self.assertEqual(self.titles(), [])

    def test_cancelled_reservation_does_not_reduce_remaining(self):
        offer = make_offer(self.company, make_lot(self.company), quantity=5)
        _, other = make_user("g2", GROUP)
        Reservation.objects.create(
            offer=offer, organization=other, reserved_quantity=5,
            requested_pickup_at=timezone.now(), status=Reservation.Status.CANCELLED,
        )
        r = self.client.get(self.url)
        self.assertEqual([o.remaining for o in r.context["offers"]], [5])

    def test_search_category_and_sort(self):
        make_offer(self.company, make_lot(self.company, days=20, name="水"), title="飲料A", deadline_days=9)
        make_offer(self.company, make_lot(self.company, days=10, name="缶詰"), title="缶詰B", deadline_days=3)
        self.assertEqual(self.titles(), ["缶詰B", "飲料A"])  # 締切が近い順
        self.assertEqual(self.titles(sort="expiry"), ["缶詰B", "飲料A"])
        self.assertEqual(self.titles(q="飲料"), ["飲料A"])
        self.assertEqual(self.titles(q="缶詰"), ["缶詰B"])
        self.assertEqual(self.titles(category="drink"), ["缶詰B", "飲料A"])  # テスト用のロットは、どちらも飲料
        self.assertEqual(self.titles(category="staple"), [])

    def test_filter_by_prefecture(self):
        make_offer(self.company, make_lot(self.company, name="a"), title="東京の募集", prefecture="東京都")
        make_offer(self.company, make_lot(self.company, name="b"), title="大阪の募集", prefecture="大阪府")
        self.assertEqual(sorted(self.titles(prefecture="大阪府")), ["大阪の募集"])
        self.assertEqual(sorted(self.titles(prefecture="東京都")), ["東京の募集"])
        self.assertEqual(self.titles(prefecture="沖縄県"), [])
        self.assertEqual(len(self.titles()), 2)
        self.assertEqual(len(self.titles(prefecture="でたらめ")), 2)  # 不正な値は、無視する

    def test_filter_by_multiple_genres(self):
        C = StockItem.Category
        make_offer(self.company, make_lot(self.company, name="a", category=C.DRINK), title="飲料")
        make_offer(self.company, make_lot(self.company, name="b", category=C.OTHER), title="缶詰")
        make_offer(self.company, make_lot(self.company, name="c", category=C.STAPLE), title="主食")
        self.assertEqual(self.titles(category=["drink"]), ["飲料"])
        self.assertEqual(sorted(self.titles(category=["drink", "other"])), ["缶詰", "飲料"])
        self.assertEqual(len(self.titles(category=["でたらめ"])), 3)

    def test_filter_by_expiry_days(self):
        make_offer(self.company, make_lot(self.company, days=5, name="a"), title="5日後")
        make_offer(self.company, make_lot(self.company, days=20, name="b"), title="20日後")
        make_offer(self.company, make_lot(self.company, days=60, name="c"), title="60日後")
        self.assertEqual(self.titles(expiry="7"), ["5日後"])
        self.assertEqual(sorted(self.titles(expiry="30")), ["20日後", "5日後"])
        self.assertEqual(len(self.titles(expiry="999")), 3)

    def test_filters_combine_and_count_is_shown(self):
        C = StockItem.Category
        make_offer(self.company, make_lot(self.company, name="a", category=C.DRINK), title="東京の飲料", prefecture="東京都")
        make_offer(self.company, make_lot(self.company, name="b", category=C.STAPLE), title="東京の缶詰", prefecture="東京都")
        make_offer(self.company, make_lot(self.company, name="c", category=C.DRINK), title="大阪の飲料", prefecture="大阪府")
        r = self.client.get(self.url, {"prefecture": "東京都", "category": ["drink"]})
        self.assertEqual([o.title for o in r.context["offers"]], ["東京の飲料"])
        self.assertContains(r, "1件の募集")
        self.assertTrue(r.context["has_filter"])

    def test_sort_new(self):
        make_offer(self.company, make_lot(self.company, name="a"), title="古い")
        make_offer(self.company, make_lot(self.company, name="b"), title="新しい")
        self.assertEqual(self.titles(sort="new"), ["新しい", "古い"])

    def test_empty_message(self):
        self.assertContains(self.client.get(self.url), "条件に合う募集はありません")


class ReserveTests(TestCase):
    def setUp(self):
        self.company_user, self.company = make_user("c")
        self.second_staff = User.objects.create_user(username="c2", password="pw")
        from .models import Profile
        Profile.objects.create(user=self.second_staff, organization=self.company)
        _, self.group = make_user("g", GROUP)
        self.offer = make_offer(self.company, make_lot(self.company, qty=100), quantity=10)
        self.url = reverse("bichiku:offer_detail", args=[self.offer.pk])
        login_as(self.client, "g")

    def test_detail_shows_offer(self):
        r = self.client.get(self.url)
        self.assertContains(r, "水を提供します")
        self.assertContains(r, "残り 10本")

    def test_reserve_creates_reservation_conversation_message_and_notifications(self):
        r = self.client.post(self.url, reserve_data(3, message="午前中に伺います"))
        self.assertRedirects(r, reverse("bichiku:reservation_list"), fetch_redirect_response=False)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertEqual(reservation.reserved_quantity, 3)
        self.assertEqual(reservation.organization, self.group)
        conversation = Conversation.objects.get(reservation=reservation)
        self.assertEqual(Message.objects.get(conversation=conversation).content, "午前中に伺います")
        notified = set(Notification.objects.values_list("user_id", flat=True))
        self.assertEqual(notified, {self.company_user.pk, self.second_staff.pk})
        self.assertEqual(Notification.objects.first().related_reservation, reservation)

    def test_no_message_means_no_chat_message(self):
        self.client.post(self.url, reserve_data(3))
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_remaining_decreases_and_boundary(self):
        self.client.post(self.url, reserve_data(6))
        r = self.client.get(self.url)
        self.assertContains(r, "残り 4本")
        r = self.client.post(self.url, reserve_data(5))
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertContains(r, "残りは 4")
        self.client.post(self.url, reserve_data(4))
        self.assertEqual(Reservation.objects.count(), 2)
        # 満員になったら、詳細は開けなくなる
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_over_quantity_rejected(self):
        r = self.client.post(self.url, reserve_data(11))
        self.assertEqual(Reservation.objects.count(), 0)
        self.assertEqual(r.status_code, 200)

    def test_zero_quantity_rejected(self):
        self.client.post(self.url, reserve_data(0))
        self.assertEqual(Reservation.objects.count(), 0)

    def test_past_pickup_rejected(self):
        self.client.post(self.url, reserve_data(1, requested_pickup_at=pickup_text(-1)))
        self.assertEqual(Reservation.objects.count(), 0)

    def test_pickup_after_expiry_rejected(self):
        late = (timezone.localtime() + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(self.url, reserve_data(1, requested_pickup_at=late))
        self.assertEqual(Reservation.objects.count(), 0)

    def test_closed_or_draft_offer_is_not_found(self):
        for status in (Offer.Status.DRAFT, Offer.Status.CLOSED):
            offer = make_offer(self.company, make_lot(self.company, name=status), status=status)
            url = reverse("bichiku:offer_detail", args=[offer.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, reserve_data(1)).status_code, 404)

    def test_company_cannot_reserve(self):
        login_as(self.client, "c")
        self.assertEqual(self.client.post(self.url, reserve_data(1)).status_code, 403)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_reservation_survives_closing_the_offer(self):
        from .offer_services import close_offer
        offer = make_offer(self.company, make_lot(self.company, qty=50, name="X"), quantity=10)
        url = reverse("bichiku:offer_detail", args=[offer.pk])
        self.client.post(url, reserve_data(4))
        offer.lot.quantity = 40  # 公開時に引いた状態に合わせる
        offer.lot.save()
        returned = close_offer(offer)
        self.assertEqual(returned, 6)
        self.assertEqual(Reservation.objects.filter(offer=offer).count(), 1)
        self.assertEqual(self.client.get(url).status_code, 404)