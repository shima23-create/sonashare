from django.test import TestCase
from django.urls import reverse

from .models import Offer, StockLot
from .test_group import make_offer
from .test_offers import login_as, make_lot, make_user
from .test_reservations import GROUP, R, make_reservation


class DashboardTests(TestCase):
    def setUp(self):
        _, self.company = make_user("c")
        self.group_user, self.group = make_user("g", GROUP)
        self.near = make_lot(self.company, days=5, qty=10, name="近い水")
        self.near2 = make_lot(self.company, days=20, qty=3, name="近い米")
        self.expired = make_lot(self.company, days=-3, qty=4, name="切れた缶")
        self.far = make_lot(self.company, days=200, qty=50, name="遠い缶詰")
        self.empty = make_lot(self.company, days=2, qty=0, name="空のロット")
        login_as(self.client, "c")

    def get(self):
        return self.client.get(reverse("bichiku:dashboard"))

    def stats(self):
        return self.get().context["stats"]

    def test_counts(self):
        s = self.stats()
        self.assertEqual(s["total"], 5)
        self.assertEqual(s["expiring_count"], 2)   # 近い水 + 近い米(数量0・期限切れは除く)
        self.assertEqual(s["expired_count"], 1)    # 切れた缶(数量0は除く)
        self.assertEqual((s["pending_count"], s["scheduled_count"], s["recruiting_count"]), (0, 0, 0))

    def test_reservation_and_offer_counts_only_own_and_right_status(self):
        offer = make_offer(self.company, self.far, quantity=20)
        make_reservation(offer, self.group, 1, R.PENDING)
        make_reservation(offer, self.group, 1, R.PENDING)
        make_reservation(offer, self.group, 1, R.APPROVED)
        make_reservation(offer, self.group, 1, R.CANCELLED)
        make_reservation(offer, self.group, 1, R.COMPLETED)
        _, other = make_user("c2")
        other_offer = make_offer(other, make_lot(other, name="他社"), quantity=5)
        make_reservation(other_offer, self.group, 1, R.PENDING)
        s = self.stats()
        self.assertEqual((s["pending_count"], s["scheduled_count"], s["recruiting_count"]), (2, 1, 1))

    def test_card_numbers_match_the_screens_they_open(self):
        offer = make_offer(self.company, self.far, quantity=20)
        make_reservation(offer, self.group, 1, R.PENDING)
        make_reservation(offer, self.group, 1, R.APPROVED)
        r = self.get()
        s = r.context["stats"]
        res_url = reverse("bichiku:reservation_list")
        self.assertEqual(len(self.client.get(res_url, {"status": "reserved"}).context["reservations"]), s["pending_count"])
        self.assertEqual(len(self.client.get(res_url, {"status": "scheduled"}).context["reservations"]), s["scheduled_count"])
        items = reverse("bichiku:item_list")
        self.assertEqual(len(self.client.get(items, {"expiry": "warning"}).context["inventory_lots"]), s["expiring_count"])
        self.assertEqual(len(self.client.get(items, {"expiry": "expired"}).context["inventory_lots"]), s["expired_count"])
        offers = reverse("bichiku:offer_list")
        self.assertEqual(len(self.client.get(offers, {"status": "recruiting"}).context["offers"]), s["recruiting_count"])

    def test_cards_link_with_filters(self):
        r = self.get()
        self.assertContains(r, "?status=reserved")
        self.assertContains(r, "?status=scheduled")
        self.assertContains(r, "?expiry=warning")
        self.assertContains(r, "?status=recruiting")

    def test_panel_order_labels_and_expired_alert(self):
        r = self.get()
        names = [row["lot"].stock_item.name for row in r.context["stats"]["expiring"]]
        self.assertEqual(names, ["切れた缶", "近い水", "近い米"])
        self.assertContains(r, "あと5日")
        self.assertContains(r, "期限切れの備蓄品が 1 件あります")
        self.assertContains(r, "?expiry=expired")
        self.assertNotContains(r, "遠い缶詰</a>")

    def test_offer_action_per_row(self):
        make_offer(self.company, self.near, quantity=5)                  # 募集中
        Offer.objects.create(lot=self.near2, organization=self.company, title="下書き", quantity=1,
                             pickup_location="p", status=Offer.Status.DRAFT)
        r = self.get()
        rows = {row["lot"].stock_item.name: row for row in r.context["stats"]["expiring"]}
        self.assertEqual(rows["近い水"]["offer_state"], "recruiting")
        self.assertEqual(rows["近い米"]["offer_state"], "draft")
        self.assertIsNone(rows["切れた缶"]["offer_state"])
        self.assertFalse(rows["切れた缶"]["can_offer"])                 # 期限切れは、募集を作れない
        self.assertContains(r, "募集中</a>")
        self.assertContains(r, "下書きあり")
        self.assertNotContains(r, "募集を作る")                            # 作れるものが、まだない
        fresh = make_lot(self.company, days=7, qty=9, name="新しい豆")
        r = self.get()
        self.assertContains(r, reverse("bichiku:offer_draft_from_lot", args=[fresh.pk]))
        self.assertContains(r, "募集を作る")

    def test_internal_lot_cannot_start_an_offer(self):
        make_lot(self.company, days=6, qty=5, name="社内用", availability=StockLot.Availability.INTERNAL)
        rows = {row["lot"].stock_item.name: row for row in self.stats()["expiring"]}
        self.assertFalse(rows["社内用"]["can_offer"])

    def test_isolated_per_organization(self):
        make_user("c2")
        login_as(self.client, "c2")
        s = self.stats()
        self.assertEqual((s["total"], s["expiring_count"], s["expired_count"]), (0, 0, 0))
        self.assertContains(self.get(), "消費期限が近い備蓄品はありません")

    def test_anonymous_still_renders(self):
        self.client.logout()
        self.assertEqual(self.get().status_code, 200)