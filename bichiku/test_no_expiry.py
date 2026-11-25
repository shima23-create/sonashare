from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import StockLotForm
from .models import Offer, StockItem, StockLot
from .offer_forms import default_offer_values, publish_problems
from .test_group import make_offer, reserve_data
from .test_offers import login_as, make_lot, make_user, offer_data
from .test_reservations import GROUP

C = StockItem.Category


def form_data(**kw):
    data = {
        "name": "簡易トイレ", "category": "toilet", "unit": "個", "notes": "", "quantity": "10",
        "expiration_date": "", "storage_place": "倉庫", "availability": "available",
    }
    data.update(kw)
    return data


class RegistrationFormTests(TestCase):
    def test_no_expiry_checkbox_saves_empty_date(self):
        form = StockLotForm(form_data(no_expiry="on"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["expiration_date"])

    def test_no_expiry_overrides_a_typed_date(self):
        form = StockLotForm(form_data(no_expiry="on", expiration_date="2030-01-01"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["expiration_date"])

    def test_date_or_checkbox_is_required(self):
        form = StockLotForm(form_data())
        self.assertFalse(form.is_valid())
        self.assertIn("expiration_date", form.errors)
        self.assertTrue(StockLotForm(form_data(expiration_date="2030-01-01")).is_valid())

    def test_provided_is_not_offered_in_registration(self):
        form = StockLotForm()
        values = [v for v, _ in form.fields["availability"].choices]
        self.assertNotIn("provided", values)
        self.assertEqual(set(values), {"available", "internal", "reserved"})
        self.assertFalse(StockLotForm(form_data(no_expiry="on", availability="provided")).is_valid())
        # すでに提供済みのロットを編集するときだけ、残せる
        edit = StockLotForm(form_data(no_expiry="on", availability="provided"), allow_provided=True)
        self.assertTrue(edit.is_valid(), edit.errors)

    def test_new_categories_are_choices(self):
        values = [v for v, _ in StockLotForm().fields["category"].choices]
        self.assertEqual(values, ["staple", "drink", "sanitary", "medical", "toilet", "other"])


class NoExpiryModelTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")

    def test_status_label_badge_and_str(self):
        lot = make_lot(self.org, days=None, name="トイレ", category=C.TOILET)
        self.assertEqual((lot.expiry_status, lot.expiry_label, lot.expiry_badge_class), ("none", "期限なし", "badge-muted"))
        self.assertIn("期限なし", str(lot))

    def test_no_expiry_sorts_last(self):
        make_lot(self.org, days=None, name="期限なし")
        make_lot(self.org, days=50, name="後")
        make_lot(self.org, days=5, name="先")
        self.assertEqual([l.stock_item.name for l in StockLot.objects.all()], ["先", "後", "期限なし"])


class ItemListFilterTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")
        make_lot(self.org, days=None, name="期限なし")
        make_lot(self.org, days=200, name="正常")
        make_lot(self.org, days=5, name="間近")
        make_lot(self.org, days=-2, name="切れ")
        login_as(self.client, "c")

    def names(self, **params):
        r = self.client.get(reverse("bichiku:item_list"), params)
        return sorted(l.stock_item.name for l in r.context["inventory_lots"])

    def test_filters(self):
        self.assertEqual(self.names(expiry="ok"), sorted(["正常", "期限なし"]))
        self.assertEqual(self.names(expiry="none"), ["期限なし"])
        self.assertEqual(self.names(expiry="warning"), ["間近"])
        self.assertEqual(self.names(expiry="expired"), ["切れ"])
        self.assertEqual(len(self.names()), 4)

    def test_new_category_filter(self):
        make_lot(self.org, days=None, name="簡易トイレ", category=C.TOILET)
        self.assertEqual(self.names(category="toilet"), ["簡易トイレ"])


class NoExpiryOfferFlowTests(TestCase):
    def setUp(self):
        self.company_user, self.company = make_user("c")
        self.group_user, self.group = make_user("g", GROUP)
        self.lot = make_lot(self.company, days=None, qty=50, name="簡易トイレ", category=C.TOILET)

    def test_default_deadline_and_publish_without_expiry(self):
        values = default_offer_values(self.lot)
        self.assertEqual(values["deadline"], timezone.localdate() + timedelta(days=30))
        offer = Offer(lot=self.lot, organization=self.company, title="t", quantity=10,
                      pickup_location="p", prefecture="東京都", deadline=values["deadline"])
        self.assertEqual(publish_problems(offer), [])

    def test_company_can_publish_and_group_can_find_and_reserve(self):
        login_as(self.client, "c")
        r = self.client.post(reverse("bichiku:offer_create"), offer_data(self.lot, quantity=20, action="publish"))
        self.assertEqual(Offer.objects.get().status, "recruiting")
        login_as(self.client, "g")
        r = self.client.get(reverse("bichiku:offer_browse"))
        self.assertEqual(len(r.context["offers"]), 1)
        offer = Offer.objects.get()
        detail = self.client.get(reverse("bichiku:offer_detail", args=[offer.pk]))
        self.assertContains(detail, "期限なし")
        self.client.post(reverse("bichiku:offer_detail", args=[offer.pk]), reserve_data(5))
        self.assertEqual(offer.reservations.count(), 1)

    def test_browse_sort_by_expiry_puts_no_expiry_last(self):
        near = make_lot(self.company, days=10, qty=5, name="近い")
        for lot in (self.lot, near):
            make_offer(self.company, lot, quantity=3)
        login_as(self.client, "g")
        r = self.client.get(reverse("bichiku:offer_browse"), {"sort": "expiry"})
        self.assertEqual([o.lot.stock_item.name for o in r.context["offers"]], ["近い", "簡易トイレ"])

    def test_offer_form_lists_no_expiry_lot(self):
        login_as(self.client, "c")
        r = self.client.get(reverse("bichiku:offer_create"))
        labels = [str(o) for o in r.context["form"].fields["lot"].queryset]
        self.assertTrue(any("簡易トイレ" in l for l in labels))
        self.assertContains(r, "期限なし")

    def test_dashboard_does_not_flag_no_expiry_lot(self):
        login_as(self.client, "c")
        s = self.client.get(reverse("bichiku:dashboard")).context["stats"]
        self.assertEqual((s["expiring_count"], s["expired_count"], s["total"]), (0, 0, 1))