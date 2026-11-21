"""ダッシュボードに出す集計。

lots は、その企業の備蓄品(ロット)の一覧(views.py の _inventory_lots_for の結果)です。
カードの数字は、押したときに開く画面の件数と、同じになるようにしています。
  - 承認待ちの予約   → 予約一覧(?status=reserved)
  - 受け取り予定     → 予約一覧(?status=scheduled)
  - 消費期限が近い   → 備蓄品管理(?expiry=warning)
  - 期限切れ         → 備蓄品管理(?expiry=expired)
  - 募集中           → 募集管理(?status=recruiting)
"""

from datetime import timedelta

from django.utils import timezone

from .models import EXPIRY_WARNING_DAYS, Offer, Reservation, StockLot

PANEL_LIMIT = 5


def _offer_states(lot_ids):
    """ロットごとの、募集の状態(募集中 > 下書き)"""
    states = {}
    for lot_id, status in Offer.objects.filter(
        lot_id__in=lot_ids, status__in=[Offer.Status.DRAFT, Offer.Status.RECRUITING]
    ).values_list("lot_id", "status"):
        if states.get(lot_id) != Offer.Status.RECRUITING:
            states[lot_id] = status
    return states


def dashboard_stats(lots, organization):
    today = timezone.localdate()
    limit = today + timedelta(days=EXPIRY_WARNING_DAYS)

    in_stock = lots.filter(quantity__gt=0)  # 全部渡し終えた(数量0の)ものは、数えない
    expired = in_stock.filter(expiration_date__lt=today)
    warning = in_stock.filter(expiration_date__gte=today, expiration_date__lte=limit)

    pending = scheduled = recruiting = 0
    if organization is not None:
        own = Reservation.objects.filter(offer__organization=organization)
        pending = own.filter(status=Reservation.Status.PENDING).count()
        scheduled = own.filter(status=Reservation.Status.APPROVED).count()
        recruiting = Offer.objects.filter(
            organization=organization, status=Offer.Status.RECRUITING
        ).count()

    panel_lots = list(
        in_stock.filter(expiration_date__lte=limit)
        .select_related("stock_item")
        .order_by("expiration_date")[:PANEL_LIMIT]
    )
    states = _offer_states([lot.pk for lot in panel_lots])
    rows = []
    for lot in panel_lots:
        days_left = (lot.expiration_date - today).days
        state = states.get(lot.pk)
        rows.append(
            {
                "lot": lot,
                "days_left": days_left,
                "offer_state": state,  # None / "draft" / "recruiting"
                # 期限内で、提供対象で、まだ募集も下書きもないものは、ここから募集を作れる
                "can_offer": state is None
                and days_left >= 0
                and lot.availability == StockLot.Availability.AVAILABLE,
            }
        )

    return {
        "total": lots.count(),
        "pending_count": pending,
        "scheduled_count": scheduled,
        "expiring_count": warning.count(),
        "expired_count": expired.count(),
        "recruiting_count": recruiting,
        "expiring": rows,
    }