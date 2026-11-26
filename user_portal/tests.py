import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bichiku.models import Reservation
from bichiku.test_group import GROUP, make_offer
from bichiku.test_offers import login_as, make_lot, make_user

from .models import Contact


class UserPortalTests(TestCase):
    def setUp(self):
        _, self.company = make_user("portal_company")
        self.requester, self.group = make_user("portal_group", GROUP)
        self.lot = make_lot(self.company, qty=10)
        self.offer = make_offer(
            self.company, self.lot, quantity=8, title="地図で探せる保存水"
        )
        login_as(self.client, "portal_group")

    def test_map_page_uses_current_bichiku_offers_and_estimated_coordinates(self):
        response = self.client.get(reverse("user_portal:item_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "場所検索・ルート案内")
        self.assertContains(response, "地図で探せる保存水")
        self.assertContains(response, "地図を探す")
        self.assertContains(response, "募集を探す")
        self.assertContains(
            response,
            f'href="{reverse("user_portal:item_list")}" class="active"',
        )
        self.assertContains(response, "推定位置")
        spots = json.loads(response.context["map_spots_json"])
        self.assertEqual(len(spots), 1)
        self.assertFalse(spots[0]["coordinates_known"])
        self.assertIn("倉庫A", spots[0]["geocode_address"])
        self.assertEqual(spots[0]["items"][0]["id"], self.offer.pk)

    def test_map_page_hides_empty_inventory_message(self):
        response = self.client.get(reverse("user_portal:item_list"), {"q": "該当なし"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "条件に合う備蓄品はありません。")

    def test_prefecture_filter_displays_one_name_per_option(self):
        response = self.client.get(reverse("user_portal:item_list"))

        self.assertContains(
            response,
            '<option value="北海道" >北海道</option>',
            count=2,
        )
        self.assertNotContains(response, "('北海道', '北海道')")

    def test_map_search_reports_available_quantity_only(self):
        Reservation.objects.create(
            offer=self.offer,
            organization=self.group,
            reserved_quantity=3,
            requested_pickup_at=timezone.now() + timedelta(days=1),
            status=Reservation.Status.APPROVED,
        )

        response = self.client.get(
            reverse("user_portal:map_inventory_search"),
            {"q": "東京都千代田区"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["organizations"][0]["items"][0]["quantity"],
            5,
        )

    def test_map_search_requires_group_account_and_specific_query(self):
        endpoint = reverse("user_portal:map_inventory_search")
        self.assertEqual(self.client.get(endpoint, {"q": "東"}).status_code, 400)

        login_as(self.client, "portal_company")
        self.assertEqual(self.client.get(endpoint, {"q": "東京"}).status_code, 403)

    def test_portal_detail_redirects_to_existing_offer_reservation_flow(self):
        response = self.client.get(
            reverse("user_portal:item_detail", args=[self.offer.pk])
        )

        self.assertRedirects(
            response,
            reverse("bichiku:offer_detail", args=[self.offer.pk]),
        )

    def test_contact_is_saved_for_current_user(self):
        response = self.client.post(
            reverse("user_portal:contact"),
            {
                "name": "地域団体",
                "email": "group@example.com",
                "category": Contact.Category.GENERAL,
                "subject": "問い合わせ",
                "body": "確認したいことがあります。",
            },
        )

        self.assertRedirects(response, reverse("user_portal:contact_complete"))
        self.assertEqual(Contact.objects.get().sender, self.requester)

    def test_map_page_requires_group_account(self):
        login_as(self.client, "portal_company")

        self.assertEqual(
            self.client.get(reverse("user_portal:item_list")).status_code,
            403,
        )
