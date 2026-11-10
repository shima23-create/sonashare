from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import (
    Conversation,
    Message,
    Offer,
    Organization,
    PickupRecord,
    Profile,
    Reservation,
    StockItem,
    StockLot,
)


class IndexAndReservationTests(TestCase):
    def test_root_displays_index_page(self):
        response = self.client.get(reverse("bichiku:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bichiku/index.html")
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:signup"))

    def test_authenticated_header_shows_login_name_and_account_menu(self):
        user = get_user_model().objects.create_user(
            username="login-name@example.com",
            email="login-name@example.com",
            first_name="別の表示名",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("bichiku:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "login-name@example.com")
        self.assertContains(response, "ログイン中")
        self.assertContains(response, "マイページ")
        self.assertContains(
            response,
            f'href="{reverse("bichiku:my_page")}#page-top"',
        )
        self.assertContains(response, reverse("accounts:logout"))

    def test_reservations_require_login(self):
        response = self.client.get(reverse("bichiku:reservation_list"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('bichiku:reservation_list')}",
        )

    def test_logged_in_user_can_open_reservations(self):
        user = get_user_model().objects.create_user(
            username="reservations@example.com",
            email="reservations@example.com",
            password="test-password-123",
        )
        self.client.force_login(user)

        reservations_response = self.client.get(reverse("bichiku:reservation_list"))

        self.assertEqual(reservations_response.status_code, 200)
        self.assertTemplateUsed(reservations_response, "bichiku/reservations.html")
        self.assertContains(reservations_response, 'class="reservation-detail-trigger"')
        self.assertContains(reservations_response, 'class="reservation-detail-popover"')

    def test_dashboard_stat_cards_link_to_inventory_and_reservations(self):
        response = self.client.get(reverse("bichiku:dashboard"))

        self.assertEqual(response.status_code, 200)
        inventory_url = reverse("bichiku:item_list")
        reservations_url = reverse("bichiku:reservation_list")
        content = response.content.decode()

        inventory_card_link = (
            f'href="{inventory_url}" class="card stat-card stat-card-link"'
        )
        self.assertEqual(content.count(inventory_card_link), 3)
        self.assertIn(f'href="{reservations_url}" class="card stat-card stat-card-link"', content)


class InventoryRegistrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inventory@example.com",
            email="inventory@example.com",
            first_name="サンプル企業",
            password="test-password-123",
        )
        organization = Organization.objects.create(
            name="サンプル企業",
            account_type=Organization.AccountType.COMPANY,
        )
        Profile.objects.create(user=self.user, organization=organization)
        self.client.force_login(self.user)

    def test_register_button_opens_inventory_form(self):
        response = self.client.get(reverse("bichiku:item_list"), {"register": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="inventoryRegisterTitle"')
        self.assertContains(response, 'name="expiration_date"')

    def test_inventory_submission_creates_item_and_lot(self):
        response = self.client.post(
            reverse("bichiku:item_list"),
            {
                "name": "保存水（500ml）",
                "category": StockItem.Category.DRINK,
                "quantity": 30,
                "unit": "本",
                "expiration_date": "2027-12-31",
                "storage_place": "第1倉庫 A棚",
                "availability": StockLot.Availability.AVAILABLE,
                "notes": "登録テスト",
            },
        )

        self.assertRedirects(response, reverse("bichiku:item_list"))
        item = StockItem.objects.get(name="保存水（500ml）")
        lot = StockLot.objects.get(stock_item=item)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(item.organization, profile.organization)
        self.assertEqual(item.category, StockItem.Category.DRINK)
        self.assertEqual(item.unit, "本")
        self.assertEqual(item.notes, "登録テスト")
        self.assertEqual(lot.quantity, 30)
        self.assertEqual(lot.storage_place, "第1倉庫 A棚")
        self.assertContains(self.client.get(reverse("bichiku:item_list")), "保存水（500ml）")

    def test_invalid_submission_keeps_form_open_with_errors(self):
        response = self.client.post(
            reverse("bichiku:item_list"),
            {
                "name": "",
                "category": StockItem.Category.DRINK,
                "quantity": -1,
                "unit": "本",
                "expiration_date": "not-a-date",
                "storage_place": "",
                "availability": StockLot.Availability.AVAILABLE,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="inventory-register-overlay"')
        self.assertEqual(StockItem.objects.count(), 0)

    def create_inventory_lot(
        self,
        name="保存水",
        category=StockItem.Category.DRINK,
        expiration_date="2027-12-31",
        availability=StockLot.Availability.AVAILABLE,
        storage_place="第1倉庫 A棚",
        notes="備考",
    ):
        item = StockItem.objects.create(
            organization=self.user.profile.organization,
            name=name,
            category=category,
            unit="本",
            notes=notes,
        )
        return StockLot.objects.create(
            stock_item=item,
            quantity=20,
            expiration_date=expiration_date,
            storage_place=storage_place,
            availability=availability,
        )

    def test_inventory_statuses_use_distinct_color_badges(self):
        self.create_inventory_lot(
            name="提供可能な水",
            availability=StockLot.Availability.AVAILABLE,
        )
        self.create_inventory_lot(
            name="予約中の水",
            availability=StockLot.Availability.RESERVED,
        )
        self.create_inventory_lot(
            name="提供済みの水",
            availability=StockLot.Availability.PROVIDED,
        )

        response = self.client.get(reverse("bichiku:item_list"))

        self.assertContains(response, 'class="badge badge-available">提供可能</span>')
        self.assertContains(response, 'class="badge badge-reserved">予約中</span>')
        self.assertContains(response, 'class="badge badge-provided">提供済み</span>')

    def test_inventory_keyword_search_matches_name_location_and_notes(self):
        self.create_inventory_lot(name="備蓄水", storage_place="第3倉庫")
        self.create_inventory_lot(name="非常食", notes="アレルギー対応")

        response = self.client.get(reverse("bichiku:item_list"), {"q": "第3倉庫"})

        self.assertContains(response, "備蓄水")
        self.assertNotContains(response, "非常食")

        response = self.client.get(reverse("bichiku:item_list"), {"q": "備蓄水"})

        self.assertContains(response, "備蓄水")
        self.assertNotContains(response, "非常食")

        response = self.client.get(reverse("bichiku:item_list"), {"q": "アレルギー"})

        self.assertContains(response, "非常食")
        self.assertNotContains(response, "備蓄水")

    def test_inventory_filters_by_category_and_availability(self):
        self.create_inventory_lot(
            name="提供できる水",
            category=StockItem.Category.DRINK,
            availability=StockLot.Availability.AVAILABLE,
        )
        self.create_inventory_lot(
            name="予約中の缶詰",
            category=StockItem.Category.CANNED,
            availability=StockLot.Availability.RESERVED,
        )

        response = self.client.get(
            reverse("bichiku:item_list"),
            {
                "category": StockItem.Category.CANNED,
                "status": StockLot.Availability.RESERVED,
            },
        )

        self.assertContains(response, "予約中の缶詰")
        self.assertNotContains(response, "提供できる水")
        self.assertContains(response, '<option value="canned" selected>')
        self.assertContains(response, '<option value="reserved" selected>')

    def test_inventory_filter_by_expiration_status(self):
        today = timezone.localdate()
        self.create_inventory_lot(
            name="期限切れ食品",
            expiration_date=today - timedelta(days=1),
        )
        self.create_inventory_lot(
            name="期限間近食品",
            expiration_date=today + timedelta(days=7),
        )
        self.create_inventory_lot(
            name="期限に余裕のある食品",
            expiration_date=today + timedelta(days=60),
        )

        response = self.client.get(
            reverse("bichiku:item_list"), {"expiry": "warning"}
        )

        self.assertContains(response, "期限間近食品")
        self.assertNotContains(response, "期限切れ食品")
        self.assertNotContains(response, "期限に余裕のある食品")

    def test_inventory_row_shows_actions_in_requested_order(self):
        lot = self.create_inventory_lot()

        response = self.client.get(reverse("bichiku:item_list"))
        action_cell = response.content.decode().split(
            '<span class="actions inventory-actions">', 1
        )[1].split("</span>", 1)[0]

        self.assertLess(
            action_cell.index(
                f'data-delete-url="{reverse("bichiku:item_delete", args=[lot.pk])}"'
            ),
            action_cell.index(f'href="{reverse("bichiku:item_edit", args=[lot.pk])}"'),
        )
        self.assertLess(
            action_cell.index(f'href="{reverse("bichiku:item_edit", args=[lot.pk])}"'),
            action_cell.index(f'href="{reverse("bichiku:item_detail", args=[lot.pk])}"'),
        )

    def test_delete_action_uses_custom_confirmation_dialog(self):
        lot = self.create_inventory_lot(name="保存水（500ml）")

        response = self.client.get(reverse("bichiku:item_list"))

        self.assertContains(response, 'id="inventoryDeleteDialog"')
        self.assertContains(response, "備蓄品を削除")
        self.assertContains(response, "この操作は取り消せません。")
        self.assertContains(response, "キャンセル")
        self.assertContains(response, "削除する")
        self.assertContains(
            response,
            f'data-delete-url="{reverse("bichiku:item_delete", args=[lot.pk])}"',
        )
        self.assertContains(response, 'data-item-name="保存水（500ml）"')
        self.assertNotContains(response, "onsubmit=\"return confirm")

    def test_detail_action_shows_inventory_details(self):
        lot = self.create_inventory_lot()

        response = self.client.get(reverse("bichiku:item_detail", args=[lot.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "備蓄品の詳細")
        self.assertContains(response, "第1倉庫 A棚")

    def test_edit_action_updates_item_and_lot(self):
        lot = self.create_inventory_lot()

        response = self.client.post(
            reverse("bichiku:item_edit", args=[lot.pk]),
            {
                "name": "更新後の保存水",
                "category": StockItem.Category.DRINK,
                "quantity": 35,
                "unit": "本",
                "expiration_date": "2028-01-31",
                "storage_place": "第2倉庫 B棚",
                "availability": StockLot.Availability.RESERVED,
                "notes": "更新した備考",
            },
        )

        self.assertRedirects(response, reverse("bichiku:item_list"))
        lot.refresh_from_db()
        lot.stock_item.refresh_from_db()
        self.assertEqual(lot.stock_item.name, "更新後の保存水")
        self.assertEqual(lot.quantity, 35)
        self.assertEqual(lot.storage_place, "第2倉庫 B棚")
        self.assertEqual(lot.stock_item.notes, "更新した備考")

    def test_delete_action_removes_lot_and_unused_item(self):
        lot = self.create_inventory_lot()
        item = lot.stock_item

        response = self.client.post(reverse("bichiku:item_delete", args=[lot.pk]))

        self.assertRedirects(response, reverse("bichiku:item_list"))
        self.assertFalse(StockLot.objects.filter(pk=lot.pk).exists())
        self.assertFalse(StockItem.objects.filter(pk=item.pk).exists())

    def test_inventory_actions_do_not_expose_other_organizations(self):
        lot = self.create_inventory_lot()
        other_user = get_user_model().objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="test-password-123",
        )
        self.client.force_login(other_user)

        response = self.client.get(reverse("bichiku:item_detail", args=[lot.pk]))

        self.assertEqual(response.status_code, 404)


class MessagesAndMyPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(
            username="requester@example.com",
            email="requester@example.com",
            first_name="さくら子ども食堂",
            password="initial-password-123",
        )
        self.provider = user_model.objects.create_user(
            username="provider@example.com",
            email="provider@example.com",
            first_name="備蓄企業",
            password="initial-password-123",
        )
        self.requester_org = Organization.objects.create(
            name="さくら子ども食堂",
            account_type=Organization.AccountType.GROUP,
            address="東京都世田谷区",
            postal_code="155-0033",
            phone_number="03-1234-5678",
            contact_person_name="佐藤 花子",
        )
        self.provider_org = Organization.objects.create(
            name="備蓄企業",
            account_type=Organization.AccountType.COMPANY,
        )
        Profile.objects.create(user=self.requester, organization=self.requester_org)
        Profile.objects.create(user=self.provider, organization=self.provider_org)
        stock_item = StockItem.objects.create(
            organization=self.provider_org,
            name="保存水",
            category=StockItem.Category.DRINK,
            unit="本",
        )
        lot = StockLot.objects.create(
            stock_item=stock_item,
            quantity=20,
            expiration_date="2027-12-31",
            storage_place="倉庫",
        )
        offer = Offer.objects.create(
            lot=lot,
            organization=self.provider_org,
            title="保存水の提供",
            quantity=10,
            pickup_location="本社",
        )
        reservation = Reservation.objects.create(
            offer=offer,
            organization=self.requester_org,
            reserved_quantity=5,
            requested_pickup_at=timezone.now(),
        )
        self.conversation = Conversation.objects.create(reservation=reservation)
        self.client.force_login(self.requester)

    def test_messages_page_lists_conversations_and_unread_count(self):
        Message.objects.create(
            conversation=self.conversation,
            sender=self.provider,
            content="受け取り日時をご相談できますか？",
        )

        response = self.client.get(reverse("bichiku:messages"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "備蓄企業")
        self.assertContains(response, "受け取り日時をご相談できますか？")
        self.assertContains(response, 'class="badge-count">1</span>')

    def test_dashboard_links_to_recent_conversations(self):
        Message.objects.create(
            conversation=self.conversation,
            sender=self.provider,
            content="備蓄品を提供できます。",
        )

        response = self.client.get(reverse("bichiku:dashboard"))

        self.assertContains(response, "備蓄品を提供できます。")
        self.assertContains(
            response,
            reverse("bichiku:conversation_detail", args=[self.conversation.pk]),
        )

    def test_performance_analysis_is_linked_below_reservations(self):
        response = self.client.get(reverse("bichiku:dashboard"))
        content = response.content.decode()

        reservation_position = content.index(
            f'href="{reverse("bichiku:reservation_list")}"'
        )
        analysis_position = content.index(
            f'href="{reverse("bichiku:performance_analysis")}"'
        )
        messages_position = content.index(
            f'href="{reverse("bichiku:messages")}"'
        )

        self.assertLess(reservation_position, analysis_position)
        self.assertLess(analysis_position, messages_position)

    def test_performance_analysis_aggregates_successful_pickups_by_unit(self):
        PickupRecord.objects.create(
            reservation=self.conversation.reservation,
            user=self.requester,
            received_quantity=5,
            picked_up_at=timezone.now(),
            pickup_status=PickupRecord.PickupStatus.COMPLETED,
        )
        PickupRecord.objects.create(
            reservation=self.conversation.reservation,
            user=self.requester,
            received_quantity=99,
            picked_up_at=timezone.now(),
            pickup_status=PickupRecord.PickupStatus.NO_SHOW,
        )

        response = self.client.get(reverse("bichiku:performance_analysis"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bichiku/performance_analysis.html")
        self.assertContains(response, "受け渡し完了・一部受取")
        self.assertContains(response, "5<small>本</small>")
        self.assertContains(response, "飲料")
        self.assertContains(response, "過去12か月")
        self.assertNotContains(response, "99")

    def test_performance_analysis_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("bichiku:performance_analysis"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('bichiku:performance_analysis')}",
        )

    def test_opening_conversation_marks_messages_read_and_sends_reply(self):
        incoming = Message.objects.create(
            conversation=self.conversation,
            sender=self.provider,
            content="受け取り日時をご相談できますか？",
        )

        response = self.client.get(
            reverse("bichiku:conversation_detail", args=[self.conversation.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="content"')
        incoming.refresh_from_db()
        self.assertTrue(incoming.is_read)

        response = self.client.post(
            reverse("bichiku:conversation_detail", args=[self.conversation.pk]),
            {"content": "来週火曜日を希望します。"},
        )

        self.assertRedirects(
            response,
            reverse("bichiku:conversation_detail", args=[self.conversation.pk]),
        )
        reply = Message.objects.get(content="来週火曜日を希望します。")
        self.assertEqual(reply.sender, self.requester)
        self.assertEqual(reply.conversation, self.conversation)

    def test_other_organization_cannot_open_conversation(self):
        outsider = get_user_model().objects.create_user(
            username="outsider@example.com",
            email="outsider@example.com",
            password="initial-password-123",
        )
        outsider_org = Organization.objects.create(
            name="別団体",
            account_type=Organization.AccountType.GROUP,
        )
        Profile.objects.create(user=outsider, organization=outsider_org)
        self.client.force_login(outsider)

        response = self.client.get(
            reverse("bichiku:conversation_detail", args=[self.conversation.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_my_page_displays_profile_and_updates_organization(self):
        response = self.client.get(reverse("bichiku:my_page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "さくら子ども食堂")
        self.assertContains(response, "佐藤 花子")
        self.assertContains(response, self.requester.email)

        response = self.client.post(
            f"{reverse('bichiku:my_page')}?edit=1",
            {
                "action": "organization",
                "name": "さくら子ども食堂（更新）",
                "account_type": Organization.AccountType.GROUP,
                "address": "東京都渋谷区",
                "postal_code": "150-0001",
                "phone_number": "03-9876-5432",
                "website_url": "",
                "notes": "地域の子どもを支援しています。",
                "contact_person_name": "鈴木 花子",
                "department_name": "",
                "contact_person_phone": "",
            },
        )

        self.assertRedirects(response, reverse("bichiku:my_page"))
        self.requester_org.refresh_from_db()
        self.assertEqual(self.requester_org.name, "さくら子ども食堂（更新）")
        self.assertEqual(self.requester_org.address, "東京都渋谷区")

    def test_my_page_changes_password_and_keeps_user_logged_in(self):
        response = self.client.post(
            reverse("bichiku:my_page"),
            {
                "action": "password",
                "old_password": "initial-password-123",
                "new_password1": "brand-new-password-456",
                "new_password2": "brand-new-password-456",
            },
        )

        self.assertRedirects(response, reverse("bichiku:my_page"))
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.check_password("brand-new-password-456"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.requester.pk)
