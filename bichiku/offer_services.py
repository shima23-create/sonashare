"""募集の公開・更新・終了で、備蓄品(ロット)の数量を増減する処理。
 
同時に操作されても数量がずれないよう、ロットを select_for_update でロックし、
transaction.atomic の中でまとめて処理します。
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
    """下書き(または新規)を「募集中」にし、提供数量をロットから引く"""
    lot = _lock_lot(offer.lot_id)
    if offer.pk:
        stored = Offer.objects.select_for_update().get(pk=offer.pk)
        if stored.status != Offer.Status.DRAFT:
            raise OfferError(["下書きの募集だけ、公開できます。"])
    offer.lot = lot
 
    problems = publish_problems(offer)
    if problems:
        raise OfferError(problems)
 
    lot.quantity -= offer.quantity
    lot.save(update_fields=["quantity", "updated_at"])
    offer.status = Offer.Status.RECRUITING
    offer.save()
    return offer
 
 
@transaction.atomic
def update_recruiting_offer(offer):
    """募集中の募集を更新する。数量が変わった分だけ、ロットの数量を増減する"""
    lot = _lock_lot(offer.lot_id)
    stored = Offer.objects.select_for_update().get(pk=offer.pk)
    if stored.status != Offer.Status.RECRUITING:
        raise OfferError(["募集中の募集だけ、この方法で更新できます。"])
    offer.lot = lot
 
    problems = publish_problems(offer)
    if problems:
        raise OfferError(problems)
 
    lot.quantity = lot.quantity + stored.quantity - offer.quantity
    lot.save(update_fields=["quantity", "updated_at"])
    offer.save()
    return offer
 
 
@transaction.atomic
def close_offer(offer):
    """募集を終了する。予約されていない分を、ロットに戻す。
    予約済みの分は、受け渡しのためにその募集に残し、募集の数量をその数に揃える。
    戻した数量を返す。"""
    stored = Offer.objects.select_for_update().get(pk=offer.pk)
    lot = _lock_lot(stored.lot_id)
    if stored.status != Offer.Status.RECRUITING:
        raise OfferError(["募集中の募集だけ、終了できます。"])
 
    reserved = reserved_quantity_of(stored)
    returned = max(stored.quantity - reserved, 0)
 
    lot.quantity += returned
    lot.save(update_fields=["quantity", "updated_at"])
    stored.status = Offer.Status.CLOSED
    stored.quantity = reserved
    stored.save()
    return returned