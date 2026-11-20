from django.test import TestCase
from django.urls import reverse

from .models import Offer, Organization, StockLot
from .test_group import make_offer
from .test_offers import login_as, make_lot, make_user
from .test_reservations import GROUP, R, make_reservation


class DashboardTests(TestCase):
    def setUp(self):
        _, self.company = make_user("c")
        self.group_user, self.group = make_user("g", GROUP)
        self.near = make_lot(self.company, days=5, qty=10, name="近い水")
        self.expired = make_lot(self.company, days=-3, qty=4, name="切れた米")
        self.far = make_lot(self.company, days=200, qty=50, name="遠い缶詰")
        self.internal = make_lot(
            self.company, days=100, qty=7, name="社内用",
            availability=StockLot.Availability.INTERNAL,
        )
        self.empty = make_lot(self.company, days=2, qty=0, name="空のロット")
        login_as(self.client, "c")

    def stats(self):
        return self.client.get(reverse("bichiku:dashboard")).context["stats"]

    def test_counts(self):
        s = self.stats()
        self.assertEqual(s["total"], 5)
        self.assertEqual(s["expiring_count"], 2)      # 近い水 + 切れた米(数量0は除く)
        self.assertEqual(s["available_count"], 2)     # 近い水 + 遠い缶詰(期限切れ・社内用・0は除く)
        self.assertEqual(s["reserved_count"], 0)

    def test_reserved_count_only_active_and_own(self):
        offer = make_offer(self.company, self.far, quantity=10)
        make_reservation(offer, self.group, 1, R.PENDING)
        make_reservation(offer, self.group, 1, R.APPROVED)
        make_reservation(offer, self.group, 1, R.CANCELLED)
        make_reservation(offer, self.group, 1, R.COMPLETED)
        _, other_company = make_user("c2")
        other_offer = make_offer(other_company, make_lot(other_company, name="他社"), quantity=5)
        make_reservation(other_offer, self.group, 1, R.PENDING)
        self.assertEqual(self.stats()["reserved_count"], 2)

    def test_panel_lists_soonest_first_with_labels(self):
        r = self.client.get(reverse("bichiku:dashboard"))
        names = [row["lot"].stock_item.name for row in r.context["stats"]["expiring"]]
        self.assertEqual(names, ["切れた米", "近い水"])
        self.assertContains(r, "期限切れ")
        self.assertContains(r, "あと5日")
        self.assertNotContains(r, "遠い缶詰</a>")

    def test_isolated_per_organization(self):
        make_user("c2")
        login_as(self.client, "c2")
        s = self.stats()
        self.assertEqual((s["total"], s["expiring_count"]), (0, 0))
        self.assertContains(self.client.get(reverse("bichiku:dashboard")), "消費期限が近い備蓄品はありません")

    def test_anonymous_still_renders(self):
        self.client.logout()
        r = self.client.get(reverse("bichiku:dashboard"))
        self.assertEqual(r.status_code, 200)