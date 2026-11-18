def test_logged_in_user_can_open_reservations(self):
    from datetime import timedelta
    from django.utils import timezone
    from .models import (Organization, Profile, StockItem, StockLot,
                         Offer, Reservation)
    from django.contrib.auth.models import User

    company = Organization.objects.create(name="企業A", account_type=Organization.AccountType.COMPANY)
    group = Organization.objects.create(name="団体B", account_type=Organization.AccountType.GROUP)
    user = User.objects.create_user(username="co@example.com", email="co@example.com", password="pass12345")
    Profile.objects.create(user=user, organization=company)
    item = StockItem.objects.create(organization=company, name="水", unit="本")
    lot = StockLot.objects.create(stock_item=item, quantity=10, storage_place="倉庫",
        expiration_date=timezone.localdate() + timedelta(days=30),
        availability=StockLot.Availability.AVAILABLE)
    offer = Offer.objects.create(lot=lot, organization=company, title="水", quantity=5,
        pickup_location="倉庫", prefecture="東京都",
        deadline=timezone.localdate() + timedelta(days=10), status=Offer.Status.RECRUITING)
    Reservation.objects.create(offer=offer, organization=group, reserved_quantity=2,
        requested_pickup_at=timezone.now() + timedelta(days=3))

    self.client.login(username="co@example.com", password="pass12345")
    response = self.client.get(reverse("bichiku:reservation_list"))
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, "bichiku/reservations.html")
    self.assertContains(response, 'class="reservation-detail-trigger"')
    self.assertContains(response, 'class="reservation-detail-popover"')