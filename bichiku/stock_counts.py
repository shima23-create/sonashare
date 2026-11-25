"""備蓄品充足率の計算用に、カテゴリごとの備蓄数量を数える。

充足率目標の計算では、次の3つの不足分を出します。
  - 水         → カテゴリ「飲料」(DRINK)
  - 主食       → カテゴリ「主食」(STAPLE。缶詰・レトルト食品もここに含む)
  - 簡易トイレ → カテゴリ「簡易トイレ」(TOILET)

数えるもの: その組織の、数量が1以上で、消費期限が切れていない(期限なしを含む)ロット。
            提供しない(社内備蓄)、提供可能、予約中のものも、手元にある備蓄として数えます。
            全部渡し終えた(数量0)ものと、期限切れのものは、数えません。
"""

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import StockItem, StockLot

C = StockItem.Category

# 充足率の計算の対象(この順番で返します)
TARGET_CATEGORIES = (C.DRINK, C.STAPLE, C.TOILET)


def usable_lots(organization, today=None):
    """手元にあって、まだ使える(期限切れでない)ロット"""
    today = today or timezone.localdate()
    return StockLot.objects.filter(
        stock_item__organization=organization,
        quantity__gt=0,
    ).filter(Q(expiration_date__isnull=True) | Q(expiration_date__gte=today))


def category_counts(organization, categories=TARGET_CATEGORIES, today=None):
    """カテゴリごとの備蓄数量を、リストで返す。備蓄が0でも、必ず1行ずつ入る。

    [
      {"category": "drink", "label": "飲料", "total": 120, "lot_count": 3,
       "by_unit": [{"unit": "本", "quantity": 100}, {"unit": "箱", "quantity": 20}]},
      ...
    ]
    total は、単位が違うものも足した数です。単位をそろえたいときは、by_unit を使ってください。
    """
    lots = usable_lots(organization, today)
    totals = {
        row["stock_item__category"]: row
        for row in lots.values("stock_item__category").annotate(
            total=Sum("quantity"), lot_count=Count("id")
        )
    }
    units = {}
    for row in (
        lots.values("stock_item__category", "stock_item__unit")
        .annotate(quantity=Sum("quantity"))
        .order_by("stock_item__unit")
    ):
        units.setdefault(row["stock_item__category"], []).append(
            {"unit": row["stock_item__unit"], "quantity": row["quantity"]}
        )

    result = []
    for category in categories:
        row = totals.get(category.value, {})
        result.append(
            {
                "category": category.value,
                "label": category.label,
                "total": row.get("total") or 0,
                "lot_count": row.get("lot_count") or 0,
                "by_unit": units.get(category.value, []),
            }
        )
    return result


def category_count_map(organization, categories=TARGET_CATEGORIES, today=None):
    """カテゴリの値 → 数量(例: {"drink": 120, "staple": 80, "toilet": 0})"""
    return {r["category"]: r["total"] for r in category_counts(organization, categories, today)}