"""備蓄品(ロット)の削除。

キャンセル済みの予約や、募集中でない募集は、履歴として残っているだけなので、
ロットと一緒に整理して削除します。
次の場合だけは、削除を止めます。
  - 募集中の募集がある
  - 予約中・承認済みの予約がある
  - 受け取りが完了した実績がある(記録として残すため)
"""

from django.db import transaction

from .models import Offer, Reservation, StockLot


class StockDeleteError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


@transaction.atomic
def delete_lot(lot):
    """ロットを削除する。ほかのロットが無くなった備蓄品も、あわせて削除する"""
    lot = StockLot.objects.select_for_update().select_related("stock_item").get(pk=lot.pk)
    offers = Offer.objects.filter(lot=lot)
    reservations = Reservation.objects.filter(offer__lot=lot)

    if offers.filter(status=Offer.Status.RECRUITING).exists():
        raise StockDeleteError("募集中の募集があります。先に募集を終了してください。")
    if reservations.filter(status__in=Reservation.ACTIVE_STATUSES).exists():
        raise StockDeleteError(
            "予約中・承認済みの予約があります。先に予約を取り消すか、受け取り完了にしてください。"
        )
    if reservations.filter(status=Reservation.Status.COMPLETED).exists():
        raise StockDeleteError("受け取りが完了した実績があるため、削除できません。")

    # ここまで来たら、残っているのはキャンセル済みの予約と、終了・下書きの募集だけ
    reservations.delete()
    offers.delete()

    item = lot.stock_item
    lot.delete()
    if not item.lots.exists():
        item.delete()