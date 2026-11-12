from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Offer, Organization, Profile, Reservation, StockItem, StockLot


def make_user(name, account_type=Organization.AccountType.COMPANY, with_profile=True):
    user = User.objects.create_user(name, password="pw")
    org = None
    if with_profile:
        org = Organization.objects.create(name=name, account_type=account_type)
        Profile.objects.create(user=user, organization=org)
    return user, org


def make_lot(org, days=20, qty=100, availability=StockLot.Availability.AVAILABLE, name="水"):
    item = StockItem.objects.create(
        organization=org, name=name, category=StockItem.Category.DRINK, unit="本"
    )
    return StockLot.objects.create(
        stock_item=item,
        quantity=qty,
        expiration_date=timezone.localdate() + timedelta(days=days),
        storage_place="倉庫A",
        availability=availability,
    )


def offer_data(lot, **kw):
    data = {
        "lot": lot.pk,
        "title": "水を提供します",
        "quantity": 10,
        "pickup_location": "倉庫A",
        "receiving_conditions": "",
        "description": "",
        "deadline": (timezone.localdate() + timedelta(days=5)).isoformat(),
        "action": "draft",
    }
    data.update(kw)
    return data


class AccessTests(TestCase):
    def test_anonymous_redirected(self):
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_no_profile_forbidden_and_no_org_created(self):
        make_user("x", with_profile=False)
        self.client.login(username="x", password="pw")
        for name in ("offer_list", "item_list"):
            self.assertEqual(self.client.get(reverse(f"bichiku:{name}")).status_code, 403)
        self.assertEqual(Organization.objects.count(), 0)

    def test_group_forbidden(self):
        make_user("g", Organization.AccountType.GROUP)
        self.client.login(username="g", password="pw")
        self.assertEqual(self.client.get(reverse("bichiku:offer_list")).status_code, 403)

    def test_post_only_views(self):
        _, org = make_user("c")
        offer = Offer.objects.create(
            lot=make_lot(org), organization=org, title="t", quantity=1, pickup_location="p"
        )
        self.client.login(username="c", password="pw")
        for name in ("offer_publish", "offer_close", "offer_delete"):
            self.assertEqual(
                self.client.get(reverse(f"bichiku:{name}", args=[offer.pk])).status_code, 405
            )


class ItemListTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")
        self.client.login(username="c", password="pw")

    def post(self, **kw):
        data = {
            "name": "水", "category": "drink", "unit": "本", "notes": "",
            "quantity": 5, "expiration_date": "2030-01-01",
            "storage_place": "倉庫", "availability": "available",
        }
        data.update(kw)
        return self.client.post(reverse("bichiku:item_list"), data)

    def test_reuses_stock_item(self):
        self.post()
        self.post(quantity=7)
        self.assertEqual(StockItem.objects.count(), 1)
        self.assertEqual(StockLot.objects.count(), 2)

    def test_internal_lot_can_be_registered(self):
        self.post(availability="internal")
        self.assertEqual(StockLot.objects.get().availability, "internal")

    def test_tenant_isolation_and_filter(self):
        _, other = make_user("o")
        make_lot(other, name="他社の品")
        make_lot(self.org, name="自社の品")
        r = self.client.get(reverse("bichiku:item_list"), {"q": "品"})
        names = [l.stock_item.name for l in r.context["inventory_lots"]]
        self.assertEqual(names, ["自社の品"])


class OfferTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")
        self.lot = make_lot(self.org)
        self.client.login(username="c", password="pw")
        self.create = reverse("bichiku:offer_create")

    def test_create_draft_then_publish(self):
        self.client.post(self.create, offer_data(self.lot))
        offer = Offer.objects.get()
        self.assertEqual(offer.status, "draft")
        self.assertEqual(offer.organization, self.org)
        self.client.post(reverse("bichiku:offer_publish", args=[offer.pk]))
        offer.refresh_from_db()
        self.assertEqual(offer.status, "recruiting")

    def test_publish_directly(self):
        self.client.post(self.create, offer_data(self.lot, action="publish"))
        self.assertEqual(Offer.objects.get().status, "recruiting")

    def test_quantity_over_lot_rejected(self):
        r = self.client.post(self.create, offer_data(self.lot, quantity=101))
        self.assertEqual(Offer.objects.count(), 0)
        self.assertContains(r, "超えています")

    def test_over_offer_across_two_recruiting_rejected(self):
        self.client.post(self.create, offer_data(self.lot, quantity=70, action="publish"))
        r = self.client.post(self.create, offer_data(self.lot, quantity=40, action="publish"))
        self.assertEqual(Offer.objects.count(), 1)
        self.assertContains(r, "残りは 30")

    def test_expired_lot_cannot_publish(self):
        lot = make_lot(self.org, days=-1, name="古い")
        offer = Offer.objects.create(
            lot=lot, organization=self.org, title="t", quantity=1,
            pickup_location="p", deadline=timezone.localdate(),
        )
        self.client.post(reverse("bichiku:offer_publish", args=[offer.pk]))
        offer.refresh_from_db()
        self.assertEqual(offer.status, "draft")

    def test_deadline_required_to_publish(self):
        r = self.client.post(self.create, offer_data(self.lot, deadline="", action="publish"))
        self.assertEqual(Offer.objects.count(), 0)
        self.assertContains(r, "募集締切日")

    def test_deadline_after_expiry_rejected(self):
        late = (self.lot.expiration_date + timedelta(days=1)).isoformat()
        self.client.post(self.create, offer_data(self.lot, deadline=late))
        self.assertEqual(Offer.objects.count(), 0)

    def test_internal_lot_not_selectable(self):
        lot = make_lot(self.org, availability="internal", name="社内")
        self.client.post(self.create, offer_data(lot))
        self.assertEqual(Offer.objects.count(), 0)

    def test_other_org_gets_404(self):
        _, other = make_user("o")
        offer = Offer.objects.create(
            lot=make_lot(other, name="他"), organization=other, title="t",
            quantity=1, pickup_location="p",
        )
        for name in ("offer_edit",):
            self.assertEqual(self.client.get(reverse(f"bichiku:{name}", args=[offer.pk])).status_code, 404)
        for name in ("offer_publish", "offer_close", "offer_delete"):
            self.assertEqual(self.client.post(reverse(f"bichiku:{name}", args=[offer.pk])).status_code, 404)

    def test_close_and_delete_rules(self):
        self.client.post(self.create, offer_data(self.lot, action="publish"))
        offer = Offer.objects.get()
        self.client.post(reverse("bichiku:offer_delete", args=[offer.pk]))
        self.assertEqual(Offer.objects.count(), 1)  # 募集中は削除不可
        self.client.post(reverse("bichiku:offer_close", args=[offer.pk]))
        offer.refresh_from_db()
        self.assertEqual(offer.status, "closed")
        r = self.client.get(reverse("bichiku:offer_edit", args=[offer.pk]))
        self.assertEqual(r.status_code, 302)  # 終了後は編集不可

    def test_delete_draft(self):
        self.client.post(self.create, offer_data(self.lot))
        offer = Offer.objects.get()
        self.client.post(reverse("bichiku:offer_delete", args=[offer.pk]))
        self.assertEqual(Offer.objects.count(), 0)

    def test_quick_draft_creates_one(self):
        url = reverse("bichiku:offer_draft_from_lot", args=[self.lot.pk])
        self.client.post(url)
        self.client.post(url)
        offer = Offer.objects.get()
        self.assertEqual(offer.status, "draft")
        self.assertEqual(offer.quantity, 100)
        self.assertLessEqual(offer.deadline, self.lot.expiration_date)

    def test_quick_draft_refuses_internal_and_other_org(self):
        lot = make_lot(self.org, availability="internal", name="社内")
        self.client.post(reverse("bichiku:offer_draft_from_lot", args=[lot.pk]))
        self.assertEqual(Offer.objects.count(), 0)
        _, other = make_user("o")
        olot = make_lot(other, name="他")
        r = self.client.post(reverse("bichiku:offer_draft_from_lot", args=[olot.pk]))
        self.assertEqual(r.status_code, 404)

    def test_list_suggestions(self):
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertEqual(list(r.context["suggestions"]), [self.lot])
        self.client.post(reverse("bichiku:offer_draft_from_lot", args=[self.lot.pk]))
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertEqual(list(r.context["suggestions"]), [])
        self.assertContains(r, "下書き")

    def test_edit_below_reserved_rejected(self):
        self.client.post(self.create, offer_data(self.lot, quantity=50, action="publish"))
        offer = Offer.objects.get()
        _, group = make_user("g", Organization.AccountType.GROUP)
        Reservation.objects.create(
            offer=offer, organization=group, reserved_quantity=30,
            requested_pickup_at=timezone.now(),
        )
        r = self.client.post(
            reverse("bichiku:offer_edit", args=[offer.pk]),
            offer_data(self.lot, quantity=20, action="save"),
        )
        offer.refresh_from_db()
        self.assertEqual(offer.quantity, 50)
        self.assertContains(r, "予約が入っている")
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertEqual(r.context["offers"][0].reserved_total, 30)
