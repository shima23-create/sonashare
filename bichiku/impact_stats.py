"""実績分析用: 譲渡による食品ロス削減の効果(概算)を集計する。

対象は、受け取りが完了した記録(受取完了・一部受取)のうち、食品(飲料・主食)のもの。
  削減量(kg) = 受け取った数量 × 1単位の重さ(標準の重さ。impact_factors.py)
  CO2削減量  = 削減量 × 係数
  廃棄費用の削減額 = 削減量 × 処理単価
あわせて、今ある在庫のうち、期限が近い/切れた食品の量も出します(管理の効果を見るため)。
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from . import impact_factors as f
from .models import PickupRecord, StockLot

C = f.C
FOOD_LABELS = {c.value: c.label for c in f.FOOD_CATEGORIES}


def _month_start(day, back):
    year, month = day.year, day.month - back
    while month < 1:
        month += 12
        year -= 1
    return day.replace(year=year, month=month, day=1)


def _round(value):
    return round(value + 1e-9, 1)


def _yen(kg):
    return int(round(kg * f.DISPOSAL_YEN_PER_KG))


def _co2(kg):
    return _round(kg * f.CO2_KG_PER_KG)


def impact_stats(organization, today=None, months=12):
    today = today or timezone.localdate()
    starts = [_month_start(today, back) for back in range(months - 1, -1, -1)]
    first = starts[0]

    records = (
        PickupRecord.objects.filter(
            Q(reservation__offer__organization=organization)
            | Q(reservation__organization=organization),
            pickup_status__in=[PickupRecord.PickupStatus.COMPLETED, PickupRecord.PickupStatus.PARTIAL],
            received_quantity__gt=0,
            picked_up_at__date__gte=first,
        )
        .select_related("reservation__offer__lot__stock_item")
        .distinct()
    )

    total = 0.0
    by_category = {c.value: 0.0 for c in f.FOOD_CATEGORIES}
    by_month = {s: 0.0 for s in starts}
    converted = unconverted = excluded = 0
    for record in records:
        item = record.reservation.offer.lot.stock_item
        if item.category not in FOOD_LABELS:
            excluded += 1
            continue
        kg = f.weight_kg(item.category, item.unit, record.received_quantity)
        if kg is None:
            unconverted += 1
            continue
        converted += 1
        total += kg
        by_category[item.category] += kg
        month = timezone.localtime(record.picked_up_at).date().replace(day=1)
        if month in by_month:
            by_month[month] += kg

    peak = max(by_month.values()) if by_month else 0
    monthly = [
        {"month": m, "kg": _round(kg), "bar_percent": int(kg / peak * 100) if peak else 0}
        for m, kg in by_month.items()
    ]
    categories = [
        {"category": c.value, "label": c.label, "kg": _round(by_category[c.value])}
        for c in f.FOOD_CATEGORIES
    ]

    at_risk, expired = _stock_risk(organization, today)

    return {
        "total_kg": _round(total),
        "co2_kg": _co2(total),
        "saved_yen": _yen(total),
        "converted_count": converted,
        "unconverted_count": unconverted,
        "excluded_count": excluded,
        "categories": categories,
        "monthly": monthly,
        "at_risk_kg": _round(at_risk),
        "at_risk_yen": _yen(at_risk),
        "expired_kg": _round(expired),
        "expired_yen": _yen(expired),
        "co2_factor": f.CO2_KG_PER_KG,
        "disposal_yen_per_kg": f.DISPOSAL_YEN_PER_KG,
        "warning_days": f.WARNING_DAYS,
    }


def _stock_risk(organization, today):
    """今ある在庫のうち、期限が近い食品(今なら譲渡できる)と、期限が切れた食品(廃棄になる見込み)の重さ"""
    lots = StockLot.objects.filter(
        stock_item__organization=organization,
        stock_item__category__in=FOOD_LABELS,
        quantity__gt=0,
        expiration_date__isnull=False,
        expiration_date__lte=today + timedelta(days=f.WARNING_DAYS),
    ).select_related("stock_item")
    at_risk = expired = 0.0
    for lot in lots:
        kg = f.weight_kg(lot.stock_item.category, lot.stock_item.unit, lot.quantity)
        if kg is None:
            continue
        if lot.expiration_date < today:
            expired += kg
        else:
            at_risk += kg
    return at_risk, expired
