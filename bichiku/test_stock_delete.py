from django.test import TestCase

from .models import Offer, Organization, Reservation, StockItem, StockLot
from .stock_services import StockDeleteError, delete_lot
from .test_group import make_offer
from .test_offers import make_lot, make_user
from .test_reservations import GROUP, R, make_reservation


class DeleteLotTests(TestCase):
    def setUp(self):
        _, self.company = make_user("c")
        _, self.group = make_user("g", GROUP)
        self.lot = make_lot(self.company, qty=100)
        self.offer = make_offer(self.company, self.lot, quantity=10)

    def assert_blocked(self, text):
        with self.assertRaises(StockDeleteError) as ctx:
            delete_lot(self.lot)
        self.assertIn(text, ctx.exception.message)
        self.assertTrue(StockLot.objects.filter(pk=self.lot.pk).exists())

    def test_lot_without_anything_is_deleted_with_its_item(self):
        lot = make_lot(self.company, name="別の備蓄品")
        item_id = lot.stock_item_id
        delete_lot(lot)
        self.assertFalse(StockLot.objects.filter(pk=lot.pk).exists())
        self.assertFalse(StockItem.objects.filter(pk=item_id).exists())

    def test_cancelled_reservation_no_longer_blocks(self):
        make_reservation(self.offer, self.group, 3, R.CANCELLED)
        self.offer.status = Offer.Status.CLOSED
        self.offer.save()
        delete_lot(self.lot)
        self.assertFalse(StockLot.objects.filter(pk=self.lot.pk).exists())
        self.assertEqual(Reservation.objects.count(), 0)
        self.assertEqual(Offer.objects.count(), 0)

    def test_recruiting_offer_blocks(self):
        self.assert_blocked("募集中")

    def test_active_reservation_blocks(self):
        self.offer.status = Offer.Status.CLOSED
        self.offer.save()
        make_reservation(self.offer, self.group, 3, R.APPROVED)
        self.assert_blocked("予約中・承認済み")

    def test_completed_history_blocks(self):
        self.offer.status = Offer.Status.CLOSED
        self.offer.save()
        make_reservation(self.offer, self.group, 3, R.COMPLETED)
        self.assert_blocked("実績")

    def test_other_lots_of_same_item_keep_the_item(self):
        self.offer.status = Offer.Status.CLOSED
        self.offer.save()
        other = StockLot.objects.create(
            stock_item=self.lot.stock_item, quantity=5,
            expiration_date=self.lot.expiration_date, storage_place="倉庫B",
        )
        delete_lot(self.lot)
        self.assertTrue(StockItem.objects.filter(pk=other.stock_item_id).exists())
        self.assertTrue(StockLot.objects.filter(pk=other.pk).exists())