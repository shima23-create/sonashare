from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import StockItem, StockLot
from .stock_counts import TARGET_CATEGORIES, category_count_map, category_counts
from .test_offers import make_lot, make_user

C = StockItem.Category


class CategoryTests(TestCase):
    def test_new_categories_and_merged_ones(self):
        values = [c.value for c in C]
        self.assertEqual(values, ["staple", "drink", "sanitary", "medical", "toilet", "other"])
        self.assertNotIn("canned", values)
        self.assertNotIn("retort", values)
        self.assertEqual(C.STAPLE.label, "主食")
        self.assertEqual((C.SANITARY.label, C.MEDICAL.label, C.TOILET.label), ("生理用品", "医療品", "簡易トイレ"))


class CountTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")
        self.today = timezone.localdate()

    def counts(self, org=None):
        return category_count_map(org or self.org)

    def test_zero_rows_for_every_target_category(self):
        rows = category_counts(self.org)
        self.assertEqual([r["category"] for r in rows], ["drink", "staple", "toilet"])
        self.assertTrue(all(r["total"] == 0 and r["by_unit"] == [] for r in rows))
        self.assertEqual([c.value for c in TARGET_CATEGORIES], ["drink", "staple", "toilet"])

    def test_sums_per_category(self):
        make_lot(self.org, qty=100, name="水", category=C.DRINK)
        make_lot(self.org, qty=20, days=90, name="水(別ロット)", category=C.DRINK)
        make_lot(self.org, qty=50, name="アルファ米", category=C.STAPLE)
        make_lot(self.org, qty=30, name="簡易トイレ", category=C.TOILET)
        make_lot(self.org, qty=5, name="ナプキン", category=C.SANITARY)      # 対象外
        self.assertEqual(self.counts(), {"drink": 120, "staple": 50, "toilet": 30})

    def test_no_expiry_counts_but_expired_and_empty_do_not(self):
        make_lot(self.org, qty=10, days=None, name="トイレ(期限なし)", category=C.TOILET)
        make_lot(self.org, qty=7, days=-1, name="切れた水", category=C.DRINK)
        make_lot(self.org, qty=0, name="空の米", category=C.STAPLE)
        self.assertEqual(self.counts(), {"drink": 0, "staple": 0, "toilet": 10})

    def test_internal_and_reserved_stock_still_counts(self):
        make_lot(self.org, qty=8, name="社内水", category=C.DRINK, availability=StockLot.Availability.INTERNAL)
        make_lot(self.org, qty=2, name="予約中の水", category=C.DRINK, availability=StockLot.Availability.RESERVED)
        self.assertEqual(self.counts()["drink"], 10)

    def test_by_unit_and_other_organizations_are_separate(self):
        lot = make_lot(self.org, qty=6, name="水", category=C.DRINK)
        item2 = StockItem.objects.create(organization=self.org, name="水(箱)", category=C.DRINK, unit="箱")
        StockLot.objects.create(stock_item=item2, quantity=2, expiration_date=self.today + timedelta(days=50), storage_place="倉庫")
        _, other = make_user("c2")
        make_lot(other, qty=999, name="他社の水", category=C.DRINK)
        drink = category_counts(self.org)[0]
        self.assertEqual((drink["total"], drink["lot_count"]), (8, 2))
        self.assertEqual(drink["by_unit"], [{"unit": "本", "quantity": 6}, {"unit": "箱", "quantity": 2}])