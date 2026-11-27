from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from . import impact_factors as f
from .impact_stats import impact_stats
from .models import Offer, PickupRecord, Reservation, StockItem, StockLot
from .test_group import make_offer
from .test_offers import make_user
from .test_reservations import GROUP

C = StockItem.Category


def lot_of(org, category, unit, qty=100, days=20, name="品"):
    item = StockItem.objects.create(organization=org, name=name, category=category, unit=unit)
    return StockLot.objects.create(
        stock_item=item, quantity=qty, storage_place="倉庫",
        expiration_date=None if days is None else timezone.localdate() + timedelta(days=days),
    )


class WeightTests(TestCase):
    def test_weight_table(self):
        self.assertEqual(f.weight_kg(C.DRINK, "ケース", 2), 24)
        self.assertEqual(f.weight_kg(C.STAPLE, "食", 4), 1.0)
        self.assertIsNone(f.weight_kg(C.DRINK, "食", 3))      # 表にない組み合わせ
        self.assertIsNone(f.weight_kg(C.TOILET, "個", 3))     # 食品ではない
        self.assertEqual(set(f.FOOD_CATEGORIES), {C.DRINK, C.STAPLE})


class ImpactTests(TestCase):
    def setUp(self):
        self.cu, self.company = make_user("c")
        self.gu, self.group = make_user("g", GROUP)

    def receive(self, lot, quantity, status=PickupRecord.PickupStatus.COMPLETED, days_ago=0):
        offer = make_offer(self.company, lot, quantity=quantity)
        res = Reservation.objects.create(
            offer=offer, organization=self.group, reserved_quantity=quantity,
            requested_pickup_at=timezone.now(), status=Reservation.Status.COMPLETED,
        )
        return PickupRecord.objects.create(
            reservation=res, user=self.gu, received_quantity=quantity,
            picked_up_at=timezone.now() - timedelta(days=days_ago), pickup_status=status,
        )

    def test_empty(self):
        s = impact_stats(self.company)
        self.assertEqual((s["total_kg"], s["co2_kg"], s["saved_yen"]), (0, 0, 0))
        self.assertEqual(len(s["monthly"]), 12)

    def test_kg_co2_and_yen(self):
        self.receive(lot_of(self.company, C.DRINK, "本"), 20)         # 10kg
        self.receive(lot_of(self.company, C.STAPLE, "食"), 40, PickupRecord.PickupStatus.PARTIAL)  # 10kg
        s = impact_stats(self.company)
        self.assertEqual(s["total_kg"], 20)
        self.assertEqual(s["co2_kg"], 44.0)
        self.assertEqual(s["saved_yen"], 20 * 46)
        self.assertEqual({c["label"]: c["kg"] for c in s["categories"]}, {"飲料": 10, "主食": 10})

    def test_group_sees_same_records_and_other_orgs_do_not(self):
        self.receive(lot_of(self.company, C.DRINK, "本"), 10)
        self.assertEqual(impact_stats(self.group)["total_kg"], 5)
        _, other = make_user("c2")
        self.assertEqual(impact_stats(other)["total_kg"], 0)

    def test_non_food_unknown_unit_and_no_show_are_not_counted(self):
        self.receive(lot_of(self.company, C.TOILET, "個"), 10)
        self.receive(lot_of(self.company, C.DRINK, "食"), 10)
        self.receive(lot_of(self.company, C.DRINK, "本"), 10, PickupRecord.PickupStatus.NO_SHOW)
        s = impact_stats(self.company)
        self.assertEqual(s["total_kg"], 0)
        self.assertEqual((s["excluded_count"], s["unconverted_count"], s["converted_count"]), (1, 1, 0))

    def test_old_records_are_outside_the_period(self):
        self.receive(lot_of(self.company, C.DRINK, "本"), 10, days_ago=400)
        self.assertEqual(impact_stats(self.company)["total_kg"], 0)

    def test_monthly_bars(self):
        self.receive(lot_of(self.company, C.DRINK, "本"), 10)
        s = impact_stats(self.company)
        self.assertEqual(s["monthly"][-1]["kg"], 5)
        self.assertEqual(s["monthly"][-1]["bar_percent"], 100)
        self.assertEqual(s["monthly"][0]["bar_percent"], 0)

    def test_at_risk_and_expired_stock(self):
        lot_of(self.company, C.DRINK, "本", qty=20, days=10)      # 近い 10kg
        lot_of(self.company, C.DRINK, "本", qty=10, days=-2)      # 切れ 5kg
        lot_of(self.company, C.DRINK, "本", qty=10, days=200)     # 問題なし
        lot_of(self.company, C.DRINK, "本", qty=10, days=None)    # 期限なし
        lot_of(self.company, C.TOILET, "個", qty=10, days=5)      # 食品ではない
        s = impact_stats(self.company)
        self.assertEqual((s["at_risk_kg"], s["expired_kg"]), (10, 5))
        self.assertEqual((s["at_risk_yen"], s["expired_yen"]), (460, 230))


class ImpactTemplateTests(TestCase):
    def test_section_renders_numbers_and_notes(self):
        from django.template.loader import render_to_string

        _, company = make_user("c")
        lot_of(company, C.DRINK, "本", qty=2000, days=10)    # 近い 1000kg
        html = render_to_string("bichiku/_impact_section.html", {"impact": impact_stats(company)})
        self.assertIn("食品ロス削減の効果", html)
        self.assertIn("46,000", html)       # 1000kg × 46円(桁区切り)
        self.assertIn("概算", html)
        self.assertIn("46円/kg", html)
