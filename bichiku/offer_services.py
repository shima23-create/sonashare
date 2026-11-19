"""募集の公開・更新・終了の処理。

備蓄品(ロット)の数量は、ここでは変えません(減るのは受け取り完了のときだけ)。
同時に公開されても確保数量が在庫を超えないよう、ロットを select_for_update で
ロックし、transaction.atomic の中で処理します。
"""

from django.db import transaction

from .models import Offer, StockLot
from .offer_forms import publish_problems, reserved_quantity_of


class OfferError(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def _lock_lot(lot_id):
    return StockLot.objects.select_for_update().select_related("stock_item").get(pk=lot_id)


@transaction.atomic
def publish_offer(offer):
    """下書き(または新規)を「募集中」にし、提供数量を確保する(在庫は減らさない)"""
    lot = _lock_lot(offer.lot_id)
    if offer.pk:
        stored = Offer.objects.select_for_update().get(pk=offer.pk)
        if stored.status != Offer.Status.DRAFT:
            raise OfferError(["下書きの募集だけ、公開できます。"])
    offer.lot = lot

    problems = publish_problems(offer)
    if problems:
        raise OfferError(problems)

    offer.status = Offer.Status.RECRUITING
    offer.save()
    return offer


@transaction.atomic
def update_recruiting_offer(offer):
    """募集中の募集を更新する(確保数量が変わるだけで、在庫は減らさない)"""
    lot = _lock_lot(offer.lot_id)
    stored = Offer.objects.select_for_update().get(pk=offer.pk)
    if stored.status != Offer.Status.RECRUITING:
        raise OfferError(["募集中の募集だけ、この方法で更新できます。"])
    offer.lot = lot

    problems = publish_problems(offer)
    if problems:
        raise OfferError(problems)

    offer.save()
    return offer


@transaction.atomic
def close_offer(offer):
    """募集を終了する。予約されていない分の確保を解除する。
    予約済みの分は、受け渡しのためにその募集に残し、募集の数量をその数に揃える。
    解除した数量を返す。"""
    stored = Offer.objects.select_for_update().get(pk=offer.pk)
    _lock_lot(stored.lot_id)
    if stored.status != Offer.Status.RECRUITING:
        raise OfferError(["募集中の募集だけ、終了できます。"])

    reserved = reserved_quantity_of(stored)
    returned = max(stored.quantity - reserved, 0)

    stored.status = Offer.Status.CLOSED
    stored.quantity = reserved
    stored.save()
    return returned