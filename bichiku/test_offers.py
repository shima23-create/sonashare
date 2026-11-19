from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .offer_forms import offerable_quantity
from .models import Offer, Organization, Profile, Reservation, StockItem, StockLot


User = get_user_model()
USERS = {}


def login_as(client, name):
    """標準ユーザーでも、メールでログインするカスタムユーザーでも動くようにする"""
    client.force_login(USERS[name])


def make_user(name, account_type=Organization.AccountType.COMPANY, with_profile=True):
    if "user_name" in [f.name for f in User._meta.get_fields()]:
        user = User.objects.create_user(email=f"{name}@example.com", user_name=name, password="pw")
    else:
        user = User.objects.create_user(name, password="pw")
    USERS[name] = user
    org = None
    if with_profile:
        org = Organization.objects.create(name=name, account_type=account_type)
        Profile.objects.create(user=user, organization=org)
    return user, org


def make_lot(org, days=20, qty=100, availability=StockLot.Availability.AVAILABLE, name="水", category=StockItem.Category.DRINK):
    item = StockItem.objects.create(
        organization=org, name=name, category=category, unit="本"
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
        "prefecture": "東京都",
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
        self.assertIn("login", r["Location"])

    def test_no_profile_forbidden_and_no_org_created(self):
        make_user("x", with_profile=False)
        login_as(self.client, "x")
        for name in ("offer_list", "item_list"):
            self.assertEqual(self.client.get(reverse(f"bichiku:{name}")).status_code, 403)
        self.assertEqual(Organization.objects.count(), 0)

    def test_group_forbidden(self):
        make_user("g", Organization.AccountType.GROUP)
        login_as(self.client, "g")
        self.assertEqual(self.client.get(reverse("bichiku:offer_list")).status_code, 403)

    def test_post_only_views(self):
        _, org = make_user("c")
        offer = Offer.objects.create(
            lot=make_lot(org), organization=org, title="t", quantity=1, pickup_location="p"
        )
        login_as(self.client, "c")
        for name in ("offer_publish", "offer_close", "offer_delete"):
            self.assertEqual(
                self.client.get(reverse(f"bichiku:{name}", args=[offer.pk])).status_code, 405
            )


class ItemListTests(TestCase):
    def setUp(self):
        _, self.org = make_user("c")
        login_as(self.client, "c")

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
        login_as(self.client, "c")
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
        self.assertContains(r, "超えています")
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.quantity, 100)  # 在庫は減らない
        self.assertEqual(offerable_quantity(self.lot), 30)

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

    def test_prefecture_is_required(self):
        r = self.client.post(self.create, offer_data(self.lot, prefecture=""))
        self.assertEqual(Offer.objects.count(), 0)
        self.assertIn("prefecture", r.context["form"].errors)  # 表示言語に左右されない

    def test_prefecture_defaults_to_organization(self):
        self.org.prefecture = "大阪府"
        self.org.save()
        r = self.client.get(self.create)
        self.assertEqual(r.context["form"].initial["prefecture"], "大阪府")
        self.client.post(reverse("bichiku:offer_draft_from_lot", args=[self.lot.pk]))
        self.assertEqual(Offer.objects.get().prefecture, "大阪府")

    def test_draft_without_prefecture_cannot_be_published(self):
        self.client.post(reverse("bichiku:offer_draft_from_lot", args=[self.lot.pk]))
        offer = Offer.objects.get()
        self.assertEqual(offer.prefecture, "")
        self.client.post(reverse("bichiku:offer_publish", args=[offer.pk]))
        offer.refresh_from_db()
        self.assertEqual(offer.status, "draft")

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


class QuantityDeductionTests(TestCase):
    """募集を公開しても、在庫(ロットの数量)は減らない。確保した数量だけが記録される"""

    def setUp(self):
        _, self.org = make_user("c")
        self.lot = make_lot(self.org, qty=100)
        login_as(self.client, "c")
        self.create = reverse("bichiku:offer_create")

    def lot_qty(self):
        self.lot.refresh_from_db()
        return self.lot.quantity

    def free(self):
        return offerable_quantity(self.lot)

    def test_draft_does_not_deduct(self):
        self.client.post(self.create, offer_data(self.lot, quantity=30))
        self.assertEqual((self.lot_qty(), self.free()), (100, 100))

    def test_publish_directly_deducts(self):
        self.client.post(self.create, offer_data(self.lot, quantity=30, action="publish"))
        self.assertEqual((self.lot_qty(), self.free()), (100, 70))

    def test_publish_draft_deducts_once(self):
        self.client.post(self.create, offer_data(self.lot, quantity=30))
        offer = Offer.objects.get()
        url = reverse("bichiku:offer_publish", args=[offer.pk])
        self.client.post(url)
        self.client.post(url)  # 2回押しても、確保するのは1回だけ
        self.assertEqual((self.lot_qty(), self.free()), (100, 70))

    def test_failed_publish_does_not_deduct(self):
        self.client.post(self.create, offer_data(self.lot, quantity=30, deadline="", action="publish"))
        self.assertEqual(self.lot_qty(), 100)

    def test_two_drafts_second_publish_fails(self):
        self.client.post(self.create, offer_data(self.lot, quantity=70))
        self.client.post(self.create, offer_data(self.lot, quantity=70))
        first, second = Offer.objects.order_by("id")
        self.client.post(reverse("bichiku:offer_publish", args=[first.pk]))
        self.client.post(reverse("bichiku:offer_publish", args=[second.pk]))
        second.refresh_from_db()
        self.assertEqual(second.status, "draft")
        self.assertEqual((self.lot_qty(), self.free()), (100, 30))

    def test_update_recruiting_adjusts_by_difference(self):
        self.client.post(self.create, offer_data(self.lot, quantity=30, action="publish"))
        offer = Offer.objects.get()
        edit = reverse("bichiku:offer_edit", args=[offer.pk])
        self.client.post(edit, offer_data(self.lot, quantity=50, action="save"))
        self.assertEqual((self.lot_qty(), self.free()), (100, 50))
        self.client.post(edit, offer_data(self.lot, quantity=10, action="save"))
        self.assertEqual((self.lot_qty(), self.free()), (100, 90))
        # 在庫(100)を超える数量は、エラー
        r = self.client.post(edit, offer_data(self.lot, quantity=101, action="save"))
        self.assertContains(r, "超えています")
        self.assertEqual((self.lot_qty(), self.free()), (100, 90))
        offer.refresh_from_db()
        self.assertEqual(offer.quantity, 10)

    def test_close_returns_unreserved(self):
        self.client.post(self.create, offer_data(self.lot, quantity=40, action="publish"))
        offer = Offer.objects.get()
        self.client.post(reverse("bichiku:offer_close", args=[offer.pk]))
        self.assertEqual(self.lot_qty(), 100)
        offer.refresh_from_db()
        self.assertEqual(offer.status, "closed")
        self.assertEqual(offer.quantity, 0)

    def test_close_keeps_reserved_part(self):
        self.client.post(self.create, offer_data(self.lot, quantity=40, action="publish"))
        offer = Offer.objects.get()
        _, group = make_user("g", Organization.AccountType.GROUP)
        Reservation.objects.create(
            offer=offer, organization=group, reserved_quantity=15,
            requested_pickup_at=timezone.now(),
        )
        self.client.post(reverse("bichiku:offer_close", args=[offer.pk]))
        self.assertEqual((self.lot_qty(), self.free()), (100, 85))  # 予約の15だけ確保が残る
        offer.refresh_from_db()
        self.assertEqual(offer.quantity, 15)
        self.client.post(reverse("bichiku:offer_close", args=[offer.pk]))  # 2回目は何も変わらない
        self.assertEqual((self.lot_qty(), self.free()), (100, 85))

    def test_delete_draft_keeps_quantity(self):
        self.client.post(self.create, offer_data(self.lot, quantity=30))
        offer = Offer.objects.get()
        self.client.post(reverse("bichiku:offer_delete", args=[offer.pk]))
        self.assertEqual(self.lot_qty(), 100)

    def test_sold_out_lot_not_selectable_or_suggested(self):
        self.client.post(self.create, offer_data(self.lot, quantity=100, action="publish"))
        self.assertEqual((self.lot_qty(), self.free()), (100, 0))
        r = self.client.post(self.create, offer_data(self.lot, quantity=1))
        self.assertEqual(Offer.objects.count(), 1)
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertEqual(list(r.context["suggestions"]), [])
        r = self.client.post(reverse("bichiku:offer_draft_from_lot", args=[self.lot.pk]))
        self.assertEqual(Offer.objects.count(), 1)

    def test_partially_offered_lot_still_suggested(self):
        self.client.post(self.create, offer_data(self.lot, quantity=40, action="publish"))
        r = self.client.get(reverse("bichiku:offer_list"))
        self.assertEqual(list(r.context["suggestions"]), [self.lot])