"""ダッシュボードに出す集計。

lots は、その企業の備蓄品(ロット)の一覧(views.py の _inventory_lots_for の結果)です。
"""

from datetime import timedelta

from django.utils import timezone

from .models import EXPIRY_WARNING_DAYS, Reservation, StockLot

PANEL_LIMIT = 5


def dashboard_stats(lots, organization):
    today = timezone.localdate()
    limit = today + timedelta(days=EXPIRY_WARNING_DAYS)

    in_stock = lots.filter(quantity__gt=0)  # 全部渡し終えた(数量0の)ものは、数えない
    attention = in_stock.filter(expiration_date__lte=limit)  # 期限切れ + 期限が近い
    available = in_stock.filter(
        availability=StockLot.Availability.AVAILABLE, expiration_date__gte=today
    )
    reserved_count = 0
    if organization is not None:
        reserved_count = Reservation.objects.filter(
            offer__organization=organization,
            status__in=Reservation.ACTIVE_STATUSES,
        ).count()

    expiring = [
        {"lot": lot, "days_left": (lot.expiration_date - today).days}
        for lot in attention.select_related("stock_item").order_by("expiration_date")[:PANEL_LIMIT]
    ]
    return {
        "total": lots.count(),
        "expiring_count": attention.count(),
        "available_count": available.count(),
        "reserved_count": reserved_count,
        "expiring": expiring,
    }