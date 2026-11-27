"""食品ロス削減の効果を概算するための、数字をまとめたファイル。

ここの数字を変えるだけで、実績分析の計算が変わります(画面や計算のコードは変えなくて大丈夫です)。
すべて「概算」のための仮の数字です。実際の重さや費用とは違います。
"""

from .models import StockItem

C = StockItem.Category

# 食品ロスとして数えるカテゴリ(簡易トイレ・生理用品・医療品・その他は、食品ではないので数えない)
FOOD_CATEGORIES = (C.DRINK, C.STAPLE)

# 1単位あたりの重さ(kg)。カテゴリ × 単位 の組み合わせで決める。
# ここにない組み合わせ(例: 飲料の「食」)は、重さが分からないので、換算の対象から外す。
UNIT_WEIGHT_KG = {
    C.DRINK: {"本": 0.5, "缶": 0.35, "個": 0.5, "袋": 0.5, "箱": 6, "ケース": 12},
    C.STAPLE: {"本": 0.5, "缶": 0.2, "食": 0.25, "個": 0.2, "袋": 0.3, "箱": 3, "ケース": 6},
}

# 食品ロス 1kg あたりの CO2 排出量(kg-CO2/kg)。
# 環境省「ecojin」特集(令和4年度): 食品ロス約472万トン → 生産に伴うCO2 約1,046万トン、を割った参考値。
# 公式の換算係数ではありません。
CO2_KG_PER_KG = 2.2

# 廃棄するときの処理費用(円/kg)。
# 東京23区の事業系一般廃棄物処理手数料(令和5年10月〜 1kgあたり46円)を目安にした値。
# 地域や契約によって違います。
DISPOSAL_YEN_PER_KG = 46

# 「期限が近い」とみなす日数(今のうちに譲渡すれば、廃棄を避けられる範囲)
WARNING_DAYS = 30


def unit_weight_kg(category, unit):
    """1単位あたりの重さ(kg)。分からなければ None"""
    return UNIT_WEIGHT_KG.get(category, {}).get(unit)


def weight_kg(category, unit, quantity):
    """数量ぶんの重さ(kg)。分からなければ None"""
    per_unit = unit_weight_kg(category, unit)
    return None if per_unit is None else per_unit * quantity
